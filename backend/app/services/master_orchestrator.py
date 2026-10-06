"""Constrained Gemini planner that dispatches the available market specialist agents."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgentTask, OrchestrationRun, RankingEntry, RankingEvent, RankingSnapshot
from app.services.ai_agents import (
    run_character_profile_agent,
    run_creator_intelligence_agent,
    run_genre_trend_agent,
    run_opportunity_finder_agent,
    run_ranking_summary_agent,
    run_review_comment_miner_agent,
)
from app.services.gemini_client import generate_json


INSTRUCTIONS = {
    "ranking_summary": "저장된 TOP10 순위와 변동 이벤트를 요약한다.",
    "character_profile": "현재 1위 캐릭터의 공개 프로필을 분석한다.",
    "opportunity_finder": "상위 5개 공개 프로필에서 검증 전 기획 가설을 찾는다.",
    "creator_intelligence": "상위 10개 공개 프로필에서 창작 패턴을 분석한다.",
    "genre_trend": "상위 10개 공개 프로필의 장르와 설정 신호를 분류한다.",
    "review_comment_miner": "사용자가 제공한 공개·동의 댓글 CSV에서 반복 의견을 분석한다.",
}


def _validate_plan(plan: dict) -> list[str]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != len(INSTRUCTIONS):
        raise ValueError("Master plan must assign every available agent")
    if any(not isinstance(item, str) for item in tasks) or set(tasks) != set(INSTRUCTIONS):
        raise ValueError("Master plan contains an unknown or duplicate agent")
    reason = plan.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Master plan needs a reason")
    return tasks


def run_market_cycle(session: Session, *, snapshot_id: int, comments_csv: str | None = None) -> OrchestrationRun:
    snapshot = session.get(RankingSnapshot, snapshot_id)
    if snapshot is None or snapshot.source != "melting" or snapshot.ranking_type != "rising_popular":
        raise LookupError("Melting ranking snapshot was not found")
    top_character_id = session.scalar(
        select(RankingEntry.character_id).where(RankingEntry.snapshot_id == snapshot_id, RankingEntry.rank == 1)
    )
    entry_count = session.scalar(select(func.count()).select_from(RankingEntry).where(RankingEntry.snapshot_id == snapshot_id))
    if top_character_id is None or entry_count != 50:
        raise ValueError("Master orchestration requires a complete 50-character snapshot")
    event_count = session.scalar(select(func.count()).select_from(RankingEvent).where(RankingEvent.snapshot_id == snapshot_id))

    run = OrchestrationRun(snapshot_id=snapshot_id, status="planning")
    session.add(run)
    session.flush()
    prompt = (
        "당신은 Agentic Character Studio의 마스터 오케스트레이터다. 이번 시장 분석 사이클에서 "
        "전문 에이전트 여섯 모두에게 한 번씩 작업을 배정하라. 안전한 실행 순서를 정하고 간단한 이유를 적어라. "
        "사용 가능한 에이전트는 ranking_summary(순위 변동 요약), character_profile(1위 공개 프로필 분석), "
        "opportunity_finder(상위 5개 기반 기획 가설), creator_intelligence(상위 10개 창작 패턴), "
        "genre_trend(상위 10개 장르 신호), review_comment_miner(제공된 CSV 댓글 분석)뿐이다. "
        "댓글 CSV가 없으면 review_comment_miner 작업은 시스템이 skipped로 기록한다. 새로운 에이전트나 외부 행동을 만들지 마라. "
        "반드시 JSON 객체만 반환: tasks(여섯 에이전트 이름을 중복 없이 넣은 문자열 배열), reason(문자열). "
        f"입력: snapshot_id={snapshot_id}, entry_count={entry_count}, event_count={event_count}, comments_csv_available={bool(comments_csv)}."
    )
    try:
        plan = generate_json(prompt)
        order = _validate_plan(plan)
    except Exception as exc:
        run.status = "failed"
        run.error_type = type(exc).__name__
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        return run

    run.plan_json = plan
    run.status = "running"
    tasks = []
    for sequence, agent_type in enumerate(order, start=1):
        task = AgentTask(
            run_id=run.id,
            sequence=sequence,
            agent_type=agent_type,
            instruction=INSTRUCTIONS[agent_type],
            status="pending",
        )
        session.add(task)
        tasks.append(task)
    session.flush()

    for task in tasks:
        if task.agent_type == "review_comment_miner" and not comments_csv:
            task.status = "skipped"
            task.error_type = "COMMENTS_CSV_NOT_PROVIDED"
            task.finished_at = datetime.now(timezone.utc)
            session.flush()
            continue
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        session.flush()
        try:
            with session.begin_nested():
                if task.agent_type == "ranking_summary":
                    analysis = run_ranking_summary_agent(session, snapshot_id=snapshot_id)
                elif task.agent_type == "character_profile":
                    analysis = run_character_profile_agent(
                        session, snapshot_id=snapshot_id, character_id=top_character_id
                    )
                elif task.agent_type == "opportunity_finder":
                    analysis = run_opportunity_finder_agent(session, snapshot_id=snapshot_id)
                elif task.agent_type == "creator_intelligence":
                    analysis = run_creator_intelligence_agent(session, snapshot_id=snapshot_id)
                elif task.agent_type == "genre_trend":
                    analysis = run_genre_trend_agent(session, snapshot_id=snapshot_id)
                else:
                    analysis = run_review_comment_miner_agent(
                        session, snapshot_id=snapshot_id, csv_path=comments_csv
                    )
                session.flush()
            task.analysis_id = analysis.id
            task.status = "completed"
        except Exception as exc:
            task.status = "failed"
            task.error_type = type(exc).__name__
        task.finished_at = datetime.now(timezone.utc)
        session.flush()

    run.status = "completed" if all(task.status in {"completed", "skipped"} for task in tasks) else "failed"
    run.finished_at = datetime.now(timezone.utc)
    session.flush()
    return run
