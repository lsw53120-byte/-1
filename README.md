# Agentic Character Studio

Public Melting rankings → PostgreSQL snapshots → rank change detection → separate Gemini analysis agents.

## Open the results screen

Double-click `멜팅_랭킹_스튜디오.cmd` in this folder. The screen shows the latest 50 characters, previous ranks, and detected changes. Use **지금 수집** to collect once, **마스터 실행** to dispatch the five ranking/profile specialists and the optional CSV comment specialist, or use an individual analysis button. Docker Desktop and the PostgreSQL container must be running while you use the screen.

## Step 1: PostgreSQL and tables

1. Copy `.env.example` to `.env`. Change `POSTGRES_PASSWORD` and make the password in `DATABASE_URL` match. If the password contains URL special characters, URL-encode it in `DATABASE_URL`.
2. From this directory, run `docker compose up -d postgres`.
3. Create a Python 3.11+ virtual environment, activate it, and run `python -m pip install -e .`.
4. Load `DATABASE_URL` from `.env` into your shell, then run `python scripts/init_db.py`.

PowerShell example for step 4:

```powershell
$env:DATABASE_URL = (Get-Content .env | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=', ''
python scripts/init_db.py
```

Tables: `characters` identifies a character by source ID; `ranking_snapshots` records each collection time and ranking type; `ranking_entries` stores one rank per character in a snapshot. Unique constraints prevent duplicate characters or ranks within a snapshot.

## Step 2: Ranking snapshot storage

`app.services.ranking_snapshots.store_ranking_snapshot` accepts one complete ranking with a timezone-aware collection time. It validates unique character IDs and ranks, updates known character names and URLs, and stores entries in the caller's transaction. Call it inside a session transaction so a failed collection cannot leave a partial ranking.

To run the PostgreSQL integration test after loading `DATABASE_URL`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

The test rolls back its sample data.

## Step 3: API profile registry

`app.repositories.api_profiles.upsert_api_profile` stores the public source origin, ranking path, response format (`html` or `json`), and enabled state. `get_enabled_api_profile` retrieves only active profiles. Credentials are not stored, and registering a profile makes no request to the source. Profiles start disabled by default; enable one only after its endpoint and parser have been verified.

Run `python scripts/init_db.py` again to create the new `api_profiles` table, then run the integration tests above.

## Step 4: Melting public ranking collector

The collector reads the public [Melting rising popularity ranking](https://melting.chat/ko/app/challenge). It accepts only the verified Melting HTTPS page and stores a snapshot only when all 50 distinct ranks and character IDs are present. It does not sign in or call an AI API.

After loading `DATABASE_URL`, register the verified source profile once and collect a snapshot. Collection also runs the validator and change detector in the same database transaction:

```powershell
.\.venv\Scripts\python.exe scripts/register_melting_profile.py
.\.venv\Scripts\python.exe scripts/collect_melting.py
```

The service stages the snapshot in one database transaction. If fetching or parsing fails, no snapshot is committed. Run the unit and PostgreSQL integration tests with the command in Step 2.

## Step 5: Validator

Before saving, the collector runs `validate_melting_ranking` using fixed policy `melting-rising-v1`. It requires 50 distinct character IDs, ranks 1–50 exactly once, canonical Melting character URLs, and nonempty names within the database limit. A failure reports issue codes and prevents a partial or invalid snapshot from being committed.

To check the most recent saved snapshot against the same policy:

```powershell
.\.venv\Scripts\python.exe scripts/validate_latest_snapshot.py
```

## Step 6: Change detector

`detect_ranking_changes` compares a snapshot with the immediately preceding snapshot of the same source and ranking type. The first snapshot is a baseline and creates no events. Later snapshots can record multiple events for one character: `NEW_CHARACTER` (never seen in earlier snapshots), `ENTER_TOP50` (absent from the previous top 50), `ENTER_TOP10`, `SURGE`, and `DECLINE`. A character that disappears from the current top 50 receives `DECLINE` with no known current rank. For characters present in both snapshots, a rise or fall of at least 10 places triggers `SURGE` or `DECLINE`. These thresholds are configurable in code. Repeating detection for the same snapshot does not duplicate events.

After loading `DATABASE_URL`, run `python scripts/init_db.py` to create the `ranking_events` table, then:

```powershell
.\.venv\Scripts\python.exe scripts/detect_changes.py
```

Pass a snapshot ID as an argument to inspect an older snapshot.

## Daily collection

The Codex app automation **멜팅 랭킹 매일 10시 수집** is paused. The GitHub Actions workflow is scheduled daily at 10:00 Asia/Seoul. The scheduled job does not run Gemini analysis; those calls are available on demand in the results screen.

The GitHub Actions workflow collects while the computer is off when its online PostgreSQL database and repository secret are configured. See [cloud setup](docs/cloud-collection.md). Keep the local Codex automation paused to avoid duplicate collections.

## Gemini specialist agents

The ranking summary agent uses only the saved top 10 and ranking events. The character profile agent reads only the selected character's public Melting description. Their outputs are stored separately in `ai_analyses` and reused for the same input and model. They do not change rankings or character records. API requests use the `GEMINI_API_KEY` environment variable and the optional `GEMINI_MODEL` variable (default `gemini-3.5-flash-lite`). Never put the key in `.env`, source files, or chat messages.

Set a valid `GEMINI_API_KEY` in Windows user environment variables, then restart the app or terminal that launches this project. To run both agents on the latest snapshot from the command line:

```powershell
.\.venv\Scripts\python.exe scripts/run_ai_agents.py
```

If the API returns HTTP 401, the key is not accepted for this request. Get or check the key in [Google AI Studio](https://aistudio.google.com/apikey) and update the user environment variable. Gemini model availability and quota can vary by account.

## Opportunity Finder

The third specialist reads the latest top-five public character descriptions and recorded top-ten rank events. It suggests up to three character planning hypotheses, names the observed evidence, and lists what further research is needed. Ranking positions do not measure total demand or genre supply, so its hypotheses are not validated market gaps. Results are saved separately in `ai_analyses` and can be opened from **기회 영역 탐색** in the results screen.

To run it from the command line:

```powershell
.\.venv\Scripts\python.exe scripts/find_opportunities.py
```

## Master orchestrator (market cycle)

This `agentic-character-studio` folder is the main project. The Creator Intelligence, Genre Trend, and Review / Comment Miner additions from the adjacent working copy are integrated here. Use this folder's launcher.

The Gemini master chooses an execution order for six available market specialists, then the dispatcher calls each agent in that order. The plan is checked against a fixed allowlist before execution. Each command and its completion, failure, or skip is recorded in `orchestration_runs` and `agent_tasks`, with a link to the specialist's saved `ai_analyses` result. An invalid plan dispatches no agents. Each specialist failure is recorded, and the other independent specialists can still run. Review / Comment Miner is skipped when no CSV is supplied.

Run `scripts/init_db.py` once to create the orchestration tables, then run the latest validated snapshot through the master:

```powershell
.\.venv\Scripts\python.exe scripts/run_master_orchestrator.py
```

The market cycle includes ranking summary, first-place character profile, opportunity hypotheses, creator intelligence, and genre signals. **마스터 실행** first asks whether to include comment analysis. Choose **아니요** to run the five agents without a file. Choose **예** to select a comment CSV; cancelling the file picker also skips the comment task. The creative, conversation, launch, and growth agents in the broader architecture are not implemented yet.

For the comment agent, use a UTF-8 CSV with `source_url,comment` headers, at most 200 nonempty rows, and a file size under 2 MB. Supply only public comments or comments you have permission to analyze; avoid names, handles, and other personal data. The CSV is sent to Gemini for this analysis. PostgreSQL stores the output and an input hash, not the raw CSV. The **댓글 CSV** button runs this specialist separately from the master.

For a live integration check of the master and all six specialists, run `scripts/verify_master_live.py`. It creates three clearly synthetic example comments in a temporary CSV, uses the latest saved ranking snapshot, then rolls back all test analysis rows and run records. A real comment analysis requires your own permitted CSV.
