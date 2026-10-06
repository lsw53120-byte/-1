import os
import unittest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.models import APIProfile
from app.repositories.api_profiles import get_enabled_api_profile, upsert_api_profile


@unittest.skipUnless(os.getenv("DATABASE_URL"), "DATABASE_URL is required for the PostgreSQL integration test")
class APIProfileIntegrationTest(unittest.TestCase):
    def test_registration_update_and_enabled_lookup(self):
        engine = make_engine()
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with Session(bind=connection) as session:
                        first = upsert_api_profile(
                            session,
                            source="integration_test",
                            profile_key="popular",
                            base_url="https://example.com/",
                            ranking_path="/rankings",
                            response_format="html",
                        )
                        with self.assertRaises(LookupError):
                            get_enabled_api_profile(session, source="integration_test", profile_key="popular")
                        second = upsert_api_profile(
                            session,
                            source="integration_test",
                            profile_key="popular",
                            base_url="https://example.com",
                            ranking_path="/rankings/today",
                            response_format="json",
                            is_enabled=True,
                        )
                        self.assertEqual(first.id, second.id)
                        enabled = get_enabled_api_profile(session, source="integration_test", profile_key="popular")
                        self.assertEqual("/rankings/today", enabled.ranking_path)
                        self.assertEqual("json", enabled.response_format)
                finally:
                    transaction.rollback()
            with Session(engine) as session:
                self.assertIsNone(session.scalar(select(APIProfile).where(APIProfile.source == "integration_test")))
        finally:
            engine.dispose()

    def test_invalid_profile_rejected_before_write(self):
        engine = make_engine()
        try:
            with Session(engine) as session:
                with self.assertRaises(ValueError):
                    upsert_api_profile(
                        session,
                        source="integration_test",
                        profile_key="popular",
                        base_url="http://example.com",
                        ranking_path="/rankings",
                        response_format="html",
                    )
                self.assertFalse(session.new)
        finally:
            engine.dispose()
