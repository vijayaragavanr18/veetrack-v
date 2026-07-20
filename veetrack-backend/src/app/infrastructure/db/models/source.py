from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.api_usage_log import ApiUsageLogModel
    from app.infrastructure.db.models.article import ArticleModel


class SourceModel(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rate_limit_budget: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    articles: Mapped[list[ArticleModel]] = relationship(
        "ArticleModel", back_populates="source", lazy="raise"
    )
    api_usage_logs: Mapped[list[ApiUsageLogModel]] = relationship(
        "ApiUsageLogModel", back_populates="source", lazy="raise"
    )
