import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.models import Character, RankingEntry, RankingSnapshot
from app.services.ranking_snapshots import RankedCharacter, store_ranking_snapshot


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL is required for the PostgreSQL integration test")
class RankingSnapshotIntegrationTest(unittest.TestCase):
    def test_snapshot_is_atomic_and_reuses_character_identity(self):
        engine = make_engine()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with Session(bind=connection) as session:
                        first = store_ranking_snapshot(
                            session,
                            source="integration_test",
                            ranking_type="popular",
                            collected_at=datetime.now(timezone.utc),
                            characters=[
                                RankedCharacter("a", "Alpha", "https://example.com/a", 1),
                                RankedCharacter("b", "Beta", "https://example.com/b", 2),
                            ],
                        )
                        second = store_ranking_snapshot(
                            session,
                            source="integration_test",
                            ranking_type="popular",
                            collected_at=datetime.now(timezone.utc),
                            characters=[
                                RankedCharacter("b", "Beta updated", "https://example.com/b", 1),
                                RankedCharacter("a", "Alpha", "https://example.com/a", 2),
                            ],
                        )
                        self.assertNotEqual(first.id, second.id)
                        self.assertEqual(
                            2,
                            session.scalar(select(func.count()).select_from(Character).where(Character.source == "integration_test")),
                        )
                        self.assertEqual(
                            [1, 2],
                            list(session.scalars(select(RankingEntry.rank).where(RankingEntry.snapshot_id == second.id).order_by(RankingEntry.rank))),
                        )
                        self.assertEqual(
                            "Beta updated",
                            session.scalar(select(Character.name).where(Character.source == "integration_test", Character.source_character_id == "b")),
                        )
                        self.assertEqual(2, session.scalar(select(func.count()).select_from(RankingSnapshot).where(RankingSnapshot.source == "integration_test")))
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()

    def test_rejects_duplicate_ranks_before_writing(self):
        engine = make_engine()
        try:
            with Session(engine) as session:
                with self.assertRaises(ValueError):
                    store_ranking_snapshot(
                        session,
                        source="integration_test",
                        ranking_type="popular",
                        collected_at=datetime.now(timezone.utc),
                        characters=[
                            RankedCharacter("a", "Alpha", "https://example.com/a", 1),
                            RankedCharacter("b", "Beta", "https://example.com/b", 1),
                        ],
                    )
                self.assertFalse(session.new)
        finally:
            engine.dispose()
