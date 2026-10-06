from sqlalchemy import select

from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.models import RankingSnapshot
from app.services.ai_agents import run_opportunity_finder_agent


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
    analysis = run_opportunity_finder_agent(session, snapshot_id=snapshot_id)
    print(f"Opportunity Finder saved analysis {analysis.id} for snapshot {snapshot_id}.")
    for heading, key in (
        ("Observed signals", "observed_signals"),
        ("Planning hypotheses", "opportunity_hypotheses"),
        ("Next checks", "next_checks"),
    ):
        print(f"{heading}:")
        for item in analysis.output_json[key]:
            print(f"- {item}")
    print(f"Limits: {analysis.output_json['limitations']}")
