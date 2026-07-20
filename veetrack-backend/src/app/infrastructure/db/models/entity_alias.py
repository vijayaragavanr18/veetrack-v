from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.entity import EntityModel


class EntityAliasModel(Base):
    __tablename__ = "entity_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias_text: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(20), nullable=False, default="name")

    entity: Mapped[EntityModel] = relationship(
        "EntityModel", back_populates="aliases", lazy="raise"
    )

    __table_args__ = (Index("ix_entity_aliases_alias_text", "alias_text"),)
