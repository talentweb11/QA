"""Seed a fictitious demo user for local testing.

Creates ``user@example.com`` / ``password123`` directly in the database. This
bypasses the API password-complexity check on purpose — it is a throwaway demo
account, not a real registration. Idempotent: re-running is a no-op if the user
already exists.

Run from the ``backend/`` directory with a populated ``.env``::

    python -m scripts.seed_demo_user
"""

from __future__ import annotations

from app import create_app
from app.extensions import db
from app.models import Role, User
from app.utils.crypto import hash_password

DEMO_EMAIL = 'user@example.com'
DEMO_PASSWORD = 'password123'
DEMO_DISPLAY_NAME = 'Demo User'


def seed() -> None:
    app = create_app()
    with app.app_context():
        if User.query.filter_by(email=DEMO_EMAIL).first():
            print(f'Demo user already exists: {DEMO_EMAIL}')
            return

        role = Role.query.filter_by(role_name='INDIVIDUAL').first()
        if not role:
            raise SystemExit('INDIVIDUAL role missing — run db/init.sql first')

        user = User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            display_name=DEMO_DISPLAY_NAME,
            status='ACTIVE',
            mfa_enabled=False,
        )
        user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        print(f'Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}')


if __name__ == '__main__':
    seed()
