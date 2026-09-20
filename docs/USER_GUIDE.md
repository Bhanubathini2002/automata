# Automata — User Guide

This guide covers the inputs you prepare once, what each stage produces, and how to fix the
common problems. For install and the quick tour see the [README](../README.md).

## 1. Inputs you prepare once

### Jobs workbook

Any `.xlsx` or `.csv`. The first sheet that has both a **Job Title** and a **Company** column is used.
Recognised optional columns (matched by name, case-insensitive):

| Column | Used for |
|---|---|
| `Location` | address matching (`City, ST` anywhere in the cell) |
| `Experience` / `Years of Experience` | dropping postings above your `max_experience_years` |
| `Match %` / `Score` | sort order inside each role workbook |
| `Original Job Posting Link` / `Link` / `URL` | the page the apply stage opens |
| `Level` | passed to the tailoring prompt |

### Address book

An `.xlsx` with `City`, `State`, `Address` headers (one row per city you are willing to list).
Nearby suburbs map to the nearest listed city; unmatched locations fall back to the first
row for that state, then to your configured **Fallback location**.

### Role rules and exclusions

* `config/role_rules.example.json` → copy to `data/role_rules.json` to change how titles are
  grouped. First matching rule wins.
* `config/exclude_companies.example.txt` → copy to `data/exclude_companies.txt`. One substring per
  line, case-insensitive.

### Candidate profile — `data/profile.json`

Every answer the apply engine can give. Copy `config/profile.example.json` and fill in:

| Section | Notes |
|---|---|
| `identity` | name, email, phone (digits only), address, LinkedIn, pronouns |
| `work_auth` | `authorized_to_work_us` and `requires_sponsorship_now_or_future` — the engine defaults to Yes / No even if these are blank. `is_us_citizen`, `has_green_card`, `security_clearance` are intentionally never used. |
| `eeo` | voluntary self-identification answers; "Prefer not to say" is fine |
| `education`, `employment`, `compensation` | plain strings as you would type them |
| `standard_answers` | relocation, travel, notice period, start-date offset, "how did you hear" |
| `essays` | short free-text answers reused for "why us", project descriptions, links |

Questions about citizenship, permanent residency, nationality, clearance, ITAR/export control,
SSN, date of birth, passport or bank details always stop the application with `gate_skip`.

### Base resume spec — `data/base_spec.json`

The **only** source of facts the model may use. Copy `pipeline/resume_engine/base_spec.json` and
replace the contents with your own:

```json
{
  "title": "AI Engineer",
  "objective": "60–90 word summary …",
  "profile": [{"label": "Bold label", "text": "30–55 words"}],
  "skills": [{"category": "Languages", "items": "Python, SQL, …"}],
  "experience_1_env": "tools used at your most recent employer (optional)",
  "experience_1_bullets": ["18–35 word bullet", "…"],
  "experience_2_env": "tools used at the previous employer (optional)",
  "experience_2_bullets": ["…"]
}
```

Anything in the tailored output that is not in this file (or is in the tech blocklist) is
rejected and the model is asked to repair it, up to three times.

### Tech blocklist

`config/blocklist.example.json` → copy to `data/blocklist.json`. `tech_blocklist` lists technologies
the model must never claim; `blocked_hosts` and `aggregators` route URLs to `captcha`,
`blocked_platform` or `aggregator` without opening them.

## 2. LaTeX templates

Your own `.tex` files are used as-is, with `{{SLOT}}` tokens replaced by escaped text. A template
with no slots is copied unchanged (useful when you only want the cover letter tailored).

**Resume slots**

| Slot | Replaced with |
|---|---|
| `{{TITLE}}` | tailored headline |
| `{{CITY_ST}}` | `City, ST` from the address match |
| `{{OBJECTIVE}}` | tailored objective paragraph |
| `{{PROFILE_ITEMS}}` | `\item \textbf{Label:} text` lines — place inside your own `itemize` |
| `{{SKILL_ROWS}}` | `\item \textbf{Category:} items` lines |
| `{{EXPERIENCE_1_BULLETS}}` | `\item …` lines for the most recent employer |
| `{{EXPERIENCE_2_BULLETS}}` | `\item …` lines for the previous employer |

**Cover letter slots**

`{{COMPANY}}`, `{{JOB_TITLE}}`, `{{CITY_ST}}`, `{{DATE}}`, `{{P1}}` … `{{P4}}`
(legacy `<<COMPANY NAME>>`, `<<JOB TITLE>>`, `<<COMPANY CITY, STATE>>` also work).

Minimal example:

```latex
\documentclass[10pt]{article}
\usepackage[margin=0.6in]{geometry}\usepackage{enumitem}
\begin{document}
\section*{Jane Doe --- {{TITLE}}}
{{CITY_ST}} \\
{{OBJECTIVE}}
\section*{Profile}\begin{itemize}[nosep]{{PROFILE_ITEMS}}\end{itemize}
\section*{Skills}\begin{itemize}[nosep]{{SKILL_ROWS}}\end{itemize}
\section*{Current Employer Inc}\begin{itemize}[nosep]{{EXPERIENCE_1_BULLETS}}\end{itemize}
\section*{Previous Employer LLC}\begin{itemize}[nosep]{{EXPERIENCE_2_BULLETS}}\end{itemize}
\end{document}
```

If the compiled resume exceeds two pages the engine drops the last experience bullet, then the
last profile item, and recompiles (up to four rounds). Output files are named after
`identity.full_name` in your profile: `Jane_Doe.pdf` and `Jane_Doe_Cover_Letter.pdf`.

## 3. Stages in detail

| # | Command | Reads | Writes |
|---|---|---|---|
| 1 | `filter --excel … --tag DAY` | jobs workbook | `data/Output/DAY/<Role>__N_jobs.xlsx`, `_REMOVED__N_jobs.xlsx` |
| 2 | `addresses --excel <role.xlsx> --date DAY` | role workbook, address book | `data/Input/DAY/updated/<file>_updated.xlsx`, `jobs_full.json`, one folder per job |
| 3 | `jd --day DAY` | `jobs_full.json` | `jd` column, `job.json.jd`, `jd_batches/` |
| 4 | `resume --day DAY` | `job.json`, `data/base_spec.json`, templates | `main.tex`, `coverletter.tex`, PDFs, `spec.json`, paths in the workbook |
| 5 | `apply --day DAY [--dry] [--limit N]` | `*_updated.xlsx` | `apply_status`, `apply_timestamp`, `data/applications/<date>/tier_a_runner.jsonl` |

**Day tag** is `M_D_YYYY` (for example `9_19_2026`). It groups one batch; you can run several
batches per day with different tags.

**Rerun semantics**

* Stage 1 overwrites its own role workbooks in the tag folder and nothing else.
* Stage 2 refuses to re-stage a day unless you pass `--redo`.
* Stage 3 can be rerun; `FETCH_FAILED` rows are retried.
* Stage 4 caches successes in `Input/DAY/updated/results/`; only failures are retried.
* Stage 5 skips rows with a status. Delete the cell to retry a row.

## 4. Apply stage behaviour

1. URL pre-check: blocked hosts, aggregators and LinkedIn get an instant status.
2. Open the posting in your persistent Chrome profile, dismiss cookie banners.
3. Dead-posting check → `job_closed`. Eligibility-gate scan → `gate_skip`. Blocking captcha →
   CapSolver (reCAPTCHA v2 only) or `captcha`.
4. Click *Apply*, then fill every visible field whose label maps to a profile answer. File inputs get
   the row's resume (or cover letter when the label says so). Radio groups are matched by option text
   and never flipped across a yes/no boundary.
5. A hard-stop label anywhere → `gate_skip`. Dry run → `needs_human` without submitting.
6. Submit, wait, look for a one-time-code prompt (fetched over IMAP if configured), then look for a
   confirmation page or message. Only that yields `applied`. Required fields the engine could not map →
   `needs_human`. Otherwise `form_blocked`.

Each row gets at most `apply_budget_seconds` (default 180). The workbook is saved after every row; if
Excel has it open the write is queued to `pending_excel_writes.jsonl` and replayed with `apply --sync`.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `check` says LaTeX not found | Install MiKTeX/TeX Live or set `XELATEX`/`PDFLATEX` in `.env`. Without it you still get `.tex` files. |
| Resume stage: `fabricated/blocked tech` after 3 tries | The posting asks for tools you do not have. Add them to your base spec only if true. |
| Resume stage: `no usable job description` | Fetch failed (login wall or JavaScript-only page). Paste the JD into the `jd` column and `job.json`, then rerun. |
| Apply: everything is `needs_human` | You are in dry-run mode, or the form uses labels the mapper does not know. Check `unmapped` in the JSONL log and extend `profile.json` or `fieldmap.py`. |
| Apply: `captcha` on every row for one host | Add the host to `blocked_hosts` in `data/blocklist.json` and apply manually. |
| `PermissionError` on a workbook | Close it in Excel and rerun; queued statuses replay automatically. |
| Browser opens but is not signed in | Point **Chrome profile** at a directory, run once headed, sign in; sessions persist there. |
