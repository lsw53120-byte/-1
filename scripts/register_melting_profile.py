from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.repositories.api_profiles import upsert_api_profile
from app.collectors.melting import BASE_URL, PROFILE_KEY, RANKING_PATH, SOURCE


load_local_env()
with session_scope() as session:
    profile = upsert_api_profile(
        session,
        source=SOURCE,
        profile_key=PROFILE_KEY,
        base_url=BASE_URL,
        ranking_path=RANKING_PATH,
        response_format="html",
        is_enabled=True,
    )
    print(f"Melting public ranking profile ready (id={profile.id}).")
