from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.collectors.melting import collect_rising_ranking
from app.services.change_detector import detect_ranking_changes, summarize_events


load_local_env()
with session_scope() as session:
    snapshot_id, count = collect_rising_ranking(session)
    events = detect_ranking_changes(session, snapshot_id=snapshot_id)
    print(f"Saved Melting ranking snapshot {snapshot_id} with {count} characters.")
    print(f"Detected {len(events)} events: {summarize_events(events)}")
