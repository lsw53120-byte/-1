import sys

from sqlalchemy import select

from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.models import RankingSnapshot
from app.services.change_detector import detect_ranking_changes, summarize_events


load_local_env()
with session_scope() as session:
    if len(sys.argv) > 1:
        snapshot_id = int(sys.argv[1])
    else:
        snapshot_id = session.scalar(
            select(RankingSnapshot.id)
            .where(RankingSnapshot.source == "melting", RankingSnapshot.ranking_type == "rising_popular")
            .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
            .limit(1)
        )
    if snapshot_id is None:
        raise SystemExit("No Melting ranking snapshot found")
    events = detect_ranking_changes(session, snapshot_id=snapshot_id)
    print(f"snapshot={snapshot_id} events={len(events)} counts={summarize_events(events)}")
