Validate Automata at C:\R@D_projects\automata for PRODUCTION ship-ready (not MVP, not a paid product).

MUST VERIFY / FIX:
1. LaTeX: find_xelatex/find_pdflatex have no hardcoded usernames; build fails clearly without compilers; UI shows LaTeX status; `python -m pipeline.run doctor` works; README has mandatory LaTeX install before resume generation.
2. Persistence: default Chrome profile data/browser_state; apply skips terminal statuses; Excel flushed after each job; stages idempotent with --force; config.yaml+.env reload in UI.
3. Safety tests pass: pytest or python -m unittest discover -s tests
4. No Jobright scraper. No secrets in repo.
5. Remove *PROMPT*.md, FULL_SHIP.md, logs, _refs from commit (gitignore).
6. Commit "release: Automata 1.0.0" and push -u origin main to https://github.com/Bhanubathini2002/automata
7. Do NOT commit .venv or .pytest_cache

Report pass/fail + commit SHA + repo URL.
