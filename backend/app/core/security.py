"""
AutoHeal DevOps — Core Security Utilities
Argon2id password hashing, PyJWT access token signing, token rotation hashes.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Any, Dict, Optional
import uuid

import jwt
from passlib.context import CryptContext

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Argon2id password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against an Argon2id hashed string.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.warning("Password verification failed unexpectedly: %s", e)
        return False


def get_password_hash(password: str) -> str:
    """
    Hashes a plain-text password using Argon2id.
    """
    return pwd_context.hash(password)


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    org_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Issues a short-lived (15-minute) signed JWT access token.
    Claims: sub (user_id), email, role, org_id, jti, iat, exp, type="access".
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": org_id,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and validates a JWT access token.
    Returns the decoded claims dictionary, or None if invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        # Ensure token type is access
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Access token has expired.")
        return None
    except jwt.PyJWTError as e:
        logger.debug("Invalid JWT token: %s", e)
        return None


def generate_refresh_token() -> str:
    """
    Generates a cryptographically strong, URL-safe random string for refresh tokens.
    Provides ~288 bits of entropy.
    """
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """
    Computes SHA-256 hex digest of a token string for secure persistent storage.
    Prevents token exposure in case of read-only database compromise.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_password_reset_token() -> str:
    """
    Generates a cryptographically strong one-time token for password reset flows.
    """
    return secrets.token_urlsafe(32)
