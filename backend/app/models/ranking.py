from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_character_id: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list["RankingEntry"]] = relationship(back_populates="character")

    __table_args__ = (UniqueConstraint("source", "source_character_id", name="uq_character_source_id"),)


class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    ranking_type: Mapped[str] = mapped_column(String(80), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list["RankingEntry"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_snapshot_source_type_collected", "source", "ranking_type", "collected_at"),)


class RankingEntry(Base):
    __tablename__ = "ranking_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("ranking_snapshots.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    snapshot: Mapped[RankingSnapshot] = relationship(back_populates="entries")
    character: Mapped[Character] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint("snapshot_id", "character_id", name="uq_entry_snapshot_character"),
        UniqueConstraint("snapshot_id", "rank", name="uq_entry_snapshot_rank"),
        Index("ix_entry_character", "character_id"),
    )
