from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import APIProfile


def _validate_profile(
    *, source: str, profile_key: str, base_url: str, ranking_path: str, response_format: str
) -> tuple[str, str, str, str, str]:
    source, profile_key = source.strip(), profile_key.strip()
    base_url, ranking_path = base_url.strip(), ranking_path.strip()
    response_format = response_format.strip().lower()
    if not source or not profile_key:
        raise ValueError("source and profile_key are required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base_url must be a public HTTPS origin without credentials")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("base_url must contain only an origin")
    if not ranking_path.startswith("/") or ranking_path.startswith("//") or ".." in ranking_path:
        raise ValueError("ranking_path must be an absolute path without traversal")
    if response_format not in {"html", "json"}:
        raise ValueError("response_format must be html or json")
    return source, profile_key, base_url.rstrip("/"), ranking_path, response_format


def upsert_api_profile(
    session: Session,
    *,
    source: str,
    profile_key: str,
    base_url: str,
    ranking_path: str,
    response_format: str,
    is_enabled: bool = False,
) -> APIProfile:
    """Register source metadata in the caller's transaction; no network request is made."""
    source, profile_key, base_url, ranking_path, response_format = _validate_profile(
        source=source,
        profile_key=profile_key,
        base_url=base_url,
        ranking_path=ranking_path,
        response_format=response_format,
    )
    statement = (
        insert(APIProfile)
        .values(
            source=source,
            profile_key=profile_key,
            base_url=base_url,
            ranking_path=ranking_path,
            response_format=response_format,
            is_enabled=is_enabled,
        )
        .on_conflict_do_update(
            constraint="uq_api_profile_source_key",
            set_={
                "base_url": base_url,
                "ranking_path": ranking_path,
                "response_format": response_format,
                "is_enabled": is_enabled,
                "updated_at": func.now(),
            },
        )
        .returning(APIProfile.id)
    )
    profile_id = session.execute(statement).scalar_one()
    session.flush()
    profile = session.get(APIProfile, profile_id, populate_existing=True)
    assert profile is not None
    return profile


def get_enabled_api_profile(session: Session, *, source: str, profile_key: str) -> APIProfile:
    profile = session.scalar(
        select(APIProfile).where(
            APIProfile.source == source.strip(),
            APIProfile.profile_key == profile_key.strip(),
            APIProfile.is_enabled.is_(True),
        )
    )
    if profile is None:
        raise LookupError(f"No enabled API profile for {source}/{profile_key}")
    return profile
