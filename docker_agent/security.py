"""
Restricted Docker Agent — Cryptographic Security & Anti-Replay Module
Enforces HMAC-SHA256 signature verification, replay prevention cache, timestamp drift validation,
and input sanitization against command injection.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Strict container name regex (Docker valid container name characters)
CONTAINER_NAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")

# Shell metacharacters forbidden across all inputs
FORBIDDEN_CHARS_PATTERN = re.compile(r"[;&|`$><\n\r\t\\]")

# In-memory nonce cache with TTL to prevent replay attacks
_SEEN_NONCES: Dict[str, float] = {}


def clean_expired_nonces(ttl_seconds: int = 300) -> None:
    """Removes expired nonces from the replay cache."""
    now = time.time()
    expired = [nonce for nonce, ts in _SEEN_NONCES.items() if now - ts > ttl_seconds]
    for nonce in expired:
        _SEEN_NONCES.pop(nonce, None)


def reset_nonce_cache() -> None:
    """Clears the in-memory nonce cache (useful for isolated unit testing)."""
    _SEEN_NONCES.clear()


def canonicalize_payload(
    action_id: str,
    target_container: str,
    action_type: str,
    parameters: Dict[str, Any],
    nonce: str,
    timestamp_iso: str,
) -> bytes:
    """Produces a deterministic canonical byte representation of the action request."""
    sorted_params = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    canonical_string = f"{action_id}:{target_container}:{action_type}:{sorted_params}:{nonce}:{timestamp_iso}"
    return canonical_string.encode("utf-8")


def sign_payload(
    secret_key: str,
    action_id: str,
    target_container: str,
    action_type: str,
    parameters: Dict[str, Any],
    nonce: str,
    timestamp_iso: str,
) -> str:
    """Generates an HMAC-SHA256 hex signature for the action payload."""
    data = canonicalize_payload(
        action_id, target_container, action_type, parameters, nonce, timestamp_iso
    )
    return hmac.new(secret_key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def verify_payload_signature(
    secret_key: str,
    action_id: str,
    target_container: str,
    action_type: str,
    parameters: Dict[str, Any],
    nonce: str,
    timestamp: datetime,
    provided_signature: str,
    max_drift_seconds: int = 300,
    nonce_ttl_seconds: int = 300,
) -> Tuple[bool, str]:
    """
    Independently verifies request authorization:
    1. Rejects timestamps with excessive clock drift (> max_drift_seconds).
    2. Rejects reused nonces to prevent replay attacks.
    3. Verifies HMAC-SHA256 signature against canonical payload.
    Returns: (is_valid: bool, error_reason: str)
    """
    clean_expired_nonces(ttl_seconds=nonce_ttl_seconds)

    # 1. Clock drift check
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    drift = abs((now - timestamp).total_seconds())
    if drift > max_drift_seconds:
        msg = f"Signature verification rejected: Timestamp drift ({drift:.1f}s) exceeds threshold ({max_drift_seconds}s)."
        logger.warning(msg)
        return False, msg

    # 2. Nonce replay check
    if nonce in _SEEN_NONCES:
        msg = f"Signature verification rejected: Nonce '{nonce}' has already been processed (replay detected)."
        logger.warning(msg)
        return False, msg

    # 3. HMAC-SHA256 signature comparison
    timestamp_iso = timestamp.isoformat()
    expected_sig = sign_payload(
        secret_key, action_id, target_container, action_type, parameters, nonce, timestamp_iso
    )
    if not hmac.compare_digest(expected_sig, provided_signature):
        msg = "Signature verification rejected: HMAC signature mismatch."
        logger.warning(msg)
        return False, msg

    # Record nonce in replay prevention cache
    _SEEN_NONCES[nonce] = time.time()
    return True, ""


def validate_container_name_security(container_name: str) -> Tuple[bool, str]:
    """
    Validates that container_name contains only valid characters and no directory traversal
    or shell injection attempts.
    """
    clean = container_name.strip()
    if not clean or not CONTAINER_NAME_REGEX.match(clean):
        return (
            False,
            f"Invalid container identifier '{clean}'. Must match alphanumeric with hyphens/underscores.",
        )

    if FORBIDDEN_CHARS_PATTERN.search(clean):
        return False, f"Prohibited metacharacters detected in container name: '{clean}'."

    return True, ""
