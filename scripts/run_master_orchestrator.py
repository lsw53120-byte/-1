import argparse

from sqlalchemy import select

from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.models import RankingSnapshot
from app.services.master_orchestrator import run_market_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the market master orchestrator")
    parser.add_argument("--comments-csv", help="Optional public or consented comments CSV")
    args = parser.parse_args()
    load_local_env()
    with session_scope() as session:
        snapshot_id = session.scalar(
            select(RankingSnapshot.id)
            .where(RankingSnapshot.source == "melting", RankingSnapshot.ranking_type == "rising_popular")
            .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
            .limit(1)
        )
        if snapshot_id is None:
            print("No Melting ranking snapshot found.")
            return 1
        run = run_market_cycle(session, snapshot_id=snapshot_id, comments_csv=args.comments_csv)
        print(f"Master run {run.id}: {run.status}; snapshot {snapshot_id}")
        if run.plan_json:
            print(f"Plan: {', '.join(run.plan_json['tasks'])}")
            print(f"Reason: {run.plan_json['reason']}")
        for task in sorted(run.tasks, key=lambda item: item.sequence):
            print(f"Command {task.sequence}: {task.agent_type} -> {task.status}; analysis_id={task.analysis_id}")
            if task.error_type:
                print(f"  Error type: {task.error_type}")
        if run.error_type:
            print(f"Planning error type: {run.error_type}")
        return 0 if run.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
