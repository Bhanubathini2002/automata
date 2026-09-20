# Automata — PRODUCTION (ship-ready, not a paid product)

You are in C:\R@D_projects\automata. Goal: production-grade Job Search Automation that is ready to ship and run. Not a demo, not an MVP, not a paid/commercial product pitch.

## Product
**Automata** — https://github.com/Bhanubathini2002/automata
Local path: C:\R@D_projects\automata

## Scope (locked)
- Post-scrape only. User brings jobs Excel. NO Jobright/scraper.
- End-to-end: filter → addresses → JD fetch → LaTeX resume+cover → Tier A Playwright apply → Excel status.
- First-run Streamlit UI explains workflow and collects ALL inputs (jobs Excel, addresses Excel, base resume/cover .tex, ATS prompt, LLM key, CapSolver key, email+password, Chrome profile).

## Production bar
1. Professional Streamlit UI — clear copy, progress, error states. No "MVP", no "buy", no pricing.
2. Real runnable code — no empty stubs for filter, addresses, JD, resume, apply.
3. Safety: auth Yes / sponsorship No; skip citizen/GC/clearance/ITAR; NEVER SSN/DOB; mark applied only after confirmed success.
4. Secrets in .env only; never commit secrets.
5. Sequential apply; resume mid-batch from Excel status; structured statuses.
6. requirements.txt + README (Windows + Linux). Optional pyproject.toml.
7. pytest for fieldmap safety + filter + config; tests must pass.
8. MIT LICENSE. README + short docs/USER_GUIDE.md.
9. Strip BUILD_PROMPT.md, VALIDATE_PROMPT.md, SHIP_PROMPT.md, _refs/, logs from public commit (gitignore).

## Finish
- Harden modules; remove MVP/buy language everywhere.
- Run pytest; fix failures.
- git add → commit "release: Automata 1.0.0" → push -u origin main
- Print test results, commit SHA, https://github.com/Bhanubathini2002/automata


# CRITICAL ADDITIONS for Automata (production) — apply NOW on top of current work

## 1) LaTeX is REQUIRED for resume/cover PDFs
- Do NOT pretend PDFs appear without a TeX engine.
- Detect `xelatex` and `pdflatex` on PATH (and common MiKTeX / TeX Live Windows paths).
- On first-run UI: show LaTeX status (found path / NOT FOUND) with clear install steps for MiKTeX (Windows) and TeX Live (Linux/Mac).
- `pipeline/resume_engine/render.py` must: compile .tex → PDF, fail with a clear actionable error if LaTeX missing, never silently skip.
- Config keys: XELATEX, PDFLATEX (env + UI).
- README: mandatory LaTeX install section before "generate resumes".
- Optional: `python -m pipeline.run doctor` that checks Python deps + Playwright + LaTeX + .env keys.

## 2) Persistence must be excellent across the whole workflow
- **Chrome/browser**: always use a durable user-data-dir (default `./data/browser_state` or user-chosen path). Same profile for apply + Gmail OTP/magic links. Document: log into Gmail once in that profile; sessions survive restarts.
- **Excel status**: never re-apply rows already marked `applied` / terminal skip statuses; resume mid-batch from the Excel status column after crash/restart.
- **Config**: `data/config.yaml` + `.env` persist all paths/keys; UI reload shows last saved values.
- **Job folders**: per-job resume/cover/JD artifacts stay on disk; re-running a stage skips work already done unless `--force`.
- **Apply checkpoint**: after each job, flush Excel status to disk immediately (no batch-end-only writes).
- **Idempotent stages**: filter/addresses/jd/resume/apply can be re-run safely; pick up where left off.

## 3) Finish
Implement the above for real (not stubs). Keep no "buy"/MVP language.
Then: pytest + doctor, commit, push to origin main.
Print what you changed for LaTeX + persistence.

