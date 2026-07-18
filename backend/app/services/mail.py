from __future__ import annotations

import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


def _send(to_email: str, subject: str, html_body: str) -> None:
    server = current_app.config.get('MAIL_SERVER')
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')

    if not all([server, username, password]):
        current_app.logger.warning('Mail not configured — skipping send to %s: %s', to_email, subject)
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = username
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html'))

    with smtplib.SMTP(server, 587) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(username, to_email, msg.as_string())


def send_verification_email(to_email: str, display_name: str, raw_token: str) -> None:
    frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:5173')
    link = f'{frontend_url}/verify-email?token={raw_token}'
    html = (
        f'<p>Hi {display_name},</p>'
        f'<p>Click the link below to verify your FinTrack account. '
        f'This link expires in 24 hours.</p>'
        f'<p><a href="{link}">{link}</a></p>'
        f'<p>If you did not create an account, ignore this email.</p>'
    )
    _send(to_email, 'Verify your FinTrack account', html)


def send_password_reset_email(to_email: str, display_name: str, raw_token: str) -> None:
    frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:5173')
    link = f'{frontend_url}/password-reset/confirm?token={raw_token}'
    html = (
        f'<p>Hi {display_name},</p>'
        f'<p>We received a request to reset your FinTrack password. '
        f'Click the link below — it expires in 15 minutes.</p>'
        f'<p><a href="{link}">{link}</a></p>'
        f'<p>If you did not request this, ignore this email. Your password has not changed.</p>'
    )
    _send(to_email, 'Reset your FinTrack password', html)


def send_consent_notification(
    to_email: str,
    grantee_name: str,
    grantor_name: str,
    access_level: str,
) -> None:
    """Tell a grantee that an individual has shared financial access with them.

    Covers both household (SUMMARY_ONLY) and advisor (FULL_VIEW) grants. Names
    are HTML-escaped because they are user-controlled free text.
    """
    frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:5173')
    safe_grantee = html.escape(grantee_name or '')
    safe_grantor = html.escape(grantor_name or '')

    if access_level == 'FULL_VIEW':
        subject = 'You have been granted advisor access on FinTrack'
        detail = (
            f'<p>{safe_grantor} has granted you <strong>financial advisor</strong> access '
            f'to their FinTrack account. This access expires in 90 days.</p>'
        )
    else:
        subject = 'You have been granted household access on FinTrack'
        detail = (
            f'<p>{safe_grantor} has added you as a <strong>household member</strong> on FinTrack. '
            f'You can now view a summary of their finances.</p>'
        )

    body = (
        f'<p>Hi {safe_grantee},</p>'
        f'{detail}'
        f'<p>Sign in to FinTrack to see what has been shared with you: '
        f'<a href="{frontend_url}">{frontend_url}</a></p>'
        f'<p>If you were not expecting this, you can ignore this email.</p>'
    )
    _send(to_email, subject, body)


def send_invitation(to_email: str, inviter_name: str, raw_token: str, access_level: str) -> None:
    """Invite a not-yet-registered person to create an account and become a
    household member (SUMMARY_ONLY) or advisor (FULL_VIEW) who can view what the
    inviter shares. `inviter_name` is HTML-escaped because it is user-controlled.
    """
    frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:5173')
    link = f'{frontend_url}/accept-invite?token={raw_token}'
    safe_inviter = html.escape(inviter_name or '')

    if access_level == 'FULL_VIEW':
        role_phrase = 'financial advisor'
        purpose = 'so you can view and advise on their finances'
    else:
        role_phrase = 'household member'
        purpose = 'so you can view a summary of their finances'

    body = (
        f'<p>Hi,</p>'
        f'<p>{safe_inviter} has invited you to join FinTrack as their <strong>{role_phrase}</strong>, '
        f'{purpose}.</p>'
        f'<p>Click the link below to create your account. This invitation expires in 7 days.</p>'
        f'<p><a href="{link}">{link}</a></p>'
        f'<p>If you were not expecting this, you can ignore this email.</p>'
    )
    _send(to_email, 'You have been invited to FinTrack', body)
