from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_

from app import limiter
from app.extensions import db
from app.middleware.auth import assert_owns_resource, require_auth, require_role
from app.models import Consent, Role, User
from app.services.analytics import full_analytics, household_summary
from app.services.audit import log_event
from app.services.consent import get_valid_consent
from app.services.mail import send_consent_notification, send_invitation
from app.utils.crypto import generate_secure_token, hash_password
from app.utils.request_meta import client_ip, user_agent

consents_bp = Blueprint('consents', __name__, url_prefix='/api')

# FR-09: POST   /api/consents/household        [implemented below]
# FR-09: DELETE /api/consents/household/:id    [implemented below]
# FR-10: POST   /api/consents/advisor          [implemented below]
# FR-10: DELETE /api/consents/advisor/:id       [implemented below]
# FR-15: GET    /api/household/summary         [implemented below]
# FR-16: GET    /api/advisor/clients           [implemented below]
# FR-16: GET    /api/advisor/clients/:grantor_id/analytics   [implemented below]

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# Advisor (FULL_VIEW) consents expire after this many days (FR-10).
_ADVISOR_CONSENT_DAYS = 90


def _serialize_consent(consent: Consent) -> dict:
    """Response shape for a consent. Never exposes anything sensitive."""
    grantee = consent.grantee
    return {
        'id': str(consent.id),
        'grantee_id': str(consent.grantee_id),
        'grantee_email': grantee.email if grantee else None,
        'grantee_display_name': grantee.display_name if grantee else None,
        'grantee_status': grantee.status if grantee else None,
        'access_level': consent.access_level,
        'status': consent.status,
        'created_at': consent.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Shared grant flow — used by household (SUMMARY_ONLY) and advisor (FULL_VIEW)
# ---------------------------------------------------------------------------

def _grant_consent(grantee_role: str, access_level: str, expires_at):
    """Grant `access_level` from the current individual to an ACTIVE user with
    role `grantee_role`. Reactivates a revoked row for the pair (respecting
    UNIQUE(grantor, grantee)) so re-granting restores access.
    """
    grantor = g.current_user
    ip, ua = client_ip(), user_agent()

    data = request.get_json(silent=True) or {}
    grantee_email = (data.get('grantee_email') or '').strip().lower()

    if not grantee_email or not _EMAIL_RE.match(grantee_email):
        return jsonify({'error': 'A valid grantee_email is required'}), 400

    # Cannot grant access to yourself.
    if grantee_email == (grantor.email or '').lower():
        log_event('CONSENT_GRANTED', 'FAILURE', ip, user_id=grantor.id, user_agent=ua)
        return jsonify({'error': 'You cannot grant access to yourself'}), 400

    grantee = User.query.filter_by(email=grantee_email).first()
    if grantee is None or grantee.status != 'ACTIVE' or not grantee.has_role(grantee_role):
        log_event('CONSENT_GRANTED', 'FAILURE', ip, user_id=grantor.id, user_agent=ua)
        return jsonify({'error': f'No active {grantee_role.lower()} user found with that email'}), 404

    # UNIQUE(grantor_id, grantee_id) means at most one row per pair. Reuse it so
    # that re-granting after a revoke restores access instead of hitting the
    # unique constraint.
    existing = Consent.query.filter_by(
        grantor_id=grantor.id, grantee_id=grantee.id,
    ).first()

    if existing is not None:
        if existing.access_level != access_level:
            log_event('CONSENT_GRANTED', 'FAILURE', ip, user_id=grantor.id,
                      resource_id=existing.id, user_agent=ua)
            return jsonify({'error': 'A different consent already exists for this user'}), 409
        if existing.status == 'ACTIVE':
            return jsonify({'error': 'Access is already granted to this user'}), 409
        existing.status = 'ACTIVE'
        existing.expires_at = expires_at
        existing.updated_at = datetime.utcnow()
        consent = existing
    else:
        consent = Consent(
            grantor_id=grantor.id,
            grantee_id=grantee.id,
            access_level=access_level,
            status='ACTIVE',
            expires_at=expires_at,
        )
        db.session.add(consent)

    db.session.commit()

    log_event('CONSENT_GRANTED', 'SUCCESS', ip, user_id=grantor.id,
              resource_id=consent.id, user_agent=ua)

    try:
        send_consent_notification(
            grantee.email, grantee.display_name, grantor.display_name, access_level,
        )
    except Exception:
        current_app.logger.exception('Failed to send consent notification to %s', grantee.email)

    return jsonify(_serialize_consent(consent)), 201


# ---------------------------------------------------------------------------
# FR-09 / SR-14: Grant a HOUSEHOLD member summary access to my finances
# ---------------------------------------------------------------------------

@consents_bp.post('/consents/household')
@require_auth
@require_role('INDIVIDUAL')
def grant_household_consent():
    return _grant_consent('HOUSEHOLD', 'SUMMARY_ONLY', expires_at=None)


# ---------------------------------------------------------------------------
# FR-09: List the household members I've granted summary access to
# ---------------------------------------------------------------------------

@consents_bp.get('/consents/household')
@require_auth
@require_role('INDIVIDUAL')
def list_household_consents():
    grantor = g.current_user
    consents = (
        Consent.query.filter(
            Consent.grantor_id == grantor.id,
            Consent.access_level == 'SUMMARY_ONLY',
            Consent.status == 'ACTIVE',
        ).all()
    )
    return jsonify({'shares': [_serialize_consent(c) for c in consents]}), 200


# ---------------------------------------------------------------------------
# FR-09 / FR-10: Invite a member by email (they may not have an account yet).
# Shared by household (SUMMARY_ONLY) and advisor (FULL_VIEW).
# ---------------------------------------------------------------------------

# Invited accounts are claimed via an emailed link within this window.
_INVITE_EXPIRY_DAYS = 7


def _upsert_consent(grantor_id, grantee_id, access_level, expires_at):
    """Create or reactivate a consent of `access_level` for (grantor, grantee).

    Returns the consent, or None if a *different* access-level consent already
    exists for the pair — respecting the unique (grantor_id, grantee_id) constraint.
    """
    existing = Consent.query.filter_by(grantor_id=grantor_id, grantee_id=grantee_id).first()
    if existing is not None:
        if existing.access_level != access_level:
            return None
        existing.status = 'ACTIVE'
        existing.expires_at = expires_at
        existing.updated_at = datetime.utcnow()
        return existing

    consent = Consent(
        grantor_id=grantor_id, grantee_id=grantee_id,
        access_level=access_level, status='ACTIVE', expires_at=expires_at,
    )
    db.session.add(consent)
    return consent


def _invite_member(specialized_role_name: str, access_level: str, expires_at):
    """Invite someone (by email) to be a household member or advisor.

    New people are pre-created as PENDING with INDIVIDUAL + the specialized role
    and claim the account via an emailed link. Inviting an existing active
    account adds the role and shares immediately.
    """
    grantor = g.current_user
    ip, ua = client_ip(), user_agent()

    data = request.get_json(silent=True) or {}
    email = (data.get('grantee_email') or '').strip().lower()

    if not email or not _EMAIL_RE.match(email):
        return jsonify({'error': 'A valid grantee_email is required'}), 400
    if email == (grantor.email or '').lower():
        return jsonify({'error': 'You cannot invite yourself'}), 400

    specialized_role = Role.query.filter_by(role_name=specialized_role_name).first()
    individual_role = Role.query.filter_by(role_name='INDIVIDUAL').first()
    if specialized_role is None or individual_role is None:
        current_app.logger.error('%s/INDIVIDUAL role missing from roles table', specialized_role_name)
        return jsonify({'error': 'Server configuration error'}), 500

    grantee = User.query.filter_by(email=email).first()

    # --- Brand-new person: pre-create a PENDING account they claim via email ---
    if grantee is None:
        raw_token, token_hash = generate_secure_token()
        grantee = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable until they set one
            display_name=email.split('@')[0],
            status='PENDING',
            email_verification_token_hash=token_hash,
            email_verification_expires_at=datetime.utcnow() + timedelta(days=_INVITE_EXPIRY_DAYS),
        )
        grantee.roles.append(individual_role)
        grantee.roles.append(specialized_role)
        db.session.add(grantee)
        db.session.flush()  # assign grantee.id for the consent FK
        _upsert_consent(grantor.id, grantee.id, access_level, expires_at)
        db.session.commit()

        try:
            send_invitation(email, grantor.display_name, raw_token, access_level)
        except Exception:
            current_app.logger.exception('Failed to send invitation to %s', email)

        log_event('CONSENT_GRANTED', 'SUCCESS', ip, user_id=grantor.id,
                  resource_id=grantee.id, user_agent=ua)
        return jsonify({'status': 'INVITED', 'grantee_email': email}), 201

    if grantee.status == 'SUSPENDED':
        log_event('CONSENT_GRANTED', 'FAILURE', ip, user_id=grantor.id, user_agent=ua)
        return jsonify({'error': 'That account cannot be invited'}), 409

    # --- Previously invited / unverified: (re)send the invitation ---
    if grantee.status == 'PENDING':
        raw_token, token_hash = generate_secure_token()
        grantee.email_verification_token_hash = token_hash
        grantee.email_verification_expires_at = datetime.utcnow() + timedelta(days=_INVITE_EXPIRY_DAYS)
        if not grantee.has_role(specialized_role_name):
            grantee.roles.append(specialized_role)
        if _upsert_consent(grantor.id, grantee.id, access_level, expires_at) is None:
            return jsonify({'error': 'A different consent already exists for this user'}), 409
        db.session.commit()

        try:
            send_invitation(email, grantor.display_name, raw_token, access_level)
        except Exception:
            current_app.logger.exception('Failed to resend invitation to %s', email)

        log_event('CONSENT_GRANTED', 'SUCCESS', ip, user_id=grantor.id,
                  resource_id=grantee.id, user_agent=ua)
        return jsonify({'status': 'INVITED', 'grantee_email': email}), 201

    # --- Existing ACTIVE account: add the role + share immediately ---
    consent = _upsert_consent(grantor.id, grantee.id, access_level, expires_at)
    if consent is None:
        return jsonify({'error': 'A different consent already exists for this user'}), 409
    if not grantee.has_role(specialized_role_name):
        grantee.roles.append(specialized_role)
    db.session.commit()

    try:
        send_consent_notification(
            grantee.email, grantee.display_name, grantor.display_name, access_level,
        )
    except Exception:
        current_app.logger.exception('Failed to send consent notification to %s', grantee.email)

    log_event('CONSENT_GRANTED', 'SUCCESS', ip, user_id=grantor.id,
              resource_id=consent.id, user_agent=ua)
    return jsonify({'status': 'SHARED', 'grantee_email': email}), 201


@consents_bp.post('/consents/household/invite')
@limiter.limit('10 per hour')
@require_auth
@require_role('INDIVIDUAL')
def invite_household_member():
    return _invite_member('HOUSEHOLD', 'SUMMARY_ONLY', expires_at=None)


@consents_bp.post('/consents/advisor/invite')
@limiter.limit('10 per hour')
@require_auth
@require_role('INDIVIDUAL')
def invite_advisor_member():
    expires_at = datetime.utcnow() + timedelta(days=_ADVISOR_CONSENT_DAYS)
    return _invite_member('ADVISOR', 'FULL_VIEW', expires_at=expires_at)


@consents_bp.get('/consents/advisor')
@require_auth
@require_role('INDIVIDUAL')
def list_advisor_consents():
    grantor = g.current_user
    consents = (
        Consent.query.filter(
            Consent.grantor_id == grantor.id,
            Consent.access_level == 'FULL_VIEW',
            Consent.status == 'ACTIVE',
        ).all()
    )
    return jsonify({'shares': [_serialize_consent(c) for c in consents]}), 200


# ---------------------------------------------------------------------------
# FR-10 / SR-14: Grant an ADVISOR full view of my finances (expires in 90 days)
# ---------------------------------------------------------------------------

@consents_bp.post('/consents/advisor')
@require_auth
@require_role('INDIVIDUAL')
def grant_advisor_consent():
    expires_at = datetime.utcnow() + timedelta(days=_ADVISOR_CONSENT_DAYS)
    return _grant_consent('ADVISOR', 'FULL_VIEW', expires_at=expires_at)


# ---------------------------------------------------------------------------
# Shared revoke flow — used by household (SUMMARY_ONLY) and advisor (FULL_VIEW)
# ---------------------------------------------------------------------------

def _revoke_consent(consent_id: str, access_level: str):
    """Soft-delete the grantor's own consent of the given `access_level`.

    The row is kept (status -> REVOKED) so a later re-grant can reactivate it.
    """
    grantor = g.current_user
    ip, ua = client_ip(), user_agent()

    # Malformed id -> 404 (never reveals existence).
    try:
        cid = uuid.UUID(consent_id)
    except ValueError:
        return jsonify({'error': 'consent not found'}), 404

    consent = Consent.query.filter_by(id=cid).first()
    if consent is None:
        return jsonify({'error': 'consent not found'}), 404

    # Ownership: only the grantor may revoke. 403 if it belongs to someone else
    # (matches the devplan IDOR expectation and Owen's Phase 6 helper).
    assert_owns_resource(consent.grantor_id)

    # Each revoke route only handles its own consent type; the other type 404s
    # so the household and advisor routes stay cleanly separated.
    if consent.access_level != access_level:
        return jsonify({'error': 'consent not found'}), 404

    # Idempotent: re-revoking an already-revoked consent is a no-op (no new audit).
    if consent.status == 'REVOKED':
        return jsonify(_serialize_consent(consent)), 200

    consent.status = 'REVOKED'
    consent.updated_at = datetime.utcnow()
    db.session.commit()

    log_event('CONSENT_REVOKED', 'SUCCESS', ip, user_id=grantor.id,
              resource_id=consent.id, user_agent=ua)

    return jsonify(_serialize_consent(consent)), 200


# ---------------------------------------------------------------------------
# FR-09: Revoke a HOUSEHOLD member's summary access (soft delete)
# ---------------------------------------------------------------------------

@consents_bp.delete('/consents/household/<consent_id>')
@require_auth
def revoke_household_consent(consent_id):
    return _revoke_consent(consent_id, 'SUMMARY_ONLY')


# ---------------------------------------------------------------------------
# FR-10: Revoke an ADVISOR's full-view access (soft delete)
# ---------------------------------------------------------------------------

@consents_bp.delete('/consents/advisor/<consent_id>')
@require_auth
def revoke_advisor_consent(consent_id):
    return _revoke_consent(consent_id, 'FULL_VIEW')


# ---------------------------------------------------------------------------
# FR-15 / SR-14: Household member views aggregated summaries shared with them
# ---------------------------------------------------------------------------

@consents_bp.get('/household/summary')
@require_auth
@require_role('HOUSEHOLD')
def household_summary_view():
    member = g.current_user
    ip, ua = client_ip(), user_agent()

    consents = (
        Consent.query.filter(
            Consent.grantee_id == member.id,
            Consent.status == 'ACTIVE',
            Consent.access_level == 'SUMMARY_ONLY',
            or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.utcnow()),
        ).all()
    )

    summaries = []
    for consent in consents:
        # Defense-in-depth: re-validate the consent before exposing any data,
        # in case it was revoked between the query above and now (SR-14).
        if get_valid_consent(consent.grantor_id, member.id) is None:
            continue
        grantor = consent.grantor
        data = household_summary(consent.grantor_id)
        summaries.append({
            'grantor_id': str(consent.grantor_id),
            'grantor_display_name': grantor.display_name if grantor else None,
            'spending_by_category': data['spending_by_category'],
            'monthly_trend': data['monthly_trend'],
        })

    log_event('HOUSEHOLD_SUMMARY_ACCESS', 'SUCCESS', ip, user_id=member.id, user_agent=ua)

    return jsonify({'grantors': summaries}), 200


# ---------------------------------------------------------------------------
# FR-16: Advisor lists their clients (individuals granting FULL_VIEW to them)
# ---------------------------------------------------------------------------

@consents_bp.get('/advisor/clients')
@require_auth
@require_role('ADVISOR')
def advisor_clients():
    advisor = g.current_user

    consents = (
        Consent.query.filter(
            Consent.grantee_id == advisor.id,
            Consent.status == 'ACTIVE',
            Consent.access_level == 'FULL_VIEW',
            or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.utcnow()),
        ).all()
    )

    # Names only — no email, no financial data.
    clients = [
        {
            'grantor_id': str(consent.grantor_id),
            'display_name': consent.grantor.display_name if consent.grantor else None,
        }
        for consent in consents
    ]

    return jsonify({'clients': clients}), 200


# ---------------------------------------------------------------------------
# FR-16 / SR-14: Advisor views one client's full analytics (consent-gated)
# ---------------------------------------------------------------------------

@consents_bp.get('/advisor/clients/<grantor_id>/analytics')
@require_auth
@require_role('ADVISOR')
def advisor_client_analytics(grantor_id):
    advisor = g.current_user
    ip, ua = client_ip(), user_agent()

    # Uniform 403 for a malformed id or any missing/insufficient consent, so an
    # advisor cannot probe which client ids exist.
    try:
        grantor_uuid = uuid.UUID(grantor_id)
    except ValueError:
        return jsonify({'error': 'Forbidden'}), 403

    consent = get_valid_consent(grantor_uuid, advisor.id)
    if consent is None or consent.access_level != 'FULL_VIEW':
        return jsonify({'error': 'Forbidden'}), 403

    log_event('ADVISOR_DATA_ACCESS', 'SUCCESS', ip, user_id=advisor.id,
              resource_id=grantor_uuid, user_agent=ua)

    grantor = consent.grantor
    return jsonify({
        'grantor_id': str(grantor_uuid),
        'display_name': grantor.display_name if grantor else None,
        'analytics': full_analytics(grantor_uuid),
    }), 200
