"""
AutoHeal DevOps — Authentication & Session Management Router
Implements Argon2id hashing, JWT access tokens, Refresh Token Rotation (RTR),
replay attack invalidation, self-service password recovery, and session revocation.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.api.deps import DatabaseDep, get_current_user
from app.config import get_settings
from app.core.rate_limit import check_auth_rate_limit
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.models.audit import AuditLog
from app.models.organization import Organization
from app.models.password_reset import PasswordReset
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    AuthMessageResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Sets secure, HttpOnly refresh token cookie on HTTP response."""
    secure_cookie = settings.COOKIE_SECURE if settings.COOKIE_SECURE is not None else (settings.APP_ENV not in ("development", "test"))
    samesite_policy = settings.COOKIE_SAMESITE if settings.COOKIE_SAMESITE is not None else ("none" if secure_cookie else "lax")
    max_age_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    kwargs = {
        "key": "refresh_token",
        "value": refresh_token,
        "max_age": max_age_seconds,
        "httponly": True,
        "samesite": samesite_policy,
        "secure": secure_cookie,
        "path": "/api/v1/auth",
    }
    if settings.COOKIE_DOMAIN:
        kwargs["domain"] = settings.COOKIE_DOMAIN
    response.set_cookie(**kwargs)


def _clear_refresh_cookie(response: Response) -> None:
    """Clears refresh token cookie with matching attributes."""
    secure_cookie = settings.COOKIE_SECURE if settings.COOKIE_SECURE is not None else (settings.APP_ENV not in ("development", "test"))
    samesite_policy = settings.COOKIE_SAMESITE if settings.COOKIE_SAMESITE is not None else ("none" if secure_cookie else "lax")
    kwargs = {
        "key": "refresh_token",
        "path": "/api/v1/auth",
        "secure": secure_cookie,
        "samesite": samesite_policy,
        "httponly": True,
    }
    if settings.COOKIE_DOMAIN:
        kwargs["domain"] = settings.COOKIE_DOMAIN
    response.delete_cookie(**kwargs)


def _to_utc(dt: datetime) -> datetime:
    """Ensures datetime is timezone-aware UTC, even when loaded from naive SQLite timestamps."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
    dependencies=[Depends(check_auth_rate_limit)],
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    response: Response,
    db: DatabaseDep,
) -> TokenResponse:
    """
    Registers a new user account, enforces password hashing via Argon2id,
    associates the user with the default organization, prevents unauthorized role escalation,
    and returns initial JWT access and refresh tokens.
    """
    normalized_email = payload.email.lower().strip()

    try:
        # 1. Prevent duplicate accounts
        existing_user_query = await db.execute(
            select(User).where(User.email == normalized_email)
        )
        if existing_user_query.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists.",
            )

        # 2. Prevent unauthorized role escalation during self-registration
        safe_role = "operator"
        if payload.role and payload.role.lower() in ("viewer", "operator"):
            safe_role = payload.role.lower()

        # 3. Associate with organization (resolve default or create if unprovisioned)
        org_query = await db.execute(
            select(Organization).where(Organization.slug == settings.DEFAULT_ORGANIZATION_SLUG)
        )
        org = org_query.scalar_one_or_none()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                slug=settings.DEFAULT_ORGANIZATION_SLUG,
                name=settings.DEFAULT_ORGANIZATION_NAME,
                plan="enterprise",
                is_active=True,
            )
            db.add(org)
            await db.flush()

        # 4. Hash password with Argon2id and create User
        hashed_pwd = get_password_hash(payload.password)
        user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=normalized_email,
            full_name=payload.full_name.strip(),
            hashed_password=hashed_pwd,
            role=safe_role,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        # 5. Issue JWT access token
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            org_id=str(user.organization_id),
        )

        # 6. Issue refresh token and persist hashed value with family ID
        raw_refresh_token = generate_refresh_token()
        family_id = str(uuid.uuid4())
        token_hash = hash_token(raw_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        db_refresh_token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            is_revoked=False,
            expires_at=expires_at,
            ip_address=client_ip,
            user_agent=user_agent[:500] if user_agent else None,
        )
        db.add(db_refresh_token)

        # 7. Record audit log
        db.add(AuditLog(
            organization_id=org.id,
            user_id=user.id,
            action="user_registered",
            resource_type="user",
            resource_id=str(user.id),
            details=f"User {user.email} registered successfully with role {user.role}.",
            ip_address=client_ip,
        ))

        await db.commit()
        await db.refresh(user)
    except HTTPException:
        raise
    except IntegrityError as ie:
        await db.rollback()
        logger.warning("Registration integrity collision on email %s: %s", normalized_email, ie)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )
    except (OperationalError, InterfaceError, DBAPIError) as dbe:
        await db.rollback()
        logger.error("Database connection failure during registration: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please retry in a few moments.",
        )

    # 8. Set HttpOnly cookie
    _set_refresh_cookie(response, raw_refresh_token)

    user_response = UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=str(user.organization_id),
        organization_name=org.name,
        is_active=user.is_active,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response,
        refresh_token=raw_refresh_token,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and issue tokens",
    dependencies=[Depends(check_auth_rate_limit)],
)
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: DatabaseDep,
) -> TokenResponse:
    """
    Authenticates user credentials against Argon2id hash.
    Employs generic error message to protect against user enumeration attacks.
    Issues short-lived JWT access token and sets HttpOnly rotated refresh token.
    """
    normalized_email = payload.email.lower().strip()

    try:
        stmt = select(User).options(selectinload(User.organization)).where(User.email == normalized_email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        # Fail securely on non-existent user or invalid password
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Prevent login for deactivated users
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been deactivated. Please contact your organization administrator.",
            )

        # Issue access token
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            org_id=str(user.organization_id),
        )

        # Issue refresh token in new family
        raw_refresh_token = generate_refresh_token()
        family_id = str(uuid.uuid4())
        token_hash = hash_token(raw_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        db_refresh_token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            is_revoked=False,
            expires_at=expires_at,
            ip_address=client_ip,
            user_agent=user_agent[:500] if user_agent else None,
        )
        db.add(db_refresh_token)

        # Record login audit log
        db.add(AuditLog(
            organization_id=user.organization_id,
            user_id=user.id,
            action="user_login",
            resource_type="user",
            resource_id=str(user.id),
            details=f"User {user.email} logged in successfully.",
            ip_address=client_ip,
        ))

        await db.commit()
    except HTTPException:
        raise
    except (OperationalError, InterfaceError, DBAPIError) as dbe:
        await db.rollback()
        logger.error("Database connection failure during login: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable. Please retry in a few moments.",
        )

    # Set cookie
    _set_refresh_cookie(response, raw_refresh_token)

    user_response = UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=str(user.organization_id),
        organization_name=user.organization.name if user.organization else None,
        is_active=user.is_active,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response,
        refresh_token=raw_refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    db: DatabaseDep,
    payload: Optional[TokenRefreshRequest] = None,
    cookie_token: Optional[str] = Cookie(None, alias="refresh_token"),
) -> TokenResponse:
    """
    Implements strict Refresh Token Rotation (RTR):
    - Reads refresh token from HttpOnly cookie or request body.
    - If a revoked token is presented, REPLAY ATTACK is detected: immediately revokes
      the entire token family to defend against compromised tokens!
    - On valid token: revokes the current token, generates a new token in the same family,
      and issues a fresh JWT access token.
    """
    raw_token = (payload.refresh_token if payload and payload.refresh_token else None) or cookie_token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash_val = hash_token(raw_token)

    # Look up token in database
    stmt = (
        select(RefreshToken)
        .options(selectinload(RefreshToken.user).selectinload(User.organization))
        .where(RefreshToken.token_hash == token_hash_val)
    )
    result = await db.execute(stmt)
    token_record = result.scalar_one_or_none()

    if not token_record:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. CRITICAL: REPLAY ATTACK DETECTION
    # If a previously revoked token is presented again, a breach or replay attack is occurring!
    # Invalidate ALL tokens in this family immediately.
    if token_record.is_revoked:
        logger.warning(
            "REPLAY ATTACK DETECTED: Revoked refresh token reused for family %s, user %s. Invalidating entire family.",
            token_record.family_id,
            token_record.user_id,
        )
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token_record.family_id)
            .values(is_revoked=True)
        )
        org_id = token_record.user.organization_id if token_record.user else None
        if not org_id:
            u_res = await db.execute(select(User).where(User.id == token_record.user_id))
            u_rec = u_res.scalar_one_or_none()
            if u_rec:
                org_id = u_rec.organization_id

        if org_id:
            db.add(AuditLog(
                organization_id=org_id,
                user_id=token_record.user_id,
                action="token_replay_detected",
                resource_type="refresh_token",
                resource_id=str(token_record.id),
                details=f"Token replay detected for family {token_record.family_id}. All family tokens revoked.",
                ip_address=request.client.host if request.client else None,
            ))
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Security violation: Token replay detected. Session terminated across devices.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Check token expiration
    now = datetime.now(timezone.utc)
    if _to_utc(token_record.expires_at) < now:
        token_record.is_revoked = True
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = token_record.user
    if not user or not user.is_active:
        token_record.is_revoked = True
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Rotate token: Revoke current token and generate next token in same family
    token_record.is_revoked = True

    new_raw_token = generate_refresh_token()
    new_token_hash = hash_token(new_raw_token)
    new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    new_refresh_token_record = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=new_token_hash,
        family_id=token_record.family_id,  # Maintains family lineage
        is_revoked=False,
        expires_at=new_expires_at,
        ip_address=client_ip,
        user_agent=user_agent[:500] if user_agent else None,
    )
    db.add(new_refresh_token_record)

    # 4. Issue new JWT access token
    new_access_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )

    await db.commit()

    # 5. Set rotated cookie
    _set_refresh_cookie(response, new_raw_token)

    user_response = UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=str(user.organization_id),
        organization_name=user.organization.name if user.organization else None,
        is_active=user.is_active,
    )

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response,
        refresh_token=new_raw_token,
    )


@router.post(
    "/logout",
    response_model=AuthMessageResponse,
    summary="Revoke active refresh token and end session",
)
async def logout(
    request: Request,
    response: Response,
    db: DatabaseDep,
    payload: Optional[TokenRefreshRequest] = None,
    cookie_token: Optional[str] = Cookie(None, alias="refresh_token"),
) -> AuthMessageResponse:
    """
    Revokes the current refresh token and its family, clears browser cookies,
    and records an audit log.
    """
    raw_token = (payload.refresh_token if payload and payload.refresh_token else None) or cookie_token

    if raw_token:
        token_hash_val = hash_token(raw_token)
        stmt = (
            select(RefreshToken)
            .options(selectinload(RefreshToken.user))
            .where(RefreshToken.token_hash == token_hash_val)
        )
        result = await db.execute(stmt)
        token_record = result.scalar_one_or_none()
        if token_record:
            # Revoke entire family for this session
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token_record.family_id)
                .values(is_revoked=True)
            )
            org_id = token_record.user.organization_id if token_record.user else None
            if not org_id:
                u_res = await db.execute(select(User).where(User.id == token_record.user_id))
                u_rec = u_res.scalar_one_or_none()
                if u_rec:
                    org_id = u_rec.organization_id

            if org_id:
                db.add(AuditLog(
                    organization_id=org_id,
                    user_id=token_record.user_id,
                    action="user_logout",
                    resource_type="refresh_token",
                    resource_id=str(token_record.id),
                    details=f"User session terminated. Family {token_record.family_id} revoked.",
                    ip_address=request.client.host if request.client else None,
                ))
            await db.commit()

    _clear_refresh_cookie(response)

    return AuthMessageResponse(
        message="Logged out successfully. Session revoked.",
        status="success",
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retrieve authenticated user profile",
)
async def get_me(
    user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Returns profile information of currently authenticated user.
    """
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=str(user.organization_id),
        organization_name=user.organization.name if user.organization else None,
        is_active=user.is_active,
    )


@router.post(
    "/forgot-password",
    response_model=AuthMessageResponse,
    summary="Request password reset instructions",
    dependencies=[Depends(check_auth_rate_limit)],
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: DatabaseDep,
) -> AuthMessageResponse:
    """
    Initiates password recovery.
    Always returns generic success message regardless of whether the email exists,
    preventing user enumeration.
    """
    normalized_email = payload.email.lower().strip()

    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user and user.is_active:
        # Generate token, hash and persist with 15-minute expiration
        raw_token = generate_password_reset_token()
        token_hash_val = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        reset_record = PasswordReset(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash_val,
            is_used=False,
            expires_at=expires_at,
        )
        db.add(reset_record)

        db.add(AuditLog(
            organization_id=user.organization_id,
            user_id=user.id,
            action="password_reset_requested",
            resource_type="user",
            resource_id=str(user.id),
            details=f"Password reset token issued for {user.email}.",
            ip_address=request.client.host if request.client else None,
        ))
        await db.commit()

        # In dev/test environments, log token for test inspection
        if settings.APP_ENV in ("development", "test"):
            logger.info("DEV/TEST Password reset token for %s: %s", user.email, raw_token)

    return AuthMessageResponse(
        message="If an account with that email exists, password reset instructions have been generated.",
        status="success",
    )


@router.post(
    "/reset-password",
    response_model=AuthMessageResponse,
    summary="Reset password using one-time token",
    dependencies=[Depends(check_auth_rate_limit)],
)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: DatabaseDep,
) -> AuthMessageResponse:
    """
    Verifies password reset token, updates user password using Argon2id,
    marks token used, and terminates all existing refresh sessions.
    """
    token_hash_val = hash_token(payload.token)

    stmt = select(PasswordReset).options(selectinload(PasswordReset.user)).where(PasswordReset.token_hash == token_hash_val)
    result = await db.execute(stmt)
    reset_record = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not reset_record or reset_record.is_used or _to_utc(reset_record.expires_at) < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already utilized password reset token.",
        )

    user = reset_record.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User associated with this reset token was not found.",
        )

    # 1. Update user password
    user.hashed_password = get_password_hash(payload.new_password)

    # 2. Mark reset token as used
    reset_record.is_used = True

    # 3. Security: Revoke all existing refresh sessions for this user (force re-login everywhere)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .values(is_revoked=True)
    )

    # 4. Audit log
    db.add(AuditLog(
        organization_id=user.organization_id,
        user_id=user.id,
        action="password_reset_completed",
        resource_type="user",
        resource_id=str(user.id),
        details=f"Password reset successfully completed for {user.email}. All sessions revoked.",
        ip_address=request.client.host if request.client else None,
    ))

    await db.commit()

    return AuthMessageResponse(
        message="Your password has been reset successfully. Please log in with your new credentials.",
        status="success",
    )
