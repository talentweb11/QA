from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from functools import lru_cache


from flask import Blueprint, current_app, g, jsonify, make_response, request

from app.extensions import db
from app.middleware.auth import require_auth
from app.models import PasswordResetToken, Role, Session, User
from app.services.audit import log_event
from app.services.mail import send_password_reset_email, send_verification_email
from app.utils.crypto import (
    generate_secure_token,
    generate_totp_secret,
    get_totp_provisioning_uri,
    hash_password,
    validate_password_complexity,
    verify_password,
    verify_totp_code,
)
from app.utils.encryption import encrypt_field
from app.utils.request_meta import client_ip, user_agent
from app import limiter
from app.middleware.csrf import generate_csrf_token

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# FR-01: POST /api/auth/login (step 1)
# FR-01: POST /api/auth/login/mfa (step 2)
# FR-01: POST /api/auth/logout
# FR-01: GET  /api/auth/me
# FR-01: POST /api/auth/mfa/setup
# FR-01: POST /api/auth/mfa/enable
# FR-01: POST /api/auth/mfa/disable
# SR-22: GET /api/auth/csrf
# FR-02: POST /api/auth/register
# FR-02: GET  /api/auth/verify-email
# FR-14: POST /api/auth/password-reset/request
# FR-14: POST /api/auth/password-reset/confirm

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_EMAIL_VERIFY_EXPIRY_HOURS = 24
_PASSWORD_RESET_EXPIRY_MINUTES = 15
_SESSION_EXPIRY_HOURS = 8
_MFA_CHALLENGE_EXPIRY_MINUTES = 5
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 10


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # Computed once on first call so verify_password always runs bcrypt
    # even when no user matches the submitted email (timing attack prevention).
    return hash_password('fintrack-timing-sentinel-not-a-real-password')


def _create_session(user_id, duration: timedelta) -> tuple[str, Session]:
    raw_token, token_hash = generate_secure_token()
    session = Session(
        user_id=user_id,
        token_hash=token_hash,
        ip_address=client_ip(),
        expires_at=datetime.utcnow() + duration,
    )
    db.session.add(session)
    return raw_token, session


def _set_cookie(response, raw_token: str, expires_at: datetime):
    response.set_cookie(
        'session_token',
        raw_token,
        httponly=True,
        secure=not current_app.debug,
        # SameSite=None requires Secure; over local HTTP (debug) the browser drops
        # such cookies, so use Lax locally (same-origin via Vite proxy) and None in prod
        # (cross-site: Vercel frontend -> EC2 backend).
        samesite='Lax' if current_app.debug else 'None',
        path='/',
        expires=expires_at,
    )
    return response


# ---------------------------------------------------------------------------
# FR-02: Registration
# ---------------------------------------------------------------------------

@auth_bp.post('/register')
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    display_name = (data.get('display_name') or '').strip()

    if not email or not _EMAIL_RE.match(email):
        return jsonify({'error': 'Invalid email address'}), 400
    if not display_name:
        return jsonify({'error': 'Display name is required'}), 400

    valid, reason = validate_password_complexity(password)
    if not valid:
        return jsonify({'error': reason}), 400

    # Generic response used for both success and duplicate — prevents email enumeration
    _generic = {'message': 'If this email is not already registered, a verification link has been sent.'}

    if User.query.filter_by(email=email).first():
        return jsonify(_generic), 201

    individual_role = Role.query.filter_by(role_name='INDIVIDUAL').first()
    if not individual_role:
        current_app.logger.error('INDIVIDUAL role missing from roles table')
        return jsonify({'error': 'Server configuration error'}), 500

    raw_token, token_hash = generate_secure_token()
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        status='PENDING',
        email_verification_token_hash=token_hash,
        email_verification_expires_at=datetime.utcnow() + timedelta(hours=_EMAIL_VERIFY_EXPIRY_HOURS),
    )
    user.roles.append(individual_role)  # every account gets INDIVIDUAL as its base role
    db.session.add(user)
    db.session.commit()

    try:
        send_verification_email(email, display_name, raw_token)
    except Exception:
        current_app.logger.exception('Failed to send verification email to %s', email)

    log_event('USER_REGISTERED', 'SUCCESS', client_ip(), user_id=user.id, user_agent=user_agent())
    return jsonify(_generic), 201


# ---------------------------------------------------------------------------
# FR-02: Email verification
# ---------------------------------------------------------------------------

@auth_bp.get('/verify-email')
def verify_email():
    raw_token = request.args.get('token', '')
    if not raw_token:
        return jsonify({'error': 'Token is required'}), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    user = User.query.filter_by(email_verification_token_hash=token_hash).first()

    if not user or not user.email_verification_expires_at or \
            user.email_verification_expires_at < datetime.utcnow():
        return jsonify({'error': 'Invalid or expired verification link'}), 400

    user.status = 'ACTIVE'
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    db.session.commit()

    log_event('EMAIL_VERIFIED', 'SUCCESS', client_ip(), user_id=user.id, user_agent=user_agent())
    return jsonify({'message': 'Email verified. You may now log in.'}), 200


# ---------------------------------------------------------------------------
# FR-09: Accept a household invitation — set password + activate the account
# ---------------------------------------------------------------------------

@auth_bp.post('/accept-invite')
@limiter.limit('10 per hour')
def accept_invite():
    data = request.get_json(silent=True) or {}
    raw_token = data.get('token') or ''
    password = data.get('password') or ''
    display_name = (data.get('display_name') or '').strip()

    if not raw_token:
        return jsonify({'error': 'Token is required'}), 400
    if not display_name:
        return jsonify({'error': 'Display name is required'}), 400

    valid, reason = validate_password_complexity(password)
    if not valid:
        return jsonify({'error': reason}), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    user = User.query.filter_by(email_verification_token_hash=token_hash).first()

    if not user or user.status != 'PENDING' or not user.email_verification_expires_at \
            or user.email_verification_expires_at < datetime.utcnow():
        return jsonify({'error': 'Invalid or expired invitation link'}), 400

    user.password_hash = hash_password(password)
    user.display_name = display_name
    user.status = 'ACTIVE'
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None

    # Ensure the INDIVIDUAL base role is present. The specialized role
    # (HOUSEHOLD or ADVISOR) was assigned when the invite was created.
    if not user.has_role('INDIVIDUAL'):
        role = Role.query.filter_by(role_name='INDIVIDUAL').first()
        if role is not None:
            user.roles.append(role)

    db.session.commit()

    log_event('EMAIL_VERIFIED', 'SUCCESS', client_ip(), user_id=user.id, user_agent=user_agent())
    return jsonify({'message': 'Account created. You may now log in.'}), 200


# ---------------------------------------------------------------------------
# FR-01 / SR-09: Login — step 1 (password)
# ---------------------------------------------------------------------------

@auth_bp.post('/login')
@limiter.limit('10 per minute')
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    ip, ua = client_ip(), user_agent()

    user = User.query.filter_by(email=email).first()

    # Lockout check before expensive bcrypt call
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        log_event('AUTH_FAILURE', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Account temporarily locked. Try again later.'}), 403

    # Always call verify_password to prevent timing attacks when user not found
    pw_hash = user.password_hash if user else _dummy_hash()
    password_ok = verify_password(password, pw_hash)

    if not user or not password_ok or user.status != 'ACTIVE':
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= _MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=_LOCKOUT_MINUTES)
            db.session.commit()
        log_event('AUTH_FAILURE', 'FAILURE', ip, user_id=user.id if user else None, user_agent=ua)
        return jsonify({'error': 'Invalid credentials or account not active'}), 401

    # Password verified — reset failed attempt counters
    user.failed_login_attempts = 0
    user.locked_until = None

    if user.mfa_enabled:
        challenge_token, challenge_session = _create_session(
            user.id, timedelta(minutes=_MFA_CHALLENGE_EXPIRY_MINUTES)
        )
        db.session.commit()
        return jsonify({'mfa_required': True, 'session_challenge': challenge_token}), 200

    raw_token, session = _create_session(user.id, timedelta(hours=_SESSION_EXPIRY_HOURS))
    db.session.commit()
    log_event('AUTH_SUCCESS', 'SUCCESS', ip, user_id=user.id, resource_id=session.id, user_agent=ua)

    resp = make_response(jsonify({'message': 'Login successful'}), 200)
    return _set_cookie(resp, raw_token, session.expires_at)


# ---------------------------------------------------------------------------
# FR-01 / SR-11: Login — step 2 (TOTP MFA)
# ---------------------------------------------------------------------------

@auth_bp.post('/login/mfa')
def login_mfa():
    data = request.get_json(silent=True) or {}
    challenge_token = data.get('session_challenge') or ''
    totp_code = data.get('totp_code') or ''
    ip, ua = client_ip(), user_agent()

    if not challenge_token or not totp_code:
        return jsonify({'error': 'session_challenge and totp_code are required'}), 400

    challenge_hash = hashlib.sha256(challenge_token.encode()).hexdigest()
    challenge = Session.query.filter_by(token_hash=challenge_hash).first()

    if not challenge or challenge.expires_at < datetime.utcnow():
        return jsonify({'error': 'Invalid or expired MFA challenge'}), 401

    user = challenge.user
    if not user or user.status != 'ACTIVE' or not user.mfa_enabled or not user.totp_secret:
        db.session.delete(challenge)
        db.session.commit()
        return jsonify({'error': 'Invalid MFA state'}), 401

    if not verify_totp_code(user.totp_secret, totp_code):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= _MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=_LOCKOUT_MINUTES)
        db.session.delete(challenge)
        db.session.commit()
        log_event('MFA_FAILURE', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Invalid TOTP code'}), 401

    # MFA passed — promote challenge to a full session
    db.session.delete(challenge)
    user.failed_login_attempts = 0
    user.locked_until = None
    raw_token, session = _create_session(user.id, timedelta(hours=_SESSION_EXPIRY_HOURS))
    db.session.commit()
    log_event('AUTH_SUCCESS', 'SUCCESS', ip, user_id=user.id, resource_id=session.id, user_agent=ua)

    resp = make_response(jsonify({'message': 'Login successful'}), 200)
    return _set_cookie(resp, raw_token, session.expires_at)


# ---------------------------------------------------------------------------
# FR-01 / SR-19: Logout
# ---------------------------------------------------------------------------

@auth_bp.post('/logout')
@require_auth
def logout():
    db.session.delete(g.session)
    db.session.commit()
    log_event('LOGOUT', 'SUCCESS', client_ip(), user_id=g.current_user.id, user_agent=user_agent())

    resp = make_response(jsonify({'message': 'Logged out'}), 200)
    resp.set_cookie(
        'session_token', '',
        expires=0, httponly=True,
        secure=not current_app.debug,
        samesite='Lax' if current_app.debug else 'None', path='/',
    )
    return resp


# ---------------------------------------------------------------------------
# FR-01: Current user
# ---------------------------------------------------------------------------

@auth_bp.get('/me')
@require_auth
def me():
    user = g.current_user
    return jsonify({
        'id': str(user.id),
        'email': user.email,
        'display_name': user.display_name,
        'roles': sorted(user.role_names),
        'mfa_enabled': user.mfa_enabled,
        'status': user.status,
    }), 200


@auth_bp.get('/csrf')
@require_auth
def csrf_token():
    raw_token = request.cookies.get('session_token', '')
    return jsonify({'csrf_token': generate_csrf_token(raw_token)}), 200


# ---------------------------------------------------------------------------
# FR-14 / SR-12: Password reset — request
# ---------------------------------------------------------------------------

@auth_bp.post('/password-reset/request')
@limiter.limit('5 per minute')
def password_reset_request():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    ip, ua = client_ip(), user_agent()

    # Always return the same response regardless of whether the email exists
    _generic = jsonify({'message': 'If this email is registered, a reset link has been sent.'})

    if not email or not _EMAIL_RE.match(email):
        return _generic, 200

    user = User.query.filter_by(email=email).first()
    if not user or user.status != 'ACTIVE':
        return _generic, 200

    raw_token, token_hash = generate_secure_token()
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(minutes=_PASSWORD_RESET_EXPIRY_MINUTES),
    )
    db.session.add(reset_token)
    db.session.commit()

    try:
        send_password_reset_email(email, user.display_name, raw_token)
    except Exception:
        current_app.logger.exception('Failed to send reset email to %s', email)

    log_event('PASSWORD_RESET_REQUESTED', 'SUCCESS', ip, user_id=user.id, user_agent=ua)
    return _generic, 200


# ---------------------------------------------------------------------------
# FR-14 / SR-12: Password reset — confirm
# ---------------------------------------------------------------------------

@auth_bp.post('/password-reset/confirm')
def password_reset_confirm():
    data = request.get_json(silent=True) or {}
    raw_token = data.get('token') or ''
    new_password = data.get('new_password') or ''
    ip, ua = client_ip(), user_agent()

    if not raw_token or not new_password:
        return jsonify({'error': 'token and new_password are required'}), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    reset_token = PasswordResetToken.query.filter_by(token_hash=token_hash).first()

    if not reset_token or reset_token.used_at or reset_token.expires_at < datetime.utcnow():
        return jsonify({'error': 'Invalid or expired reset token'}), 400

    valid, reason = validate_password_complexity(new_password)
    if not valid:
        return jsonify({'error': reason}), 400

    user = reset_token.user
    user.password_hash = hash_password(new_password)
    reset_token.used_at = datetime.utcnow()
    # Invalidate all existing sessions on password change
    Session.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    log_event('PASSWORD_RESET_USED', 'SUCCESS', ip, user_id=user.id, user_agent=ua)
    return jsonify({'message': 'Password updated. Please log in again.'}), 200


# ---------------------------------------------------------------------------
# FR-01 / SR-11: MFA setup — generate secret and QR URI
# ---------------------------------------------------------------------------

@auth_bp.post('/mfa/setup')
@require_auth
def mfa_setup():
    user = g.current_user

    if user.mfa_enabled:
        return jsonify({'error': 'MFA already enabled. Disable it first to reconfigure.'}), 400

    secret = generate_totp_secret()
    user.totp_secret = encrypt_field(secret)
    db.session.commit()

    uri = get_totp_provisioning_uri(user.email, secret)
    log_event('MFA_SETUP_INITIATED', 'SUCCESS', client_ip(), user_id=user.id, user_agent=user_agent())
    return jsonify({'qr_uri': uri}), 200


# ---------------------------------------------------------------------------
# FR-01 / SR-11: MFA enable — verify first TOTP code
# ---------------------------------------------------------------------------

@auth_bp.post('/mfa/enable')
@require_auth
def mfa_enable():
    data = request.get_json(silent=True) or {}
    totp_code = data.get('totp_code') or ''
    user = g.current_user
    ip, ua = client_ip(), user_agent()

    if not user.totp_secret:
        return jsonify({'error': 'Run /mfa/setup first'}), 400

    if not verify_totp_code(user.totp_secret, totp_code):
        log_event('MFA_ENABLE_FAILED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Invalid TOTP code'}), 400

    user.mfa_enabled = True
    db.session.commit()
    log_event('MFA_ENABLED', 'SUCCESS', ip, user_id=user.id, user_agent=ua)
    return jsonify({'message': 'MFA enabled'}), 200


# ---------------------------------------------------------------------------
# FR-01: MFA disable — require current TOTP code to confirm
# ---------------------------------------------------------------------------

@auth_bp.post('/mfa/disable')
@require_auth
def mfa_disable():
    data = request.get_json(silent=True) or {}
    totp_code = data.get('totp_code') or ''
    user = g.current_user
    ip, ua = client_ip(), user_agent()

    if not user.mfa_enabled or not user.totp_secret:
        return jsonify({'error': 'MFA is not enabled'}), 400

    if not verify_totp_code(user.totp_secret, totp_code):
        log_event('MFA_DISABLE_FAILED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Invalid TOTP code'}), 400

    user.mfa_enabled = False
    user.totp_secret = None
    db.session.commit()
    log_event('MFA_DISABLED', 'SUCCESS', ip, user_id=user.id, user_agent=ua)
    return jsonify({'message': 'MFA disabled'}), 200
