import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.services.ai_agents import _check_output, run_character_profile_agent, run_opportunity_finder_agent, run_ranking_summary_agent
from app.services.ranking_snapshots import RankedCharacter, store_ranking_snapshot


class AIOutputValidationTest(unittest.TestCase):
    def test_no_ranking_changes_can_have_empty_highlights(self):
        _check_output(
            {"summary": "변동 없음", "highlights": [], "uncertainty": "이전 자료 없음"},
            fields={"summary": str, "highlights": list, "uncertainty": str},
        )


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL is required for the PostgreSQL integration test")
class AIAgentIntegrationTest(unittest.TestCase):
    def test_opportunity_finder_uses_top_five_and_caches_result(self):
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
                                source_character_id=f"00000000-0000-0000-0000-{rank:012d}",
                                name=f"Test Character {rank}",
                                source_url=f"https://melting.chat/ko/app/characters/00000000-0000-0000-0000-{rank:012d}",
                                rank=rank,
                            ) for rank in range(1, 6)],
                        )
                        response = {
                            "observed_signals": ["1위 캐릭터 설명에 판타지 설정이 있다"],
                            "opportunity_hypotheses": ["판타지 설정을 다른 관계 구조로 탐색"],
                            "next_checks": ["장르별 공급량 조사"],
                            "limitations": "상위 랭킹만으로 수요와 공급을 판단할 수 없음",
                        }
                        profile = {"tagline": "test", "description": "A long public character description for this test."}
                        with patch("app.services.ai_agents._fetch_public_profile", return_value=profile) as fetch, patch(
                            "app.services.ai_agents.generate_json", return_value=response
                        ) as generate:
                            first = run_opportunity_finder_agent(session, snapshot_id=snapshot.id)
                            second = run_opportunity_finder_agent(session, snapshot_id=snapshot.id)
                        self.assertEqual(first.id, second.id)
                        self.assertEqual("opportunity_finder", first.agent_type)
                        self.assertEqual(10, fetch.call_count)
                        generate.assert_called_once()
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()

    def test_specialist_outputs_are_separate_and_cached(self):
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
                                source_character_id="00000000-0000-0000-0000-000000000001",
                                name="Test Character",
                                source_url="https://melting.chat/ko/app/characters/00000000-0000-0000-0000-000000000001",
                                rank=1,
                            )],
                        )
                        character_id = snapshot.entries[0].character_id if snapshot.entries else None
                        if character_id is None:
                            session.refresh(snapshot)
                            character_id = snapshot.entries[0].character_id
                        ranking_output = {"summary": "변동 없음", "highlights": ["첫 수집"], "uncertainty": "이전 자료 없음"}
                        profile_output = {
                            "concept": "테스트 캐릭터", "appeal_points": ["명료함"],
                            "audience_hypotheses": ["추정 없음"], "evidence": ["공개 설명 기반"],
                        }
                        with patch("app.services.ai_agents.generate_json", return_value=ranking_output) as ranking_call:
                            first = run_ranking_summary_agent(session, snapshot_id=snapshot.id)
                            second = run_ranking_summary_agent(session, snapshot_id=snapshot.id)
                            self.assertEqual(first.id, second.id)
                            ranking_call.assert_called_once()
                        with patch("app.services.ai_agents._fetch_public_profile", return_value={"tagline": "test", "description": "A long public character description for the test."}), patch(
                            "app.services.ai_agents.generate_json", return_value=profile_output
                        ) as profile_call:
                            profile = run_character_profile_agent(
                                session, snapshot_id=snapshot.id, character_id=character_id
                            )
                            self.assertNotEqual(first.id, profile.id)
                            self.assertEqual("character_profile", profile.agent_type)
                            profile_call.assert_called_once()
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()
