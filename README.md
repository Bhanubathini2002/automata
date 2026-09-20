# Automata — Job Search Automation

Post-scrape pipeline: **jobs Excel → filter → addresses → JD fetch → LaTeX resume+cover PDFs → Tier A Playwright apply**.

No Jobright/scraper code in this package. Product name: **Automata**.

## Pipeline

| Stage | Module | What it does |
|-------|--------|--------------|
| Doctor | `pipeline/doctor.py` | Preflight: imports, Playwright, LaTeX, `.env` keys (presence only) |
| Filter | `pipeline/filter_jobs.py` | Dedupe, drop blocked companies & 6+ yrs, split by role |
| Addresses | `pipeline/addresses.py` | Address-book match, stage folders, write `*_updated.xlsx` |
| JD fetch | `pipeline/jd_fetch.py` | Split → fetch/distill → merge into Excel + `job.json` |
| Resume | `pipeline/resume_engine/` | 2 LLM calls/job → validate → **LaTeX compile → PDF** |
| Apply | `pipeline/apply_tier_a/` | Sequential Playwright, CapSolver, Gmail OTP |

**Apply hard rules:** skip ITAR/citizen/clearance · never SSN/DOB · mark `applied` only on confirmation · one-by-one sequential.

**Persistence:** stages skip already-done work unless `--force`. Apply skips terminal statuses and flushes Excel after **each** job (safe mid-batch resume).

---

## Mandatory: install LaTeX (before generate-resumes)

Resume and cover letter **PDFs require** `xelatex` and `pdflatex`. Automata will **fail clearly** if they are missing — it will never silently pretend a PDF exists.

### Windows — MiKTeX

1. Install from **https://miktex.org/**
2. Ensure `xelatex.exe` and `pdflatex.exe` are on PATH, or set overrides in `.env` / UI:
   ```
   XELATEX=%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\xelatex.exe
   PDFLATEX=%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe
   ```
3. Verify:
   ```powershell
   python -m pipeline.run doctor
   ```

### Linux — TeX Live

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install texlive-xetex texlive-latex-recommended texlive-fonts-recommended

# or full TeX Live: https://www.tug.org/texlive/
python -m pipeline.run doctor
```

### macOS — MacTeX

Install from **https://www.tug.org/mactex/** then re-run `doctor`.

Detection order: `XELATEX`/`PDFLATEX` env → `PATH` → common MiKTeX / TeX Live install locations (no hardcoded usernames).

---

## Windows install

```powershell
# 1. Clone
cd C:\R@D_projects
git clone https://github.com/Bhanubathini2002/automata.git
cd automata

# 2. Python venv
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
playwright install chromium

# 3. LaTeX — REQUIRED (see section above)
# Install MiKTeX, then:
python -m pipeline.run doctor

# 4. Secrets + config
copy config\example.env .env
# Edit .env: LLM_API_KEY, CAPSOLVER_API_KEY, APPLY_EMAIL, APPLY_PASSWORD
copy config\profile.example.json data\profile.json
copy config\role_rules.example.json data\role_rules.json
copy config\exclude_companies.example.txt data\exclude_companies.txt

# 5. UI setup wizard (collects paths + secrets; shows LaTeX status)
streamlit run ui\app.py
```

Optional env overrides in `.env`:

```
# Durable Chrome profile (default). Log into Gmail once in the headed browser.
CHROME_USER_DATA_DIR=data/browser_state

# Only if not on PATH:
# XELATEX=%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\xelatex.exe
# PDFLATEX=%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe
```

### One-time Gmail login (apply persistence)

1. Chrome user-data-dir defaults to **`data/browser_state`** (created automatically).
2. First headed apply run: sign into Gmail / job-site accounts in the Playwright Chrome window.
3. Cookies and session survive restarts — do not delete `data/browser_state` unless you want a fresh login.

---

## CLI

```powershell
cd C:\R@D_projects\automata
.\.venv\Scripts\Activate.ps1

python -m pipeline.run doctor
python -m pipeline.run --help

python -m pipeline.run filter --excel path\to\AllJobs.xlsx --tag 9_19_2026
python -m pipeline.run addresses --excel path\to\AI_Engineer__N_jobs.xlsx --addresses path\to\address_for_resume.xlsx --date 9_19_2026
python -m pipeline.run jd --day 9_19_2026 --split --fetch --merge
python -m pipeline.run resume --day 9_19_2026          # requires LaTeX
python -m pipeline.run resume --day 9_19_2026 --dry    # no LLM; still needs LaTeX for PDFs
python -m pipeline.run resume --day 9_19_2026 --force  # redo already-done folders
python -m pipeline.run apply --excel data\Input\9_19_2026\updated\*_updated.xlsx --dry --limit 3 --headed
python -m pipeline.run apply --url https://boards.greenhouse.io/... --dry --headed
```

## Linux / this box

```bash
cd /workspace/automata
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pipeline.run doctor --skip-playwright-probe
python -m pipeline.run --help
streamlit run ui/app.py
```

## Config layout

| File | Contents |
|------|----------|
| `data/config.yaml` | Non-secrets (Excel paths, LLM URL/model, Chrome profile, LaTeX paths) |
| `.env` | Secrets (API keys, email/password) — **gitignored** |
| `data/browser_state/` | Persistent Chrome profile (Gmail login) |
| `config/*.example.*` | Templates to copy into `data/` or `.env` |

UI **Reload** + **Save** keep last saved `config.yaml` / `.env` values in the form fields.

## Status vocabulary (apply)

Terminal (skipped on resume): `applied` · `job_closed` · `captcha` · `blocked_platform` · `aggregator` · `gate_skip` · `needs_human` · `form_blocked` · `left for LinkedIn - apply manually` · `error`

## Tests

```bash
python -m pytest tests/ -q
# or:
python -m unittest tests.test_safety_fieldmap tests.test_doctor_latex -v
```

## License

MIT — see [LICENSE](LICENSE).

## Product

**Automata** — https://github.com/Bhanubathini2002/automata
