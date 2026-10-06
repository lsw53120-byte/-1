import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.repositories.api_profiles import get_enabled_api_profile
from app.services.melting_validator import require_valid_melting_ranking
from app.services.ranking_snapshots import RankedCharacter, store_ranking_snapshot


SOURCE = "melting"
PROFILE_KEY = "rising_popular"
RANKING_TYPE = "rising_popular"
BASE_URL = "https://melting.chat"
RANKING_PATH = "/ko/app/challenge"
EXPECTED_RANKS = 50
MAX_PAGE_BYTES = 2_000_000
CHARACTER_PATH = re.compile(r"^/ko/app/characters/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")


def parse_rising_ranking(html: str, *, expected_count: int = EXPECTED_RANKS) -> list[RankedCharacter]:
    soup = BeautifulSoup(html, "html.parser")
    heading = next(
        (item for item in soup.find_all("h2") if item.get_text(" ", strip=True) == "라이징 인기 랭킹"),
        None,
    )
    section = heading.find_parent("section") if heading else None
    if section is None:
        raise ValueError("Melting rising popularity ranking section was not found")

    result: list[RankedCharacter] = []
    for card in section.select(".ranking-multi-row-card > a[href]"):
        match = CHARACTER_PATH.fullmatch(card.get("href", ""))
        name_tag = card.find("h3")
        rank_tag = card.select_one("span.text-xl.font-bold")
        if not match or not name_tag or not rank_tag:
            raise ValueError("A Melting ranking card is missing its ID, name, or rank")
        rank_text = rank_tag.get_text(strip=True)
        if not rank_text.isdigit():
            raise ValueError(f"Invalid Melting ranking position: {rank_text!r}")
        name = name_tag.get_text(" ", strip=True)
        if not name:
            raise ValueError("A Melting ranking card has no character name")
        result.append(
            RankedCharacter(
                source_character_id=match.group(1),
                name=name,
                source_url=f"{BASE_URL}{card['href']}",
                rank=int(rank_text),
            )
        )

    if len(result) != expected_count or sorted(item.rank for item in result) != list(range(1, expected_count + 1)):
        raise ValueError(f"Expected complete ranks 1-{expected_count}; found {len(result)} cards")
    if len({item.source_character_id for item in result}) != len(result):
        raise ValueError("Melting ranking contains a duplicate character ID")
    return sorted(result, key=lambda item: item.rank)


def fetch_rising_ranking() -> list[RankedCharacter]:
    request = Request(
        f"{BASE_URL}{RANKING_PATH}",
        headers={"User-Agent": "AgenticCharacterStudio/0.1 (public ranking snapshot)"},
    )
    with urlopen(request, timeout=20) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.netloc != "melting.chat" or final.path != RANKING_PATH:
            raise ValueError("Melting ranking request redirected to an unexpected page")
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError("Melting ranking response is not HTML")
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise ValueError("Melting ranking response exceeds the size limit")
    return parse_rising_ranking(body.decode("utf-8"))


def collect_rising_ranking(session: Session) -> tuple[int, int]:
    """Fetch once and stage one complete snapshot in the caller's transaction."""
    profile = get_enabled_api_profile(session, source=SOURCE, profile_key=PROFILE_KEY)
    if (
        profile.base_url != BASE_URL
        or profile.ranking_path != RANKING_PATH
        or profile.response_format != "html"
    ):
        raise ValueError("The enabled Melting profile does not match the verified public page")
    characters = fetch_rising_ranking()
    require_valid_melting_ranking(characters, expected_count=EXPECTED_RANKS)
    snapshot = store_ranking_snapshot(
        session,
        source=SOURCE,
        ranking_type=RANKING_TYPE,
        collected_at=datetime.now(timezone.utc),
        characters=characters,
    )
    return snapshot.id, len(characters)
