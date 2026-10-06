import threading
from queue import Empty, Queue
import tkinter as tk
import webbrowser
from datetime import timezone, timedelta
from tkinter import filedialog, messagebox, ttk

from app.collectors.melting import collect_rising_ranking
from app.core.database import session_scope
from app.core.local_env import load_local_env
from app.services.change_detector import detect_ranking_changes
from app.services.dashboard_data import DashboardData, RankingRow, load_dashboard_data
from app.services.ai_agents import (run_character_profile_agent, run_opportunity_finder_agent,
    run_ranking_summary_agent, run_creator_intelligence_agent, run_genre_trend_agent,
    run_review_comment_miner_agent)
from app.services.master_orchestrator import run_market_cycle


KST = timezone(timedelta(hours=9))
EVENT_LABELS = {
    "NEW_CHARACTER": "신규",
    "ENTER_TOP50": "TOP50 진입",
    "ENTER_TOP10": "TOP10 진입",
    "SURGE": "급등",
    "DECLINE": "하락",
}


class StudioDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("멜팅 랭킹 스튜디오")
        self.geometry("1120x760")
        self.minsize(850, 600)
        self.configure(bg="#fff8f2")
        self._rows: dict[str, RankingRow] = {}
        self._snapshot_id: int | None = None
        self._busy = False
        self._result_queue: Queue = Queue()
        self._build()
        self.after(50, self._poll_results)
        self.refresh()

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Ranking.Treeview", background="#fffdf9", fieldbackground="#fffdf9", foreground="#352b32", rowheight=32, font=("Malgun Gothic", 10))
        style.configure("Ranking.Treeview.Heading", background="#f5e5dd", foreground="#5b3d45", font=("Malgun Gothic", 10, "bold"))
        style.map("Ranking.Treeview", background=[("selected", "#f2c8b7")], foreground=[("selected", "#352b32")])

        header = tk.Frame(self, bg="#6d3e53", padx=28, pady=22)
        header.pack(fill="x")
        tk.Label(header, text="✦ 멜팅 랭킹 스튜디오", bg="#6d3e53", fg="white", font=("Malgun Gothic", 20, "bold")).pack(anchor="w")
        tk.Label(header, text="공개 라이징 인기 랭킹의 흐름을 한눈에", bg="#6d3e53", fg="#f8dcd9", font=("Malgun Gothic", 10)).pack(anchor="w", pady=(4, 0))

        controls = tk.Frame(self, bg="#fff8f2", padx=28, pady=16)
        controls.pack(fill="x")
        self.summary = tk.Label(controls, text="데이터를 불러오는 중…", bg="#fff8f2", fg="#51434a", font=("Malgun Gothic", 11, "bold"))
        self.summary.pack(side="left")
        self.collect_button = tk.Button(controls, text="지금 수집", command=self.collect, bg="#b8636d", fg="white", activebackground="#9f505d", relief="flat", padx=18, pady=9, font=("Malgun Gothic", 10, "bold"))
        self.collect_button.pack(side="right")
        self.master_button = tk.Button(controls, text="마스터 실행", command=self.run_master, bg="#d5b7c5", fg="#352b32", relief="flat", padx=12, pady=9, font=("Malgun Gothic", 10, "bold"))
        self.master_button.pack(side="right", padx=(0, 8))
        tk.Button(controls, text="새로고침", command=self.refresh, bg="#e9d8cb", fg="#493940", relief="flat", padx=16, pady=9, font=("Malgun Gothic", 10)).pack(side="right", padx=(0, 8))

        agent_controls = tk.Frame(self, bg="#fff8f2", padx=28, pady=4)
        agent_controls.pack(fill="x")
        self.summary_button = tk.Button(agent_controls, text="AI 변동 요약", command=self.analyze_ranking, bg="#e9d8cb", fg="#493940", relief="flat", padx=12, pady=9, font=("Malgun Gothic", 10))
        self.summary_button.pack(side="left", padx=(0, 8))
        self.opportunity_button = tk.Button(agent_controls, text="기회 영역 탐색", command=self.analyze_opportunities, bg="#e9d8cb", fg="#493940", relief="flat", padx=12, pady=9, font=("Malgun Gothic", 10))
        self.opportunity_button.pack(side="left", padx=(0, 8))
        self.creator_button = tk.Button(agent_controls, text="창작 패턴", command=self.analyze_creators, bg="#e9d8cb", fg="#493940", relief="flat", padx=12, pady=9)
        self.creator_button.pack(side="left", padx=(0, 8))
        self.genre_button = tk.Button(agent_controls, text="장르 신호", command=self.analyze_genres, bg="#e9d8cb", fg="#493940", relief="flat", padx=12, pady=9)
        self.genre_button.pack(side="left", padx=(0, 8))
        self.review_button = tk.Button(agent_controls, text="댓글 CSV", command=self.analyze_reviews, bg="#e9d8cb", fg="#493940", relief="flat", padx=12, pady=9)
        self.review_button.pack(side="left")

        event_frame = tk.Frame(self, bg="#fff8f2", padx=28)
        event_frame.pack(fill="x")
        self.event_summary = tk.Label(event_frame, text="", bg="#fff8f2", fg="#8b5965", font=("Malgun Gothic", 10))
        self.event_summary.pack(anchor="w")

        table_frame = tk.Frame(self, bg="#fff8f2", padx=28, pady=16)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=("rank", "name", "previous", "change", "events"), show="headings", style="Ranking.Treeview")
        for column, title, width, anchor in (
            ("rank", "순위", 70, "center"),
            ("name", "캐릭터", 390, "w"),
            ("previous", "이전", 80, "center"),
            ("change", "변화", 80, "center"),
            ("events", "감지 결과", 300, "w"),
        ):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, anchor=anchor, stretch=column in {"name", "events"})
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self._show_selected)

        footer = tk.Frame(self, bg="#f5e9e1", padx=28, pady=12)
        footer.pack(fill="x")
        self.detail = tk.Label(footer, text="캐릭터를 선택하면 원본 페이지를 열 수 있습니다.", bg="#f5e9e1", fg="#51434a", anchor="w", font=("Malgun Gothic", 10))
        self.detail.pack(side="left", fill="x", expand=True)
        self.open_button = tk.Button(footer, text="캐릭터 보기 ↗", command=self._open_selected, state="disabled", bg="#d9b8ab", fg="#382d34", relief="flat", padx=12, pady=7, font=("Malgun Gothic", 9))
        self.open_button.pack(side="right")
        self.profile_button = tk.Button(footer, text="AI 프로필 분석", command=self.analyze_profile, state="disabled", bg="#d9b8ab", fg="#382d34", relief="flat", padx=12, pady=7, font=("Malgun Gothic", 9))
        self.profile_button.pack(side="right", padx=(0, 8))
        self.status = tk.Label(self, text="", bg="#fff8f2", fg="#7b6d72", anchor="w", padx=28, pady=7, font=("Malgun Gothic", 9))
        self.status.pack(fill="x")

    def _run_background(self, operation, success_message, *, refresh_after=False):
        if self._busy:
            return
        self._busy = True
        self.collect_button.configure(state="disabled")
        self.summary_button.configure(state="disabled")
        self.opportunity_button.configure(state="disabled")
        self.master_button.configure(state="disabled")
        self.profile_button.configure(state="disabled")
        for button in (self.genre_button, self.creator_button, self.review_button):
            button.configure(state="disabled")
        self.status.configure(text="작업 중입니다…")

        def worker():
            try:
                load_local_env()
                with session_scope() as session:
                    message = operation(session)
                self._result_queue.put((True, message, success_message, refresh_after))
            except Exception as exc:
                self._result_queue.put((False, str(exc), None, False))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_results(self):
        try:
            while True:
                succeeded, payload, success_message, refresh_after = self._result_queue.get_nowait()
                if succeeded:
                    self._finished(success_message(payload), refresh_after=refresh_after)
                else:
                    self._failed(payload)
        except Empty:
            pass
        self.after(50, self._poll_results)

    def _finished(self, message, *, refresh_after=False):
        self._busy = False
        self.collect_button.configure(state="normal")
        self.summary_button.configure(state="normal")
        self.opportunity_button.configure(state="normal")
        self.master_button.configure(state="normal")
        for button in (self.genre_button, self.creator_button, self.review_button):
            button.configure(state="normal")
        self.status.configure(text=message)
        self._show_selected()
        if refresh_after:
            self.refresh()

    def _failed(self, error):
        self._busy = False
        self.collect_button.configure(state="normal")
        self.summary_button.configure(state="normal")
        self.opportunity_button.configure(state="normal")
        self.master_button.configure(state="normal")
        for button in (self.genre_button, self.creator_button, self.review_button):
            button.configure(state="normal")
        self.status.configure(text=f"오류: {error}")
        self._show_selected()
        messagebox.showerror("작업을 완료하지 못했습니다", f"{error}\n\nDocker Desktop과 PostgreSQL 컨테이너가 실행 중인지 확인해 주세요.")

    def refresh(self):
        def operation(session):
            return load_dashboard_data(session)
        self._run_background(operation, lambda data: self._render(data))

    def collect(self):
        def operation(session):
            snapshot_id, count = collect_rising_ranking(session)
            events = detect_ranking_changes(session, snapshot_id=snapshot_id)
            return snapshot_id, count, len(events)
        self._run_background(operation, lambda result: f"수집 완료: {result[1]}개 캐릭터, 변동 {result[2]}건 (스냅샷 #{result[0]})", refresh_after=True)

    def analyze_ranking(self):
        if self._snapshot_id is None:
            messagebox.showinfo("분석할 데이터 없음", "먼저 랭킹을 수집해 주세요.")
            return
        snapshot_id = self._snapshot_id
        self._run_background(
            lambda session: run_ranking_summary_agent(session, snapshot_id=snapshot_id).output_json,
            lambda result: self._show_analysis("AI 순위 변동 요약", result),
        )

    def analyze_opportunities(self):
        if self._snapshot_id is None:
            messagebox.showinfo("분석할 데이터 없음", "먼저 랭킹을 수집해 주세요.")
            return
        snapshot_id = self._snapshot_id
        self._run_background(
            lambda session: run_opportunity_finder_agent(session, snapshot_id=snapshot_id).output_json,
            lambda result: self._show_analysis("기회 영역 탐색 · 기획 가설", result),
        )

    def analyze_creators(self):
        if self._snapshot_id is None:
            messagebox.showinfo("분석할 데이터 없음", "먼저 랭킹을 수집해 주세요.")
            return
        snapshot_id = self._snapshot_id
        self._run_background(lambda session: run_creator_intelligence_agent(session, snapshot_id=snapshot_id).output_json,
                             lambda result: self._show_analysis("창작 패턴", result))

    def analyze_genres(self):
        if self._snapshot_id is None:
            messagebox.showinfo("분석할 데이터 없음", "먼저 랭킹을 수집해 주세요.")
            return
        snapshot_id = self._snapshot_id
        self._run_background(lambda session: run_genre_trend_agent(session, snapshot_id=snapshot_id).output_json,
                             lambda result: self._show_analysis("장르 신호", result))

    def analyze_reviews(self):
        if self._snapshot_id is None:
            messagebox.showinfo("분석할 데이터 없음", "먼저 랭킹을 수집해 주세요.")
            return
        path = filedialog.askopenfilename(title="댓글 CSV 선택", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        snapshot_id = self._snapshot_id
        self._run_background(lambda session: run_review_comment_miner_agent(session, snapshot_id=snapshot_id, csv_path=path).output_json,
                             lambda result: self._show_analysis("댓글 분석", result))

    def run_master(self):
        if self._snapshot_id is None:
            messagebox.showinfo("실행할 데이터 없음", "먼저 랭킹을 수집해 주세요.")
            return
        snapshot_id = self._snapshot_id
        comments_csv = None
        if messagebox.askyesno(
            "댓글 분석은 선택 사항",
            "댓글 CSV도 함께 분석할까요?\n\n"
            "예: 공개 댓글이 담긴 CSV 파일을 선택합니다.\n"
            "아니요: 파일 없이 나머지 5개 에이전트를 실행합니다.",
        ):
            comments_csv = filedialog.askopenfilename(
                title="댓글 CSV 선택 (취소하면 댓글 분석을 건너뜁니다)",
                filetypes=[("CSV", "*.csv")],
            ) or None

        def operation(session):
            run = run_market_cycle(session, snapshot_id=snapshot_id, comments_csv=comments_csv)
            return {
                "run_id": run.id,
                "status": run.status,
                "reason": (run.plan_json or {}).get("reason", "계획을 만들지 못했습니다."),
                "tasks": [
                    f"{task.sequence}. {task.instruction} → {task.status} (결과 #{task.analysis_id or '없음'}"
                    f"{', 사유: ' + task.error_type if task.error_type else ''})"
                    for task in sorted(run.tasks, key=lambda item: item.sequence)
                ],
                "error": run.error_type or "",
            }

        self._run_background(operation, lambda result: self._show_master_run(result))

    def _show_master_run(self, result: dict) -> str:
        lines = "\n".join(result["tasks"]) or "배정된 작업 없음"
        messagebox.showinfo(
            "마스터 실행 결과",
            f"실행 #{result['run_id']} · {result['status']}\n\n"
            f"실행 이유: {result['reason']}\n\n에이전트 명령과 결과:\n{lines}"
            + (f"\n\n오류 유형: {result['error']}" if result["error"] else ""),
        )
        return f"마스터 실행 #{result['run_id']}: {result['status']}"

    def analyze_profile(self):
        selected = self.table.selection()
        row = self._rows.get(selected[0]) if selected else None
        if row is None or self._snapshot_id is None:
            return
        snapshot_id, character_id, name = self._snapshot_id, row.character_id, row.name
        self._run_background(
            lambda session: run_character_profile_agent(session, snapshot_id=snapshot_id, character_id=character_id).output_json,
            lambda result: self._show_analysis(f"AI 캐릭터 분석 · {name}", result),
        )

    def _show_analysis(self, title: str, result: dict) -> str:
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("680x580")
        window.configure(bg="#fff8f2")
        text = tk.Text(window, wrap="word", bg="#fffdf9", fg="#352b32", relief="flat", padx=22, pady=20, font=("Malgun Gothic", 11))
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        labels = {
            "summary": "요약", "highlights": "핵심 변화", "uncertainty": "확인 범위",
            "concept": "콘셉트", "appeal_points": "매력 요소", "audience_hypotheses": "독자 반응 가설", "evidence": "공개 프로필 근거",
            "observed_signals": "관찰된 특징", "opportunity_hypotheses": "캐릭터 기획 가설", "next_checks": "추가로 확인할 것", "limitations": "판단 범위",
            "patterns": "창작 패턴", "creator_tips": "창작 참고점", "genre_signals": "장르 신호",
            "setting_signals": "설정 신호", "themes": "반복 의견", "positive_points": "호평",
            "concerns": "우려",
        }
        for key, value in result.items():
            text.insert("end", f"{labels.get(key, key)}\n", "heading")
            if isinstance(value, list):
                if not value:
                    text.insert("end", "현재 제안 없음\n")
                for line in value:
                    text.insert("end", f"• {line}\n")
            else:
                text.insert("end", f"{value}\n")
            text.insert("end", "\n")
        text.tag_configure("heading", font=("Malgun Gothic", 12, "bold"), foreground="#9f505d")
        text.configure(state="disabled")
        return f"{title}을 완료했습니다."

    def _render(self, data: DashboardData):
        for item in self.table.get_children():
            self.table.delete(item)
        self._rows.clear()
        self._snapshot_id = data.snapshot_id
        self.open_button.configure(state="disabled")
        if data.snapshot_id is None:
            self.summary.configure(text="저장된 랭킹이 없습니다. ‘지금 수집’을 눌러 시작하세요.")
            self.event_summary.configure(text="")
            return "아직 수집된 데이터가 없습니다."
        time_text = data.collected_at.astimezone(KST).strftime("%Y-%m-%d %H:%M") if data.collected_at else "시간 미상"
        self.summary.configure(text=f"최근 수집  {time_text}  ·  {len(data.rows)}개 캐릭터")
        self.event_summary.configure(text="   ·   ".join(f"{label} {data.event_counts.get(key, 0)}" for key, label in EVENT_LABELS.items()))
        for row in data.rows:
            previous = str(row.previous_rank) if row.previous_rank is not None else "—"
            change = "—" if row.previous_rank is None else (f"↑{row.previous_rank - row.rank}" if row.previous_rank > row.rank else (f"↓{row.rank - row.previous_rank}" if row.previous_rank < row.rank else "=") )
            labels = ", ".join(EVENT_LABELS.get(event, event) for event in row.events)
            item_id = self.table.insert("", "end", values=(row.rank, row.name, previous, change, labels))
            self._rows[item_id] = row
        return f"스냅샷 #{data.snapshot_id}을 표시하고 있습니다."

    def _show_selected(self, _event=None):
        selected = self.table.selection()
        row = self._rows.get(selected[0]) if selected else None
        if row:
            self.detail.configure(text=f"{row.rank}위 · {row.name}  |  {row.source_url}")
            self.open_button.configure(state="normal")
            self.profile_button.configure(state="normal")

    def _open_selected(self):
        selected = self.table.selection()
        row = self._rows.get(selected[0]) if selected else None
        if row:
            webbrowser.open(row.source_url)


def main():
    StudioDashboard().mainloop()


if __name__ == "__main__":
    main()
