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
