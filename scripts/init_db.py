from app.core.database import Base, make_engine
from app.core.local_env import load_local_env
import app.models  # noqa: F401 - register model tables


def main() -> None:
    load_local_env()
    engine = make_engine()
    try:
        Base.metadata.create_all(engine)
        print("Database tables are ready.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
