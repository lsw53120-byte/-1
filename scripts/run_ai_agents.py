from sqlalchemy import select

from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.models import RankingEntry, RankingSnapshot
from app.services.ai_agents import run_character_profile_agent, run_ranking_summary_agent


load_local_env()
with session_scope() as session:
    snapshot_id = session.scalar(
        select(RankingSnapshot.id)
        .where(RankingSnapshot.source == "melting", RankingSnapshot.ranking_type == "rising_popular")
        .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
        .limit(1)
    )
    if snapshot_id is None:
        raise SystemExit("No Melting ranking snapshot found")

failures = []
try:
    with session_scope() as session:
        analysis = run_ranking_summary_agent(session, snapshot_id=snapshot_id)
        print(f"Ranking summary agent saved analysis {analysis.id}.")
except Exception as exc:
    failures.append(f"ranking summary: {exc}")

try:
    with session_scope() as session:
        top_character_id = session.scalar(
            select(RankingEntry.character_id).where(RankingEntry.snapshot_id == snapshot_id, RankingEntry.rank == 1)
        )
        if top_character_id is None:
            raise LookupError("Top-ranked character was not found")
        analysis = run_character_profile_agent(session, snapshot_id=snapshot_id, character_id=top_character_id)
        print(f"Character profile agent saved analysis {analysis.id}.")
except Exception as exc:
    failures.append(f"character profile: {exc}")

if failures:
    raise SystemExit("; ".join(failures))
