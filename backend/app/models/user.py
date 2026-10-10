from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, Text, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, relationship, mapped_column

from app.db.session import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Branch


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            native_enum=False,
            validate_strings=True,
            values_callable=lambda roles: [role.value for role in roles],
            create_constraint=True,
        ),
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_policy_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_pending_secret: Mapped[str | None] = mapped_column(Text)
    mfa_pending_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_step: Mapped[int | None] = mapped_column(Integer)
    mfa_reenrollment_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    branch_assignments: Mapped[list[UserBranchAssignment]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserBranchAssignment(Base):
    __tablename__ = "user_branch_assignments"
    __table_args__ = (UniqueConstraint("user_id", "branch_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)

    user: Mapped[User] = relationship(back_populates="branch_assignments")
    branch: Mapped[Branch] = relationship(back_populates="user_assignments")
