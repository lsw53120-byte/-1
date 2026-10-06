import os
from pathlib import Path


def load_local_env() -> None:
    """Load this project's local database URL without replacing an existing setting."""
    if os.getenv("DATABASE_URL"):
        return
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        raise RuntimeError(f"Local configuration was not found: {env_path}")
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("DATABASE_URL="):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1]
            return
    raise RuntimeError("DATABASE_URL is missing from .env")
