from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Character, RankingEntry, RankingEvent, RankingSnapshot


@dataclass(frozen=True)
class RankingRow:
    character_id: int
    rank: int
    name: str
    previous_rank: int | None
    source_url: str
    events: tuple[str, ...]


@dataclass(frozen=True)
class DashboardData:
    snapshot_id: int | None
    collected_at: datetime | None
    rows: tuple[RankingRow, ...]
    event_counts: dict[str, int]


def load_dashboard_data(session: Session) -> DashboardData:
    latest = session.scalar(
        select(RankingSnapshot)
        .where(RankingSnapshot.source == "melting", RankingSnapshot.ranking_type == "rising_popular")
        .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
        .limit(1)
    )
    if latest is None:
        return DashboardData(None, None, (), {})

    previous = session.scalar(
        select(RankingSnapshot)
        .where(
            RankingSnapshot.source == latest.source,
            RankingSnapshot.ranking_type == latest.ranking_type,
            or_(
                RankingSnapshot.collected_at < latest.collected_at,
                and_(RankingSnapshot.collected_at == latest.collected_at, RankingSnapshot.id < latest.id),
            ),
        )
        .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
        .limit(1)
    )
    previous_ranks = (
        dict(
            session.execute(
                select(RankingEntry.character_id, RankingEntry.rank).where(RankingEntry.snapshot_id == previous.id)
            ).all()
        )
        if previous is not None
        else {}
    )
    events_by_character: dict[int, list[str]] = {}
    event_counts: dict[str, int] = {}
    for event in session.scalars(select(RankingEvent).where(RankingEvent.snapshot_id == latest.id)).all():
        events_by_character.setdefault(event.character_id, []).append(event.event_type)
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

    rows = tuple(
        RankingRow(
            character_id=character_id,
            rank=rank,
            name=name,
            previous_rank=previous_ranks.get(character_id),
            source_url=url,
            events=tuple(events_by_character.get(character_id, ())),
        )
        for character_id, rank, name, url in session.execute(
            select(RankingEntry.character_id, RankingEntry.rank, Character.name, Character.source_url)
            .join(Character, RankingEntry.character_id == Character.id)
            .where(RankingEntry.snapshot_id == latest.id)
            .order_by(RankingEntry.rank)
        ).all()
    )
    return DashboardData(latest.id, latest.collected_at, rows, event_counts)
