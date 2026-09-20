"""
Automata CLI - post-scrape job search automation.

  python -m pipeline.run --help
  python -m pipeline.run doctor
  python -m pipeline.run filter --excel jobs.xlsx
  python -m pipeline.run addresses --excel role.xlsx --addresses book.xlsx
  python -m pipeline.run jd --day 9_14_2026 --fetch
  python -m pipeline.run resume --day 9_14_2026
  python -m pipeline.run apply --excel updated.xlsx --dry --limit 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow `python -m pipeline.run` from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config_io import (  # noqa: E402
    load_config, load_dotenv, secret, ensure_data_dirs,
    default_chrome_user_data_dir, apply_latex_env_from_config,
)


def cmd_doctor(args):
    from pipeline.doctor import run_doctor
    report = run_doctor(probe_playwright=not args.skip_playwright_probe)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for c in report["checks"]:
            mark = "OK " if c.get("ok") else "FAIL"
            print(f"  [{mark}] {c['check']}: {c.get('detail', '')}")
        print()
        if report["ok"]:
            print("Doctor: all required checks passed.")
        else:
            print("Doctor: FAILED ->", ", ".join(report["failed"]))
            print("Install LaTeX (MiKTeX / TeX Live) before generate-resumes.")
            print("Hints:", json.dumps(report["hints"], indent=2))
    return 0 if report["ok"] else 1


def cmd_filter(args):
    from pipeline.filter_jobs import process
    cfg = load_config()
    tag = args.tag
    out = args.out or str(ROOT / "data" / "Output" / (tag or "latest"))
    r = process(args.excel, out, tag, max_years=cfg.get("max_experience_years", 5))
    print(json.dumps(r, indent=2))
    return 0


def cmd_addresses(args):
    from pipeline.addresses import run_setup
    cfg = load_config()
    r = run_setup(
        args.excel,
        args.addresses or cfg.get("addresses_excel") or "",
        base_resume_tex=args.resume_tex or cfg.get("base_resume_tex") or "",
        base_cover_tex=args.cover_tex or cfg.get("base_cover_tex") or "",
        day=args.date,
        root=args.root or str(ROOT / "data"),
        default_city_st=cfg.get("default_city_st", "Houston, TX"),
        redo=args.force or args.redo,
    )
    print(json.dumps(r, indent=2))
    return 0 if r.get("ok") or r.get("already_processed") else 1


def cmd_jd(args):
    from pipeline import jd_fetch
    root = Path(args.root or ROOT / "data")
    force = args.force
    if args.split or not (args.fetch or args.merge):
        print(json.dumps(jd_fetch.cmd_split(root, args.day, args.n), indent=2))
    if args.fetch:
        print(json.dumps(jd_fetch.cmd_fetch(root, args.day, args.batch, force=force), indent=2))
    if args.merge:
        r = jd_fetch.cmd_merge(root, args.day)
        print(json.dumps(r, indent=2))
        return 1 if r.get("missing") else 0
    return 0


def cmd_resume(args):
    from pipeline.resume_engine.tailor import run_batch
    load_dotenv()
    cfg = load_config()
    apply_latex_env_from_config(cfg)
    r = run_batch(
        args.day,
        root=args.root or str(ROOT / "data"),
        base_url=args.base_url or cfg.get("llm_base_url") or secret("LLM_BASE_URL"),
        api_key=args.api_key or secret("LLM_API_KEY") or secret("OPENAI_API_KEY"),
        model=args.model or cfg.get("llm_model") or secret("LLM_MODEL", "deepseek-chat"),
        workers=args.workers,
        only=args.only,
        resume_template=cfg.get("base_resume_tex") or None,
        cover_template=cfg.get("base_cover_tex") or None,
        dry_llm=args.dry,
        write_excel=not args.no_excel,
        force=args.force,
    )
    print(json.dumps(r, indent=2))
    return 0 if r.get("failed", 0) == 0 else 1


def cmd_apply(args):
    from pipeline.apply_tier_a.apply import run_excel_batch, apply_to
    load_dotenv()
    cfg = load_config()
    profile = (
        args.chrome_profile
        or cfg.get("chrome_profile_path")
        or secret("CHROME_USER_DATA_DIR")
        or str(default_chrome_user_data_dir())
    )
    if args.url:
        r = apply_to(
            args.url,
            resume=args.resume or "",
            cover_letter=args.cover or "",
            chrome_profile=profile or "",
            headless=not args.headed,
            dry_run=args.dry,
            budget_s=args.budget,
        )
        print(json.dumps(r, indent=2))
        return 0 if r.get("status") == "applied" else 1
    if not args.excel:
        print("need --excel or --url", file=sys.stderr)
        return 2
    r = run_excel_batch(
        args.excel,
        limit=args.limit,
        dry_run=args.dry,
        headed=args.headed,
        chrome_profile=profile or "",
        budget_s=args.budget,
    )
    print(json.dumps(r, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipeline.run",
        description="Automata - Job Search Automation (filter -> addresses -> JD -> resume -> apply)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="Preflight: Python imports, Playwright, LaTeX, .env keys")
    p.add_argument("--json", action="store_true")
    p.add_argument("--skip-playwright-probe", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("filter", help="Filter/sort/split jobs Excel by role")
    p.add_argument("--excel", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--tag", default=None)
    p.set_defaults(func=cmd_filter)

    p = sub.add_parser("addresses", help="Match addresses + stage job folders")
    p.add_argument("--excel", required=True)
    p.add_argument("--addresses", default=None)
    p.add_argument("--resume-tex", default=None)
    p.add_argument("--cover-tex", default=None)
    p.add_argument("--date", default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--redo", action="store_true", help="alias for --force")
    p.add_argument("--force", action="store_true", help="Re-stage even if already processed")
    p.set_defaults(func=cmd_addresses)

    p = sub.add_parser("jd", help="Split / fetch / merge job descriptions")
    p.add_argument("--day", required=True)
    p.add_argument("--n", type=int, default=8)
    p.add_argument("--batch", type=int, default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--split", action="store_true")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--merge", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-fetch even if out_*.json exists")
    p.set_defaults(func=cmd_jd)

    p = sub.add_parser("resume", help="Tailor LaTeX resume + cover PDFs per job (requires LaTeX)")
    p.add_argument("--day", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--base-url", default=None)
    p.add_argument("--api-key", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--only", default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--dry", action="store_true", help="Skip LLM; use base_spec (still needs LaTeX for PDFs)")
    p.add_argument("--no-excel", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-tailor even if job folder already done")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("apply", help="Tier A sequential Playwright apply")
    p.add_argument("--excel", default=None)
    p.add_argument("--url", default=None)
    p.add_argument("--resume", default=None)
    p.add_argument("--cover", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--headed", action="store_true", default=True)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--chrome-profile", default=None,
                   help="Persistent Chrome user-data-dir (default: data/browser_state)")
    p.add_argument("--budget", type=int, default=180)
    p.set_defaults(func=cmd_apply)

    return ap


def main(argv=None):
    ensure_data_dirs()
    load_dotenv()
    apply_latex_env_from_config()
    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "headless", False):
        args.headed = False
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
