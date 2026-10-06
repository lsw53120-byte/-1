import re
from dataclasses import dataclass
from collections.abc import Sequence

from app.services.ranking_snapshots import RankedCharacter


CHARACTER_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CHARACTER_URL_PREFIX = "https://melting.chat/ko/app/characters/"
POLICY_VERSION = "melting-rising-v1"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    policy_version: str
    item_count: int
    issues: tuple[ValidationIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


class RankingValidationError(ValueError):
    def __init__(self, report: ValidationReport):
        self.report = report
        message = "; ".join(f"{issue.code}: {issue.detail}" for issue in report.issues)
        super().__init__(f"Melting ranking validation failed: {message}")


def validate_melting_ranking(
    characters: Sequence[RankedCharacter], *, expected_count: int = 50
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if len(characters) != expected_count:
        issues.append(ValidationIssue("COUNT", f"expected {expected_count}, found {len(characters)}"))

    ranks = [item.rank for item in characters]
    if any(type(rank) is not int for rank in ranks) or sorted(ranks) != list(range(1, expected_count + 1)):
        issues.append(ValidationIssue("RANKS", f"expected each rank 1-{expected_count} exactly once"))

    ids = [item.source_character_id for item in characters]
    if len(ids) != len(set(ids)):
        issues.append(ValidationIssue("DUPLICATE_ID", "character IDs repeat within the ranking"))

    for position, item in enumerate(characters, start=1):
        if not CHARACTER_ID.fullmatch(item.source_character_id):
            issues.append(ValidationIssue("CHARACTER_ID", f"item {position} has an invalid ID"))
        if item.source_url != f"{CHARACTER_URL_PREFIX}{item.source_character_id}":
            issues.append(ValidationIssue("SOURCE_URL", f"item {position} has a noncanonical URL"))
        name = item.name.strip()
        if not name or len(name) > 300 or any(ord(char) < 32 for char in name):
            issues.append(ValidationIssue("NAME", f"item {position} has an invalid name"))

    return ValidationReport(POLICY_VERSION, len(characters), tuple(issues))


def require_valid_melting_ranking(
    characters: Sequence[RankedCharacter], *, expected_count: int = 50
) -> ValidationReport:
    report = validate_melting_ranking(characters, expected_count=expected_count)
    if not report.passed:
        raise RankingValidationError(report)
    return report
