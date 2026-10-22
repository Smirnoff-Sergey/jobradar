from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        # Активное резюме у пользователя одно: по нему идёт оценка вакансий.
        Index(
            "uq_resumes_user_id_active",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=true())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
