import os
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.services.change_detector import detect_ranking_changes, summarize_events
from app.services.ranking_snapshots import RankedCharacter, store_ranking_snapshot


def ranked(character_number: int, rank: int) -> RankedCharacter:
    return RankedCharacter(
        source_character_id=f"detector-{character_number}",
        name=f"Character {character_number}",
        source_url=f"https://example.com/{character_number}",
        rank=rank,
    )


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL is required for the PostgreSQL integration test")
class ChangeDetectorIntegrationTest(unittest.TestCase):
    def test_baseline_and_all_event_types_are_idempotent(self):
        engine = make_engine()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with Session(bind=connection) as session:
                        now = datetime.now(timezone.utc)
                        baseline = store_ranking_snapshot(
                            session,
                            source="detector_test",
                            ranking_type="popular",
                            collected_at=now,
                            characters=[ranked(number, number) for number in range(1, 13)],
                        )
                        self.assertEqual([], detect_ranking_changes(session, snapshot_id=baseline.id))
                        current_order = [12, 2, 3, 4, 5, 6, 7, 8, 13, 11, 10, 1]
                        current = store_ranking_snapshot(
                            session,
                            source="detector_test",
                            ranking_type="popular",
                            collected_at=now + timedelta(seconds=1),
                            characters=[ranked(number, rank) for rank, number in enumerate(current_order, start=1)],
                        )
                        events = detect_ranking_changes(
                            session, snapshot_id=current.id, surge_threshold=10, decline_threshold=10
                        )
                        self.assertEqual(
                            {"NEW_CHARACTER": 1, "ENTER_TOP50": 1, "ENTER_TOP10": 3, "SURGE": 1, "DECLINE": 2},
                            summarize_events(events),
                        )
                        self.assertEqual(len(events), len(detect_ranking_changes(session, snapshot_id=current.id)))
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()
