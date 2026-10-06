"""Run all six specialists with live services and roll back the sample comment analysis."""

from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.core.local_env import load_local_env
from app.models import RankingSnapshot
from app.services.master_orchestrator import run_market_cycle


def main() -> int:
    load_local_env()
    engine = make_engine()
    try:
        with TemporaryDirectory() as directory, engine.connect() as connection:
            csv_path = Path(directory) / "synthetic_comments.csv"
            csv_path.write_text(
                "source_url,comment\n"
                "https://example.com/integration-test,캐릭터의 설정이 흥미롭습니다\n"
                "https://example.com/integration-test,대화의 전개가 궁금합니다\n"
                "https://example.com/integration-test,배경 설명이 조금 더 필요합니다\n",
                encoding="utf-8",
            )
            transaction = connection.begin()
            try:
                with Session(bind=connection) as session:
                    snapshot_id = session.scalar(
                        select(RankingSnapshot.id)
                        .where(RankingSnapshot.source == "melting", RankingSnapshot.ranking_type == "rising_popular")
                        .order_by(RankingSnapshot.collected_at.desc(), RankingSnapshot.id.desc())
                        .limit(1)
                    )
                    if snapshot_id is None:
                        raise RuntimeError("No Melting ranking snapshot found")
                    run = run_market_cycle(session, snapshot_id=snapshot_id, comments_csv=str(csv_path))
                    print(f"Live master test: snapshot={snapshot_id}, status={run.status}, tasks={len(run.tasks)}")
                    for task in sorted(run.tasks, key=lambda item: item.sequence):
                        print(f"{task.sequence}. {task.agent_type}: {task.status}; error={task.error_type or 'none'}")
                    ok = run.status == "completed" and len(run.tasks) == 6 and all(
                        task.status == "completed" and task.analysis_id is not None for task in run.tasks
                    )
            finally:
                transaction.rollback()
            print("Synthetic comment test results rolled back.")
            return 0 if ok else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
