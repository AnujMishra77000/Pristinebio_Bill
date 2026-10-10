"""Revocable cookie sessions, one-time setup/invitations, MFA and security audit.

Existing hashes and billing snapshots are not rewritten. Existing users must
upgrade their passphrase on their next password-authenticated session.
"""
import sqlalchemy as sa
from alembic import op

revision = "20260916_0009"
down_revision = "20260916_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("password_policy_version", sa.Integer(), server_default="0", nullable=False))
    for name in ("mfa_secret", "mfa_pending_secret"):
        op.add_column("users", sa.Column(name, sa.Text(), nullable=True))
    for name in ("mfa_pending_expires_at", "mfa_enabled_at"):
        op.add_column("users", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_last_step", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("mfa_reenrollment_required", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table("admin_setup_state", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.execute("INSERT INTO admin_setup_state (id, completed_at) SELECT 1, CASE WHEN EXISTS (SELECT 1 FROM users) THEN CURRENT_TIMESTAMP ELSE NULL END")
    op.create_table("auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False), sa.Column("current_refresh_hash", sa.String(64), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table("auth_refresh_credentials",
        sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("auth_sessions.id"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("successor_hash", sa.String(64)), sa.Column("successor_encrypted", sa.Text()))
    op.create_index("ix_auth_refresh_credentials_session_id", "auth_refresh_credentials", ["session_id"])
    op.create_table("account_invitations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(255), nullable=False), sa.Column("role", sa.String(16), nullable=False),
        sa.Column("branch_ids", sa.JSON(), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("accepted_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_account_invitations_email", "account_invitations", ["email"])
    op.create_table("mfa_recovery_codes", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("code_hash", sa.String(64), nullable=False, unique=True), sa.Column("used_at", sa.DateTime(timezone=True)))
    op.create_index("ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"])
    op.create_table("security_audit_logs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before", sa.JSON()), sa.Column("after", sa.JSON()))
    op.create_table("auth_throttles", sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False))


def downgrade():
    raise RuntimeError("Security migration is forward-only; do not discard account/session history")
