"""LLM tailor driver: 2 calls/job → JSON → validate → render hooks."""
from __future__ import annotations

import concurrent.futures as cf
import glob
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from . import prompts, render

ENGINE = Path(__file__).resolve().parent


def chat(base_url, api_key, model, messages, temperature=0.2, max_tokens=3000,
         json_mode=True, timeout=180):
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="replace")
            if e.code == 400 and "response_format" in txt and json_mode:
                return chat(
                    base_url, api_key, model, messages, temperature,
                    max_tokens, json_mode=False, timeout=timeout,
                )
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f"HTTP {e.code}: {txt[:300]}")
        except Exception:
            if attempt < 3:
                time.sleep(2 ** attempt * 3)
                continue
            raise


def extract_json(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        t = m.group(0)
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return json.loads(t)


def _llm_json(args, msgs, system, validate_fn, max_tries=3):
    raw, errors = "", []
    for _ in range(max_tries):
        try:
            raw = chat(args["base_url"], args["api_key"], args["model"], msgs,
                       max_tokens=args.get("max_tokens", 3000))
            obj = extract_json(raw)
        except Exception as e:
            errors = [f"LLM/JSON error: {e}"]
            msgs = prompts.repair_messages(system, raw, errors)
            continue
        errors = validate_fn(obj)
        if not errors:
            return obj, []
        msgs = prompts.repair_messages(system, json.dumps(obj, ensure_ascii=False), errors)
    return None, errors


def tailor_job(
    job_dir: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    resume_template: str | None = None,
    cover_template: str | None = None,
    max_tokens: int = 3000,
    dry_llm: bool = False,
) -> dict[str, Any]:
    meta_path = os.path.join(job_dir, "job.json")
    if not os.path.isfile(meta_path):
        return {"ok": False, "errors": ["missing job.json"]}
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    jd = meta.get("jd") or ""
    if not jd or jd == "FETCH_FAILED":
        return {"folder": meta.get("folder"), "ok": False, "errors": ["no usable jd"]}

    args = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "max_tokens": max_tokens,
    }
    co, ti, cs, lv = meta["company"], meta["title"], meta["city_st"], meta.get("level", "")

    if dry_llm:
        # Offline path: use base_spec as the "model" output
        spec = dict(render.BASE_SPEC)
        spec["title"] = ti[:60] or spec.get("title", "AI Engineer")
        cl = {
            "addr": cs,
            "p1": f"I am writing to apply for {ti} at {co}. "
                  "I bring half a decade of production AI/ML experience.",
            "p2": (render.BASE_SPEC.get("objective") or "")[:500],
            "p3": "My stack and working methods map to the role requirements in the posting.",
            "p4": f"I would welcome a conversation about {co}. Thank you for your time and consideration.",
        }
    else:
        if not api_key:
            return {"ok": False, "errors": ["LLM_API_KEY missing"]}
        spec, errs = _llm_json(
            args,
            prompts.build_messages(jd, co, ti, cs, lv),
            prompts.SYSTEM_RESUME,
            lambda o: render.validate(render.normalize(o), cs),
        )
        if spec is None:
            return {"folder": meta.get("folder"), "ok": False, "stage": "resume-llm", "errors": errs}

        def cl_check(o):
            if not isinstance(o, dict):
                return ["cover letter must be a JSON object"]
            missing = [k for k in ("p1", "p2", "p3", "p4") if not str(o.get(k, "")).strip()]
            if missing:
                return ["missing paragraphs: " + ", ".join(missing)]
            low = json.dumps(o).lower()
            fab = [b for b in render.BLOCKLIST if re.search(rf"\b{re.escape(b)}\b", low)]
            return (["remove blocked tech: " + ", ".join(fab)] if fab else [])

        cl, errs = _llm_json(
            args,
            prompts.build_cl_messages(jd, co, ti, cs, lv),
            prompts.SYSTEM_CL,
            cl_check,
        )
        if cl is None:
            return {"folder": meta.get("folder"), "ok": False, "stage": "cl-llm", "errors": errs}

    result = render.build_job(
        job_dir, spec, cl, cs, co, ti,
        resume_template=resume_template,
        cover_template=cover_template,
    )
    result["folder"] = meta.get("folder")
    result["num"] = meta.get("num")
    result["row"] = meta.get("row")
    result["model"] = model if not dry_llm else "dry/base_spec"
    return result


def run_batch(
    day: str,
    *,
    root: str | None = None,
    base_url: str = "",
    api_key: str = "",
    model: str = "deepseek-chat",
    workers: int = 4,
    only: str | None = None,
    resume_template: str | None = None,
    cover_template: str | None = None,
    dry_llm: bool = False,
    write_excel: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    root_p = Path(root) if root else ENGINE.parent.parent / "data"
    out_root = root_p / "Resume" / "output" / f"date_{day}"
    upd = root_p / "Input" / day / "updated"
    results_dir = upd / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    jobs = sorted(
        d for d in glob.glob(str(out_root / "*"))
        if os.path.isfile(os.path.join(d, "job.json"))
    )
    if only:
        keep = set(only.split(","))
        jobs = [j for j in jobs if os.path.basename(j) in keep]

    done = fail = 0
    t0 = time.time()

    def _one(j):
        out_path = results_dir / (os.path.basename(j) + ".json")
        # Idempotent: skip already-done job folders unless --force
        if not force and out_path.is_file():
            try:
                prev = json.loads(out_path.read_text(encoding="utf-8"))
                if prev.get("ok") and prev.get("compiled"):
                    return {**prev, "cached": True}
                # Also skip if PDFs already on disk from a prior successful compile
                rp = os.path.join(j, "Bhanu_Prakash_Bathini.pdf")
                cp = os.path.join(j, "Bhanu_Prakash_Bathini_Cover_Letter.pdf")
                if prev.get("ok") and os.path.isfile(rp) and os.path.isfile(cp):
                    return {**prev, "cached": True}
            except Exception:
                pass
        r = tailor_job(
            j,
            base_url=base_url,
            api_key=api_key,
            model=model,
            resume_template=resume_template,
            cover_template=cover_template,
            dry_llm=dry_llm,
        )
        out_path.write_text(json.dumps(r, indent=1), encoding="utf-8")
        return r

    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for r in ex.map(_one, jobs):
            if r.get("ok"):
                done += 1
            else:
                fail += 1
            tag = "cached" if r.get("cached") else ("OK" if r.get("ok") else "FAIL")
            print(f"[{done + fail:>3}/{len(jobs)}] {str(r.get('folder', ''))[:50]:<50} {tag}")

    excel_n = 0
    if write_excel:
        excel_n = _write_excel_paths(upd, jobs)

    return {
        "day": day,
        "done": done,
        "failed": fail,
        "total": len(jobs),
        "elapsed_min": round((time.time() - t0) / 60, 2),
        "excel_rows": excel_n,
    }


def _write_excel_paths(upd: Path, jobs: list[str]) -> int:
    try:
        import openpyxl
        from pypdf import PdfReader
    except ImportError:
        return 0
    cand = [p for p in upd.glob("*_updated.xlsx") if not p.name.startswith("~$")]
    if not cand:
        return 0
    wb = openpyxl.load_workbook(cand[0])
    ws = wb[wb.sheetnames[0]]
    hdr = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]
    if "updated_resume_section" not in hdr or "coverletter" not in hdr:
        return 0
    c_res = hdr.index("updated_resume_section") + 1
    c_cl = hdr.index("coverletter") + 1
    n = 0
    for j in jobs:
        meta = json.loads(Path(j, "job.json").read_text(encoding="utf-8"))
        rp = os.path.join(j, "Bhanu_Prakash_Bathini.pdf")
        cp = os.path.join(j, "Bhanu_Prakash_Bathini_Cover_Letter.pdf")
        if os.path.exists(rp) and os.path.exists(cp):
            try:
                # Prefer correct page counts; still record paths if PDFs exist
                ws.cell(row=meta["row"], column=c_res, value=rp)
                ws.cell(row=meta["row"], column=c_cl, value=cp)
                n += 1
                continue
            except Exception:
                pass
        # Do NOT write .tex paths as if PDFs exist — LaTeX compile is required
    try:
        wb.save(cand[0])
    except PermissionError:
        print("PermissionError: close Excel and rerun (results cached).")
    return n
