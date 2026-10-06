from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Character, RankingEntry, RankingSnapshot


@dataclass(frozen=True)
class RankedCharacter:
    source_character_id: str
    name: str
    source_url: str
    rank: int


def store_ranking_snapshot(
    session: Session,
    *,
    source: str,
    ranking_type: str,
    collected_at: datetime,
    characters: Sequence[RankedCharacter],
) -> RankingSnapshot:
    """Stage one complete ranking in the caller's transaction.

    The caller commits or rolls back. A failed write never commits part of a ranking.
    """
    if not source.strip() or not ranking_type.strip():
        raise ValueError("source and ranking_type are required")
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ValueError("collected_at must include a timezone")
    if not characters:
        raise ValueError("A ranking snapshot must contain at least one character")

    ids = [item.source_character_id.strip() for item in characters]
    ranks = [item.rank for item in characters]
    if any(not item_id for item_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("source_character_id values must be nonempty and unique")
    if any(not isinstance(rank, int) or isinstance(rank, bool) or rank < 1 for rank in ranks):
        raise ValueError("rank values must be positive integers")
    if len(ranks) != len(set(ranks)):
        raise ValueError("rank values must be unique within a snapshot")
    if any(not item.name.strip() or not item.source_url.strip() for item in characters):
        raise ValueError("name and source_url are required for every character")

    snapshot = RankingSnapshot(source=source.strip(), ranking_type=ranking_type.strip(), collected_at=collected_at)
    session.add(snapshot)
    session.flush()

    for item in characters:
        statement = (
            insert(Character)
            .values(
                source=source.strip(),
                source_character_id=item.source_character_id.strip(),
                name=item.name.strip(),
                source_url=item.source_url.strip(),
            )
            .on_conflict_do_update(
                constraint="uq_character_source_id",
                set_={"name": item.name.strip(), "source_url": item.source_url.strip()},
            )
            .returning(Character.id)
        )
        character_id = session.execute(statement).scalar_one()
        session.add(RankingEntry(snapshot_id=snapshot.id, character_id=character_id, rank=item.rank))

    session.flush()
    return snapshot
