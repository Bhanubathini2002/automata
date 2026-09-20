"""LLM prompts for resume/cover JSON specs. Verbatim contract from DUMB_MODEL_RUNBOOK."""
from __future__ import annotations

import json
import os
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
_BASE_PATH = ENGINE / "base_spec.json"
BASE_SPEC = json.loads(_BASE_PATH.read_text(encoding="utf-8")) if _BASE_PATH.is_file() else {}

RULES = """ABSOLUTE RULES
1. Use ONLY facts, employers, dates, tools and numbers that appear in BASE_RESUME. Never add a technology, tool, certification, employer, degree or metric that is not already there.
2. If the job asks for something BASE_RESUME does not have (example: Kotlin, Adobe, TensorRT, Rust, SAS), do NOT mention it anywhere.
3. Keep every number from BASE_RESUME exactly (35%, 40%, 60%, 30+). Do not invent new percentages.
4. Reword, reorder, shorten, emphasize - that is your whole job. Put the technologies the job description repeats most FIRST.
5. Order matters: MOST job-relevant items FIRST in every list. The last items may be deleted automatically to fit the page.
6. Seniority: entry/junior job -> plain builder verbs (built, shipped, implemented). Senior/staff/lead -> ownership verbs are fine (owned, led, architected).
7. Plain text only. No LaTeX, no backslashes, no markdown, no bullet symbols, no emojis. Normal characters (&, %, #) are fine.
8. Output ONLY a valid JSON object. No prose before or after. No markdown fences."""

SYSTEM_RESUME = (
    "You rewrite ONE resume to match ONE job description and output ONLY a JSON object.\n\n"
    + RULES
)
SYSTEM_CL = (
    "You write ONE cover letter for ONE job and output ONLY a JSON object.\n\n" + RULES
)

RESUME_SCHEMA = {
    "title": "string, 3-6 words, the job's role name",
    "objective": "string, 60-90 words, ONE paragraph",
    "profile": [{"label": "2-4 word bold label", "text": "30-55 words"}],
    "skills": [{"category": "2-5 word category", "items": "comma-separated technologies"}],
    "mondee_bullets": ["string, 18-35 words"],
    "cosmic_bullets": ["string, 18-35 words"],
}
RESUME_COUNTS = (
    "profile: 6-8 items | skills: 8-10 rows (20-25 technologies total) | "
    "mondee_bullets: 8-9 | cosmic_bullets: 5-6"
)

CL_SCHEMA = {
    "addr": "string: City, ST or Remote, United States",
    "p1": "string, 55-70 words",
    "p2": "string, 90-110 words",
    "p3": "string, 80-100 words",
    "p4": "string, 45-60 words",
}


def _job_block(jd, company, title, city_st, level):
    return f"""JOB
company: {company}
title: {title}
location: {city_st}
level: {level}

JOB DESCRIPTION
{(jd or '').strip()[:6000]}
"""


def build_messages(jd, company, title, city_st, level, base_spec=None):
    base = base_spec if base_spec is not None else BASE_SPEC
    user = (
        _job_block(jd, company, title, city_st, level)
        + "\nBASE_RESUME (the only allowed source of facts)\n"
        + json.dumps(base, ensure_ascii=False, indent=0)
        + "\n\nOUTPUT_SCHEMA - every key is required\n"
        + json.dumps(RESUME_SCHEMA, ensure_ascii=False, indent=0)
        + "\n\nREQUIRED COUNTS\n"
        + RESUME_COUNTS
        + "\n\nReturn the JSON object now."
    )
    return [{"role": "system", "content": SYSTEM_RESUME}, {"role": "user", "content": user}]


def build_cl_messages(jd, company, title, city_st, level, base_spec=None):
    base = base_spec if base_spec is not None else BASE_SPEC
    facts = {
        "objective": base.get("objective", ""),
        "mondee_bullets": (base.get("mondee_bullets") or [])[:8],
        "skills": (base.get("skills") or [])[:6],
    }
    user = (
        _job_block(jd, company, title, city_st, level)
        + "\nBASE_RESUME (the only allowed source of facts)\n"
        + json.dumps(facts, ensure_ascii=False, indent=0)
        + "\n\nOUTPUT_SCHEMA - every key is required, respect the word counts\n"
        + json.dumps(CL_SCHEMA, ensure_ascii=False, indent=0)
        + "\n\nReturn the JSON object now."
    )
    return [{"role": "system", "content": SYSTEM_CL}, {"role": "user", "content": user}]


def repair_messages(system, previous_output, errors):
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                "Your previous JSON had these problems:\n- "
                + "\n- ".join(errors)
                + "\n\nFix ONLY those problems and return the complete corrected JSON object.\n"
                "Previous output:\n"
                + previous_output[:12000]
            ),
        },
    ]


def load_ats_prompt(path: str | None) -> str:
    """Optional ATS prompt markdown appended to system (reference only)."""
    if not path or not os.path.isfile(path):
        return ""
    return Path(path).read_text(encoding="utf-8")[:8000]
