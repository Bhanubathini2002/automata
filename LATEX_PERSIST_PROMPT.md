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
