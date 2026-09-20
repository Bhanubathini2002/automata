"""
Stage 3 prep — match job locations to an address book, stage job folders.

Ported from resume/scripts/pipeline_setup.py (paths via config / data/).
"""
from __future__ import annotations

import json
import os
import re
import shutil
from copy import copy
from datetime import date as _date
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent

NEAREST = {
    ("san mateo", "CA"): ("san francisco", "CA"),
    ("santa clara", "CA"): ("san jose", "CA"),
    ("sunnyvale", "CA"): ("san jose", "CA"),
    ("palo alto", "CA"): ("san jose", "CA"),
    ("mountain view", "CA"): ("san jose", "CA"),
    ("menlo park", "CA"): ("san francisco", "CA"),
    ("south san francisco", "CA"): ("san francisco", "CA"),
    ("dublin", "CA"): ("san francisco", "CA"),
    ("burlingame", "CA"): ("san francisco", "CA"),
    ("foster city", "CA"): ("san francisco", "CA"),
    ("redwood city", "CA"): ("san francisco", "CA"),
    ("cupertino", "CA"): ("san jose", "CA"),
    ("hawthorne", "CA"): ("los angeles", "CA"),
    ("irvine", "CA"): ("los angeles", "CA"),
    ("santa monica", "CA"): ("los angeles", "CA"),
    ("pasadena", "CA"): ("los angeles", "CA"),
    ("irving", "TX"): ("dallas", "TX"),
    ("plano", "TX"): ("dallas", "TX"),
    ("frisco", "TX"): ("dallas", "TX"),
    ("richardson", "TX"): ("dallas", "TX"),
    ("round rock", "TX"): ("austin", "TX"),
    ("kirkland", "WA"): ("seattle", "WA"),
    ("redmond", "WA"): ("seattle", "WA"),
    ("bellevue", "WA"): ("seattle", "WA"),
    ("cambridge", "MA"): ("boston", "MA"),
    ("quincy", "MA"): ("boston", "MA"),
    ("arlington", "VA"): ("richmond", "VA"),
    ("mclean", "VA"): ("richmond", "VA"),
    ("reston", "VA"): ("richmond", "VA"),
    ("herndon", "VA"): ("richmond", "VA"),
    ("bolingbrook", "IL"): ("chicago", "IL"),
    ("dearborn", "MI"): ("detroit", "MI"),
    ("ann arbor", "MI"): ("detroit", "MI"),
}

LOC_RE = re.compile(r"([A-Za-z][A-Za-z .\-]{1,25}),\s*([A-Z]{2})\b")
CITYST_RE = re.compile(r",\s*([A-Za-z .\-]+),\s*([A-Z]{2})\s*\d{5}")


def load_address_book(path: str):
    ws = openpyxl.load_workbook(path).active
    by_city, by_state = {}, {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 5 or not row[1]:
            continue
        city = str(row[1]).strip()
        state = str(row[2]).strip().upper()
        addr = str(row[4]).strip()
        by_city[(city.lower(), state)] = addr
        by_state.setdefault(state, []).append((city, addr))
    return by_city, by_state


def resolve_address(loc, by_city, by_state, default):
    if not loc:
        return default, "default"
    hits = LOC_RE.findall(str(loc).strip())
    if not hits:
        return default, "default"
    city, state = hits[-1][0].strip().lower(), hits[-1][1].upper()
    if (city, state) in by_city:
        return by_city[(city, state)], "exact"
    if (city, state) in NEAREST and NEAREST[(city, state)] in by_city:
        return by_city[NEAREST[(city, state)]], "nearest"
    if state in by_state:
        return by_state[state][0][1], "nearest"
    return default, "default"


def city_st(full_address: str, fallback: str = "Houston, TX") -> str:
    m = CITYST_RE.search(full_address or "")
    return f"{m.group(1).strip()}, {m.group(2)}" if m else fallback


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_")[:45]


def find_col(headers, *names):
    low = [str(h).strip().lower() if h else "" for h in headers]
    for n in names:
        if n.lower() in low:
            return low.index(n.lower()) + 1
    return None


def parse_day(xlsx: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(xlsx))
    if m:
        return f"{int(m.group(2))}_{int(m.group(3))}_{m.group(1)}"
    t = _date.today()
    return f"{t.month}_{t.day}_{t.year}"


def run_setup(
    xlsx: str,
    addresses_excel: str,
    base_resume_tex: str = "",
    base_cover_tex: str = "",
    day: str | None = None,
    root: str | None = None,
    default_addr: str | None = None,
    default_city_st: str = "Houston, TX",
    redo: bool = False,
) -> dict[str, Any]:
    """
    File Excel → add address/resume/jd/cover columns → stage per-job folders.
    """
    root_p = Path(root) if root else ROOT / "data"
    day = parse_day(xlsx, day)
    orig = root_p / "Input" / day / "original"
    upd = root_p / "Input" / day / "updated"
    orig.mkdir(parents=True, exist_ok=True)
    upd.mkdir(parents=True, exist_ok=True)

    existing = list(upd.glob("*_updated.xlsx"))
    if existing and not redo:
        return {
            "ok": False,
            "already_processed": True,
            "day": day,
            "message": f"already processed on {day}; pass redo=True to overwrite",
            "excel": str(existing[0]),
        }

    dst = orig / os.path.basename(xlsx)
    if os.path.abspath(xlsx) != os.path.abspath(dst):
        shutil.copy2(xlsx, dst)
    else:
        dst = Path(xlsx)

    by_city, by_state = load_address_book(addresses_excel)
    if default_addr is None:
        default_addr = by_city.get(("houston", "TX")) or next(iter(by_city.values()), "")
    if not default_addr:
        raise SystemExit("Address book is empty and no default_addr provided")

    wb = openpyxl.load_workbook(dst)
    ws = wb[wb.sheetnames[0]]
    headers = [c.value for c in ws[1]]
    c_title = find_col(headers, "Job Title", "Title") or 2
    c_comp = find_col(headers, "Company") or 3
    c_loc = find_col(headers, "Location") or 6
    c_level = find_col(headers, "Level") or 9
    c_orig = find_col(headers, "Original Job Posting Link", "Link", "URL") or 5
    c_jr = find_col(headers, "Jobright Link") or 13

    base = ws.max_column
    # Prefer fixed column layout matching COMPLETE_WORKFLOW if enough columns exist
    C_ADDR, C_RES, C_JD, C_CL = base + 1, base + 2, base + 3, base + 4
    hf = copy(ws.cell(row=1, column=1).font)
    for col, name, width in [
        (C_ADDR, "complete_address_section", 50),
        (C_RES, "updated_resume_section", 70),
        (C_JD, "jd", 60),
        (C_CL, "coverletter", 70),
    ]:
        ws.cell(row=1, column=col, value=name).font = hf
        ws.column_dimensions[get_column_letter(col)].width = width

    jobs, stats, seen = [], {}, {}
    for r in range(2, ws.max_row + 1):
        title = ws.cell(row=r, column=c_title).value
        if not title:
            continue
        company = str(ws.cell(row=r, column=c_comp).value or "Unknown")
        addr, how = resolve_address(
            ws.cell(row=r, column=c_loc).value, by_city, by_state, default_addr
        )
        ws.cell(row=r, column=C_ADDR, value=addr)
        stats[how] = stats.get(how, 0) + 1

        folder = f"{slug(company)}_{slug(title)}"
        key = folder.lower()
        if key in seen:
            seen[key] += 1
            folder = f"{folder}_{seen[key]}"
        else:
            seen[key] = 1

        jobs.append({
            "row": r,
            "num": ws.cell(row=r, column=1).value,
            "company": company,
            "title": str(title),
            "loc": str(ws.cell(row=r, column=c_loc).value or ""),
            "level": str(ws.cell(row=r, column=c_level).value or ""),
            "jobright": str(ws.cell(row=r, column=c_jr).value or ""),
            "original": str(ws.cell(row=r, column=c_orig).value or ""),
            "city_st": city_st(addr, default_city_st),
            "folder": folder,
            "cols": {"addr": C_ADDR, "resume": C_RES, "jd": C_JD, "cl": C_CL},
        })

    stem = os.path.splitext(os.path.basename(dst))[0]
    out_xlsx = upd / f"{stem}_updated.xlsx"
    wb.save(out_xlsx)
    (upd / "jobs_full.json").write_text(
        json.dumps(jobs, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    out_root = root_p / "Resume" / "output" / f"date_{day}"
    out_root.mkdir(parents=True, exist_ok=True)
    for j in jobs:
        d = out_root / j["folder"]
        d.mkdir(parents=True, exist_ok=True)
        if base_resume_tex and os.path.isfile(base_resume_tex):
            shutil.copy(base_resume_tex, d / "main.tex")
        if base_cover_tex and os.path.isfile(base_cover_tex):
            shutil.copy(base_cover_tex, d / "coverletter.tex")
        meta = {k: j[k] for k in ("row", "num", "company", "title", "loc", "level", "city_st", "folder")}
        meta["jd"] = ""
        (d / "job.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

    return {
        "ok": True,
        "day": day,
        "addresses": stats,
        "jobs": len(jobs),
        "excel": str(out_xlsx),
        "output_root": str(out_root),
        "jobs_full": str(upd / "jobs_full.json"),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Address match + stage job folders")
    ap.add_argument("xlsx")
    ap.add_argument("--addresses", required=True)
    ap.add_argument("--resume-tex", default="")
    ap.add_argument("--cover-tex", default="")
    ap.add_argument("--date", default=None)
    ap.add_argument("--root", default=None)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run_setup(
        a.xlsx, a.addresses, a.resume_tex, a.cover_tex, a.date, a.root, redo=a.redo
    ), indent=2))
