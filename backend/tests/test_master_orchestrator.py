import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.services.master_orchestrator import run_market_cycle
from app.services.ranking_snapshots import RankedCharacter, store_ranking_snapshot


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL is required for the PostgreSQL integration test")
class MasterOrchestratorIntegrationTest(unittest.TestCase):
    def test_master_dispatches_six_agents_and_records_responses(self):
        engine = make_engine()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with Session(bind=connection) as session:
                        snapshot = store_ranking_snapshot(
                            session,
                            source="melting",
                            ranking_type="rising_popular",
                            collected_at=datetime.now(timezone.utc),
                            characters=[RankedCharacter(
                                source_character_id=f"00000000-0000-0000-0001-{rank:012d}",
                                name=f"Orchestrator Test {rank}",
                                source_url=f"https://melting.chat/ko/app/characters/00000000-0000-0000-0001-{rank:012d}",
                                rank=rank,
                            ) for rank in range(1, 51)],
                        )
                        plan = {
                            "tasks": ["ranking_summary", "character_profile", "opportunity_finder", "creator_intelligence", "genre_trend", "review_comment_miner"],
                            "reason": "순위 변동을 파악한 뒤 프로필과 기획 가설을 검토한다.",
                        }
                        outputs = [
                            {"summary": "변동 없음", "highlights": [], "uncertainty": "첫 수집"},
                            {"concept": "테스트", "appeal_points": ["설정"], "audience_hypotheses": [], "evidence": ["설명"]},
                            {"observed_signals": ["테스트"], "opportunity_hypotheses": ["검증 전 가설"], "next_checks": ["설문"], "limitations": "수요 확인 안 됨"},
                            {"patterns": ["설정"], "creator_tips": ["검증"], "evidence": ["1위"], "limitations": "상위 10개 표본"},
                            {"genre_signals": ["판타지"], "setting_signals": ["세계관"], "evidence": ["1위"], "limitations": "시계열 없음"},
                        ]
                        public = {"tagline": "테스트", "description": "A sufficiently long public description for the orchestration test."}
                        with patch("app.services.master_orchestrator.generate_json", return_value=plan) as planner, patch(
                            "app.services.ai_agents.generate_json", side_effect=outputs
                        ) as specialist, patch("app.services.ai_agents._fetch_public_profile", return_value=public):
                            run = run_market_cycle(session, snapshot_id=snapshot.id)
                        planner.assert_called_once()
                        self.assertEqual(5, specialist.call_count)
                        self.assertEqual("completed", run.status)
                        self.assertEqual(plan["tasks"], [task.agent_type for task in run.tasks])
                        self.assertTrue(all(task.status == "completed" and task.analysis_id for task in run.tasks[:-1]))
                        self.assertEqual("skipped", run.tasks[-1].status)
                        self.assertEqual("COMMENTS_CSV_NOT_PROVIDED", run.tasks[-1].error_type)

                        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", encoding="utf-8", newline="", delete=False) as handle:
                            handle.write("source_url,comment\nhttps://example.com/review,좋아요\n")
                            csv_path = handle.name
                        try:
                            review_output = {"themes": ["호평"], "positive_points": ["좋아요"],
                                             "concerns": [], "evidence": ["https://example.com/review"],
                                             "limitations": "한 건의 표본"}
                            with patch("app.services.master_orchestrator.generate_json", return_value=plan), patch(
                                "app.services.ai_agents.generate_json", return_value=review_output
                            ) as review_model, patch("app.services.ai_agents._fetch_public_profile", return_value=public):
                                with_comments = run_market_cycle(session, snapshot_id=snapshot.id, comments_csv=csv_path)
                            self.assertEqual("completed", with_comments.status)
                            self.assertTrue(all(task.status == "completed" and task.analysis_id for task in with_comments.tasks))
                            review_model.assert_called_once()
                        finally:
                            os.unlink(csv_path)

                        with patch("app.services.master_orchestrator.generate_json", return_value={
                            "tasks": ["ranking_summary", "character_profile", "unknown_agent"], "reason": "테스트"
                        }), patch("app.services.ai_agents.generate_json") as blocked:
                            rejected = run_market_cycle(session, snapshot_id=snapshot.id)
                        self.assertEqual("failed", rejected.status)
                        self.assertEqual("ValueError", rejected.error_type)
                        self.assertEqual([], rejected.tasks)
                        blocked.assert_not_called()
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()
