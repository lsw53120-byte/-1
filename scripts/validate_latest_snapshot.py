from sqlalchemy import select

from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.models import Character, RankingEntry, RankingSnapshot
from app.services.melting_validator import validate_melting_ranking
from app.services.ranking_snapshots import RankedCharacter


load_local_env()
with session_scope() as session:
    snapshot = session.scalar(
        select(RankingSnapshot)
        .where(RankingSnapshot.source == "melting", RankingSnapshot.ranking_type == "rising_popular")
        .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
    )
    if snapshot is None:
        raise SystemExit("No Melting ranking snapshot found")
    rows = session.execute(
        select(RankingEntry.rank, Character.source_character_id, Character.name, Character.source_url)
        .join(Character, RankingEntry.character_id == Character.id)
        .where(RankingEntry.snapshot_id == snapshot.id, Character.source == "melting")
        .order_by(RankingEntry.rank)
    ).all()
    characters = [
        RankedCharacter(source_character_id=row.source_character_id, name=row.name, source_url=row.source_url, rank=row.rank)
        for row in rows
    ]
    report = validate_melting_ranking(characters)
    if report.passed:
        print(f"PASS snapshot={snapshot.id} policy={report.policy_version} count={report.item_count}")
    else:
        for issue in report.issues:
            print(f"FAIL {issue.code}: {issue.detail}")
        raise SystemExit(1)
