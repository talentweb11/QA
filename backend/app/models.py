import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ENUM as PGEnum
from app.extensions import db

# Reference existing PostgreSQL ENUM types (created by db/init.sql — do not recreate)
user_status_enum       = PGEnum('PENDING', 'ACTIVE', 'SUSPENDED',        name='user_status',        create_type=False)
statement_status_enum  = PGEnum('PENDING', 'PROCESSED', 'FAILED',        name='statement_status',   create_type=False)
category_type_enum     = PGEnum('INCOME', 'EXPENSE',                     name='category_type',      create_type=False)
consent_access_enum    = PGEnum('SUMMARY_ONLY', 'FULL_VIEW',             name='consent_access_level', create_type=False)
consent_status_enum    = PGEnum('ACTIVE', 'REVOKED',                     name='consent_status',     create_type=False)
audit_outcome_enum     = PGEnum('SUCCESS', 'FAILURE',                    name='audit_outcome',      create_type=False)


# Many-to-many User <-> Role link. Matches the user_roles table in db/init.sql.
user_roles = db.Table(
    'user_roles',
    db.Column('user_id', PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
)


class Role(db.Model):
    __tablename__ = 'roles'

    id        = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(20), unique=True, nullable=False)

    users = db.relationship('User', secondary=user_roles, back_populates='roles', lazy='select')


class User(db.Model):
    __tablename__ = 'users'

    id                            = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email                         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash                 = db.Column(db.String(255), nullable=False)
    totp_secret                   = db.Column(db.String(255), nullable=True)
    mfa_enabled                   = db.Column(db.Boolean, nullable=False, default=False)
    display_name                  = db.Column(db.String(100), nullable=False)
    nric                          = db.Column(db.String(255), nullable=True)
    status                        = db.Column(user_status_enum, nullable=False, default='PENDING')
    email_verification_token_hash = db.Column(db.String(255), nullable=True)
    email_verification_expires_at = db.Column(db.DateTime, nullable=True)
    failed_login_attempts         = db.Column(db.Integer, nullable=False, default=0)
    locked_until                  = db.Column(db.DateTime, nullable=True)
    created_at                    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    roles        = db.relationship('Role', secondary=user_roles, back_populates='users', lazy='selectin')
    sessions     = db.relationship('Session', back_populates='user', cascade='all, delete-orphan')
    reset_tokens = db.relationship('PasswordResetToken', back_populates='user', cascade='all, delete-orphan')
    statements   = db.relationship('BankStatement', back_populates='user', cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', back_populates='user', cascade='all, delete-orphan')
    categories   = db.relationship('Category', back_populates='user', cascade='all, delete-orphan')
    consents_granted  = db.relationship('Consent', foreign_keys='Consent.grantor_id', back_populates='grantor', cascade='all, delete-orphan')
    consents_received = db.relationship('Consent', foreign_keys='Consent.grantee_id', back_populates='grantee', cascade='all, delete-orphan')

    @property
    def role_names(self) -> set[str]:
        """Set of this user's role names, e.g. {'INDIVIDUAL', 'HOUSEHOLD'}."""
        return {r.role_name for r in self.roles}

    def has_role(self, name: str) -> bool:
        return any(r.role_name == name for r in self.roles)


class Session(db.Model):
    __tablename__ = 'sessions'

    id          = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash  = db.Column(db.String(255), nullable=False)
    ip_address  = db.Column(db.String(45), nullable=False)
    last_active = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at  = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User', back_populates='sessions')


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'

    id         = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at    = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', back_populates='reset_tokens')


class BankStatement(db.Model):
    __tablename__ = 'bank_statements'

    id                       = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id                  = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    account_number_encrypted = db.Column(db.String(255), nullable=True)
    file_name                = db.Column(db.String(255), nullable=False)
    storage_path             = db.Column(db.String(500), nullable=False)
    file_hash                = db.Column(db.String(64), nullable=False)
    status                   = db.Column(statement_status_enum, nullable=False, default='PENDING')
    uploaded_at              = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user         = db.relationship('User', back_populates='statements')
    transactions = db.relationship('Transaction', back_populates='statement')


class Category(db.Model):
    __tablename__ = 'categories'

    id      = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    name    = db.Column(db.String(100), nullable=False)
    type    = db.Column(category_type_enum, nullable=False)

    user         = db.relationship('User', back_populates='categories')
    transactions = db.relationship('Transaction', back_populates='category')


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id               = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    statement_id     = db.Column(PGUUID(as_uuid=True), db.ForeignKey('bank_statements.id', ondelete='SET NULL'), nullable=True)
    category_id      = db.Column(PGUUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    amount           = db.Column(db.Numeric(12, 2), nullable=False)
    merchant_name    = db.Column(db.String(255), nullable=True)
    description      = db.Column(db.Text, nullable=True)
    created_at       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user      = db.relationship('User', back_populates='transactions')
    statement = db.relationship('BankStatement', back_populates='transactions')
    category  = db.relationship('Category', back_populates='transactions')


class Consent(db.Model):
    __tablename__ = 'consents'

    id           = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grantor_id   = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    grantee_id   = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    access_level = db.Column(consent_access_enum, nullable=False)
    status       = db.Column(consent_status_enum, nullable=False, default='ACTIVE')
    expires_at   = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    grantor = db.relationship('User', foreign_keys=[grantor_id], back_populates='consents_granted')
    grantee = db.relationship('User', foreign_keys=[grantee_id], back_populates='consents_received')

    __table_args__ = (
        db.UniqueConstraint('grantor_id', 'grantee_id', name='uq_consent_grantor_grantee'),
    )


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id          = db.Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = db.Column(PGUUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    event_type  = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(PGUUID(as_uuid=True), nullable=True)
    outcome     = db.Column(audit_outcome_enum, nullable=False)
    ip_address  = db.Column(db.String(45), nullable=False)
    user_agent  = db.Column(db.String(500), nullable=True)
    timestamp   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
