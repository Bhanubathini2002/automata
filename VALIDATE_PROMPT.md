Validate the Automata repo at C:\R@D_projects\automata (Job Search Automation, post-scrape only).

Check and FIX if needed:
1. python -m pipeline.run --help works (create venv + pip install -r requirements.txt if needed)
2. ui/app.py imports (streamlit heading Automata, setup wizard fields present)
3. No Jobright/scraper code
4. Apply hard rules: never SSN/DOB; skip citizen/ITAR/clearance; auth Yes / sponsorship No
5. .gitignore covers .env, chrome_profile, secrets
6. README paths say C:\R@D_projects\automata and github.com/Bhanubathini2002/automata
7. Remove BUILD_PROMPT.md and claude-build.log from tracked files if present

Then: git add all (respecting gitignore), commit "feat: Automata MVP — filter, tailor, Tier A apply UI", push -u origin main.

Report: pass/fail list, commit sha, push URL.
