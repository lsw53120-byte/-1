from collections import Counter

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import RankingEntry, RankingEvent, RankingSnapshot


NEW_CHARACTER = "NEW_CHARACTER"
ENTER_TOP50 = "ENTER_TOP50"
ENTER_TOP10 = "ENTER_TOP10"
SURGE = "SURGE"
DECLINE = "DECLINE"


def detect_ranking_changes(
    session: Session,
    *,
    snapshot_id: int,
    surge_threshold: int = 10,
    decline_threshold: int = 10,
) -> list[RankingEvent]:
    """Record changes against the preceding snapshot; the first snapshot is a baseline."""
    if surge_threshold < 1 or decline_threshold < 1:
        raise ValueError("change thresholds must be positive")
    current = session.get(RankingSnapshot, snapshot_id)
    if current is None:
        raise LookupError(f"Ranking snapshot {snapshot_id} was not found")

    earlier = or_(
        RankingSnapshot.collected_at < current.collected_at,
        and_(RankingSnapshot.collected_at == current.collected_at, RankingSnapshot.id < current.id),
    )
    previous = session.scalar(
        select(RankingSnapshot)
        .where(
            RankingSnapshot.source == current.source,
            RankingSnapshot.ranking_type == current.ranking_type,
            earlier,
        )
        .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
        .limit(1)
    )
    if previous is None:
        return []

    current_ranks = dict(
        session.execute(
            select(RankingEntry.character_id, RankingEntry.rank).where(RankingEntry.snapshot_id == current.id)
        ).all()
    )
    previous_ranks = dict(
        session.execute(
            select(RankingEntry.character_id, RankingEntry.rank).where(RankingEntry.snapshot_id == previous.id)
        ).all()
    )
    previously_seen = set(
        session.scalars(
            select(RankingEntry.character_id)
            .join(RankingSnapshot, RankingEntry.snapshot_id == RankingSnapshot.id)
            .where(
                RankingSnapshot.source == current.source,
                RankingSnapshot.ranking_type == current.ranking_type,
                earlier,
            )
        ).all()
    )

    findings: list[tuple[int, str, int | None, int | None, int | None]] = []
    for character_id, rank in current_ranks.items():
        old_rank = previous_ranks.get(character_id)
        if character_id not in previously_seen:
            findings.append((character_id, NEW_CHARACTER, None, rank, None))
        if old_rank is None:
            findings.append((character_id, ENTER_TOP50, None, rank, None))
        if rank <= 10 and (old_rank is None or old_rank > 10):
            findings.append((character_id, ENTER_TOP10, old_rank, rank, None if old_rank is None else old_rank - rank))
        if old_rank is not None:
            change = old_rank - rank
            if change >= surge_threshold:
                findings.append((character_id, SURGE, old_rank, rank, change))
            elif -change >= decline_threshold:
                findings.append((character_id, DECLINE, old_rank, rank, change))

    for character_id, old_rank in previous_ranks.items():
        if character_id not in current_ranks:
            findings.append((character_id, DECLINE, old_rank, None, None))

    for character_id, event_type, old_rank, new_rank, change in findings:
        session.execute(
            insert(RankingEvent)
            .values(
                snapshot_id=current.id,
                character_id=character_id,
                event_type=event_type,
                previous_rank=old_rank,
                current_rank=new_rank,
                rank_change=change,
            )
            .on_conflict_do_nothing(constraint="uq_ranking_event_identity")
        )
    session.flush()
    return list(
        session.scalars(
            select(RankingEvent)
            .where(RankingEvent.snapshot_id == current.id)
            .order_by(RankingEvent.event_type, RankingEvent.current_rank, RankingEvent.id)
        ).all()
    )


def summarize_events(events: list[RankingEvent]) -> dict[str, int]:
    counts = Counter(event.event_type for event in events)
    return {event_type: counts.get(event_type, 0) for event_type in (NEW_CHARACTER, ENTER_TOP50, ENTER_TOP10, SURGE, DECLINE)}
