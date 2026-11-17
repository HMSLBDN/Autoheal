"""
AutoHeal DevOps — Restricted Infrastructure Agent Security
Cryptographic envelope signing, signature verification, nonce replay prevention, and timestamp validation.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)

# In-memory nonce cache with TTL to prevent replay attacks
# (In multi-node production setups, this can also be backed by Redis)
_SEEN_NONCES: Dict[str, float] = {}
NONCE_EXPIRY_SECONDS = 300  # 5 minutes
MAX_TIMESTAMP_DRIFT_SECONDS = 300  # Reject requests older than 5 minutes or >5m in future


def clean_expired_nonces():
    """Removes expired nonces from the replay cache."""
    now = time.time()
    expired = [nonce for nonce, ts in _SEEN_NONCES.items() if now - ts > NONCE_EXPIRY_SECONDS]
    for nonce in expired:
        _SEEN_NONCES.pop(nonce, None)


def canonicalize_payload(
    action_id: str,
    service_id: str,
    action_type: str,
    parameters: Dict[str, Any],
    nonce: str,
    timestamp_iso: str,
) -> bytes:
    """Produces a deterministic canonical byte representation of the action request."""
    sorted_params = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    canonical_string = f"{action_id}:{service_id}:{action_type}:{sorted_params}:{nonce}:{timestamp_iso}"
    return canonical_string.encode("utf-8")


def sign_payload(
    secret_key: str,
    action_id: str,
    service_id: str,
    action_type: str,
    parameters: Dict[str, Any],
    nonce: str,
    timestamp_iso: str,
) -> str:
    """Generates an HMAC-SHA256 hex signature for the action payload."""
    data = canonicalize_payload(action_id, service_id, action_type, parameters, nonce, timestamp_iso)
    return hmac.new(secret_key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def verify_payload_signature(
    secret_key: str,
    action_id: str,
    service_id: str,
    action_type: str,
    parameters: Dict[str, Any],
    nonce: str,
    timestamp: datetime,
    provided_signature: str,
) -> bool:
    """
    Verifies that:
    1. Signature matches HMAC-SHA256 over canonical data.
    2. Timestamp is within acceptable clock drift (<= 300s).
    3. Nonce has not been seen before (replay attack prevention).
    """
    clean_expired_nonces()

    # 1. Check clock drift
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    drift = abs((now - timestamp).total_seconds())
    if drift > MAX_TIMESTAMP_DRIFT_SECONDS:
        logger.warning("Agent signature verification failed: Timestamp drift %s exceeds threshold.", drift)
        return False

    # 2. Check nonce replay
    if nonce in _SEEN_NONCES:
        logger.warning("Agent signature verification failed: Nonce '%s' already used (replay detected).", nonce)
        return False

    # 3. Verify HMAC signature
    timestamp_iso = timestamp.isoformat()
    expected_sig = sign_payload(secret_key, action_id, service_id, action_type, parameters, nonce, timestamp_iso)
    if not hmac.compare_digest(expected_sig, provided_signature):
        logger.warning("Agent signature verification failed: Signature mismatch.")
        return False

    # Record nonce
    _SEEN_NONCES[nonce] = time.time()
    return True


def sanitize_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures parameters contain no control characters or unexpected structures."""
    sanitized = {}
    for k, v in parameters.items():
        if isinstance(v, str):
            # Strip null bytes and control codes
            clean_str = "".join(ch for ch in v if ord(ch) >= 32 and ord(ch) != 127)
            sanitized[k] = clean_str
        elif isinstance(v, (int, float, bool)):
            sanitized[k] = v
        else:
            # Reject nested arbitrary objects
            sanitized[k] = str(v)
    return sanitized
