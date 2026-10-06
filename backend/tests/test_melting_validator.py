import os
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.melting import collect_rising_ranking
from app.core.database import make_engine
from app.models import RankingSnapshot
from app.repositories.api_profiles import upsert_api_profile
from app.services.melting_validator import RankingValidationError, require_valid_melting_ranking, validate_melting_ranking
from app.services.ranking_snapshots import RankedCharacter


def item(rank: int, *, name: str | None = None, source_url: str | None = None) -> RankedCharacter:
    character_id = f"00000000-0000-0000-0000-{rank:012d}"
    return RankedCharacter(
        source_character_id=character_id,
        name=name if name is not None else f"Character {rank}",
        source_url=source_url if source_url is not None else f"https://melting.chat/ko/app/characters/{character_id}",
        rank=rank,
    )


class MeltingValidatorTest(unittest.TestCase):
    def test_complete_ranking_passes(self):
        report = require_valid_melting_ranking([item(1), item(2), item(3)], expected_count=3)
        self.assertTrue(report.passed)
        self.assertEqual(3, report.item_count)

    def test_bad_name_and_url_are_reported(self):
        report = validate_melting_ranking(
            [item(1, name="  ", source_url="https://other.example/character")], expected_count=1
        )
        self.assertEqual({"NAME", "SOURCE_URL"}, {issue.code for issue in report.issues})
        with self.assertRaises(RankingValidationError):
            require_valid_melting_ranking([item(1, name="  ")], expected_count=1)

    def test_partial_ranking_is_rejected(self):
        report = validate_melting_ranking([item(1), item(3)], expected_count=3)
        self.assertEqual({"COUNT", "RANKS"}, {issue.code for issue in report.issues})


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL is required for the PostgreSQL integration test")
class MeltingValidationIntegrationTest(unittest.TestCase):
    def test_invalid_fetch_never_stages_a_snapshot(self):
        engine = make_engine()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with Session(bind=connection) as session:
                        upsert_api_profile(
                            session,
                            source="melting",
                            profile_key="rising_popular",
                            base_url="https://melting.chat",
                            ranking_path="/ko/app/challenge",
                            response_format="html",
                            is_enabled=True,
                        )
                        before = session.scalar(
                            select(func.count()).select_from(RankingSnapshot).where(RankingSnapshot.source == "melting")
                        )
                        malformed = [item(rank) for rank in range(1, 51)]
                        malformed[0] = item(1, source_url="https://other.example/character")
                        with patch("app.collectors.melting.fetch_rising_ranking", return_value=malformed):
                            with self.assertRaises(RankingValidationError):
                                collect_rising_ranking(session)
                        after = session.scalar(
                            select(func.count()).select_from(RankingSnapshot).where(RankingSnapshot.source == "melting")
                        )
                        self.assertEqual(before, after)
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()
