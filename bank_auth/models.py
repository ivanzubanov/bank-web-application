import enum
from datetime import datetime, timezone
from datetime import date
from typing import Optional
from sqlalchemy import String, Enum, CheckConstraint, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from bank_auth.database import Base

class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"

class UserTable(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(60), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)

    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    patronymic: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_banned: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", create_type=True),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False
    )

    __table_args__ = (
        CheckConstraint("birth_date <= CURRENT_DATE - INTERVAL '14 years'", name="check_user_age_min"),
    )

class UserRefreshTokenTable(Base):
    __tablename__ = "user_refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )