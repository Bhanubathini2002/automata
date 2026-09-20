"""
Automata - Streamlit UI
  streamlit run ui/app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from pipeline.config_io import (
    load_config, save_config, load_dotenv, save_dotenv, ensure_data_dirs, secret,
    default_chrome_user_data_dir, apply_latex_env_from_config,
)

st.set_page_config(page_title="Automata", page_icon="⚙️", layout="wide")
ensure_data_dirs()
load_dotenv()

st.title("Automata")
st.caption("Job Search Automation - post-scrape pipeline")

with st.expander("Workflow overview", expanded=True):
    st.markdown(
        """
**Pipeline (no Jobright scraper in this package):**

1. **Filter** - dedupe, drop excluded companies & 6+ yrs experience, split by role  
2. **Addresses** - match location -> address book, stage per-job folders + Excel columns  
3. **JD fetch** - split batches -> fetch/distill job descriptions -> merge into Excel  
4. **Resume + cover** - LLM JSON tailor -> **LaTeX required** -> PDF (2-page resume / 1-page cover)  
5. **Apply (Tier A)** - sequential Playwright with persistent Chrome profile (`data/browser_state`), CapSolver, Gmail OTP  

**Hard apply rules:** skip ITAR/citizen/clearance · never SSN/DOB · mark `applied` only on confirmation · one job at a time.

**Persistence:** Chrome user-data-dir defaults to `data/browser_state` - log into Gmail once; sessions survive restarts. Apply skips terminal statuses and flushes Excel after each job (mid-batch resume).
        """
    )

tab_setup, tab_run, tab_status = st.tabs(["Setup wizard", "Run dashboard", "Config status"])

# Always reload last saved values from disk
if "cfg_tick" not in st.session_state:
    st.session_state.cfg_tick = 0

cfg = load_config()
apply_latex_env_from_config(cfg)

with tab_setup:
    c_reload, _ = st.columns([1, 3])
    with c_reload:
        if st.button("Reload config.yaml + .env"):
            load_dotenv()
            cfg = load_config()
            apply_latex_env_from_config(cfg)
            st.session_state.cfg_tick += 1
            st.success("Reloaded from disk.")

    st.subheader("LaTeX (required for resume/cover PDFs)")
    from pipeline.resume_engine.render import latex_status
    lst = latex_status()
    if lst["ok"]:
        st.success(f"LaTeX OK - xelatex: `{lst['xelatex']}` · pdflatex: `{lst['pdflatex']}`")
    else:
        st.error("LaTeX missing - resume/cover PDF generation will fail until installed.")
        st.markdown(
            f"- **Windows (MiKTeX):** [{lst['install_windows']}]({lst['install_windows']})\n"
            f"- **Linux (TeX Live):** [{lst['install_linux']}]({lst['install_linux']})\n"
            f"- **macOS (MacTeX):** [{lst['install_macos']}]({lst['install_macos']})"
        )
        if not lst["xelatex_ok"]:
            st.warning("xelatex not found")
        if not lst["pdflatex_ok"]:
            st.warning("pdflatex not found")

    lx1, lx2 = st.columns(2)
    with lx1:
        xelatex_path = st.text_input(
            "XELATEX path (optional override)",
            cfg.get("xelatex_path", "") or os.environ.get("XELATEX", ""),
            key=f"xelatex_{st.session_state.cfg_tick}",
            help="Full path to xelatex.exe / xelatex if not on PATH",
        )
    with lx2:
        pdflatex_path = st.text_input(
            "PDFLATEX path (optional override)",
            cfg.get("pdflatex_path", "") or os.environ.get("PDFLATEX", ""),
            key=f"pdflatex_{st.session_state.cfg_tick}",
            help="Full path to pdflatex.exe / pdflatex if not on PATH",
        )

    st.subheader("Paths & models")
    c1, c2 = st.columns(2)
    with c1:
        jobs_excel = st.text_input(
            "Jobs Excel (raw or role-split)",
            cfg.get("jobs_excel", ""),
            key=f"jobs_{st.session_state.cfg_tick}",
        )
        addresses_excel = st.text_input(
            "Addresses Excel",
            cfg.get("addresses_excel", ""),
            key=f"addr_{st.session_state.cfg_tick}",
        )
        base_resume = st.text_input(
            "Base resume.tex",
            cfg.get("base_resume_tex", ""),
            key=f"bres_{st.session_state.cfg_tick}",
        )
        base_cover = st.text_input(
            "Base cover.tex",
            cfg.get("base_cover_tex", ""),
            key=f"bcov_{st.session_state.cfg_tick}",
        )
        ats_prompt = st.text_input(
            "ATS prompt (.md, optional)",
            cfg.get("ats_prompt", ""),
            key=f"ats_{st.session_state.cfg_tick}",
        )
    with c2:
        llm_base = st.text_input(
            "LLM base URL",
            cfg.get("llm_base_url", "https://api.deepseek.com/v1"),
            key=f"llmbase_{st.session_state.cfg_tick}",
        )
        llm_model = st.text_input(
            "LLM model",
            cfg.get("llm_model", "deepseek-chat"),
            key=f"llmmodel_{st.session_state.cfg_tick}",
        )
        default_chrome = str(default_chrome_user_data_dir())
        chrome_profile = st.text_input(
            "Chrome profile path (persistent)",
            cfg.get("chrome_profile_path", "") or os.environ.get("CHROME_USER_DATA_DIR", "") or default_chrome,
            key=f"chrome_{st.session_state.cfg_tick}",
            help="Default: data/browser_state - one-time Gmail login persists here",
        )
        default_city = st.text_input(
            "Default City, ST",
            cfg.get("default_city_st", "Houston, TX"),
            key=f"city_{st.session_state.cfg_tick}",
        )

    st.subheader("Secrets (saved to `.env` - never committed)")
    s1, s2 = st.columns(2)
    with s1:
        llm_key = st.text_input(
            "LLM API key",
            secret("LLM_API_KEY"),
            type="password",
            key=f"llmkey_{st.session_state.cfg_tick}",
        )
        cap_key = st.text_input(
            "CapSolver API key",
            secret("CAPSOLVER_API_KEY"),
            type="password",
            key=f"cap_{st.session_state.cfg_tick}",
        )
    with s2:
        apply_email = st.text_input(
            "Apply / Gmail email",
            secret("APPLY_EMAIL") or secret("GMAIL_ADDRESS"),
            key=f"email_{st.session_state.cfg_tick}",
        )
        apply_pw = st.text_input(
            "Apply / Gmail password",
            secret("APPLY_PASSWORD") or secret("GMAIL_PASSWORD"),
            type="password",
            key=f"pw_{st.session_state.cfg_tick}",
        )

    if st.button("Save configuration", type="primary"):
        new_cfg = {
            **cfg,
            "jobs_excel": jobs_excel,
            "addresses_excel": addresses_excel,
            "base_resume_tex": base_resume,
            "base_cover_tex": base_cover,
            "ats_prompt": ats_prompt,
            "llm_base_url": llm_base,
            "llm_model": llm_model,
            "chrome_profile_path": chrome_profile or default_chrome,
            "xelatex_path": xelatex_path,
            "pdflatex_path": pdflatex_path,
            "default_city_st": default_city,
            "output_root": str(ROOT / "data"),
        }
        save_config(new_cfg)
        env_payload = {
            "LLM_BASE_URL": llm_base,
            "LLM_MODEL": llm_model,
            "LLM_API_KEY": llm_key,
            "CAPSOLVER_API_KEY": cap_key,
            "APPLY_EMAIL": apply_email,
            "APPLY_PASSWORD": apply_pw,
            "GMAIL_ADDRESS": apply_email,
            "GMAIL_PASSWORD": apply_pw,
            "CHROME_USER_DATA_DIR": chrome_profile or default_chrome,
        }
        if xelatex_path:
            env_payload["XELATEX"] = xelatex_path
        if pdflatex_path:
            env_payload["PDFLATEX"] = pdflatex_path
        save_dotenv(env_payload)
        apply_latex_env_from_config(new_cfg)
        st.success("Saved non-secrets -> `data/config.yaml` · secrets -> `.env`")
        cfg = new_cfg

with tab_run:
    st.subheader("Run a stage")
    if st.button("Run doctor (preflight)"):
        import subprocess
        r = subprocess.run(
            [sys.executable, "-m", "pipeline.run", "doctor", "--skip-playwright-probe"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        st.code(r.stdout or r.stderr)
        if r.returncode != 0:
            st.error("Doctor failed - fix LaTeX / imports / .env before resume stage.")

    stage = st.selectbox(
        "Stage",
        ["filter", "addresses", "jd (split+fetch+merge)", "resume", "apply"],
    )
    day = st.text_input("Day tag (M_D_YYYY)", "")
    limit = st.number_input("Apply limit (0 = all pending)", min_value=0, value=5)
    dry = st.checkbox("Dry run (resume: no LLM / apply: fill but don't submit)", value=True)
    force = st.checkbox("Force re-run (ignore already-done folders)", value=False)

    if st.button("Run stage"):
        import subprocess
        env = os.environ.copy()
        if cfg.get("xelatex_path"):
            env["XELATEX"] = cfg["xelatex_path"]
        if cfg.get("pdflatex_path"):
            env["PDFLATEX"] = cfg["pdflatex_path"]
        py = sys.executable
        log = st.empty()
        try:
            if stage == "filter":
                excel = cfg.get("jobs_excel") or ""
                if not excel:
                    st.error("Set Jobs Excel in Setup")
                else:
                    cmd = [py, "-m", "pipeline.run", "filter", "--excel", excel]
                    if day:
                        cmd += ["--tag", day]
                    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env)
                    log.code(r.stdout or r.stderr)
            elif stage == "addresses":
                excel = cfg.get("jobs_excel") or ""
                addr = cfg.get("addresses_excel") or ""
                cmd = [py, "-m", "pipeline.run", "addresses", "--excel", excel, "--addresses", addr]
                if cfg.get("base_resume_tex"):
                    cmd += ["--resume-tex", cfg["base_resume_tex"]]
                if cfg.get("base_cover_tex"):
                    cmd += ["--cover-tex", cfg["base_cover_tex"]]
                if day:
                    cmd += ["--date", day]
                if force:
                    cmd.append("--force")
                r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env)
                log.code(r.stdout or r.stderr)
            elif stage.startswith("jd"):
                if not day:
                    st.error("Day tag required")
                else:
                    for flag in ("--split", "--fetch", "--merge"):
                        cmd = [py, "-m", "pipeline.run", "jd", "--day", day, flag]
                        if force and flag == "--fetch":
                            cmd.append("--force")
                        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env)
                        st.write(flag, "->")
                        st.code(r.stdout or r.stderr)
            elif stage == "resume":
                if not day:
                    st.error("Day tag required")
                else:
                    if not lst["ok"]:
                        st.error("LaTeX not found - install MiKTeX/TeX Live before generate-resumes.")
                    cmd = [py, "-m", "pipeline.run", "resume", "--day", day]
                    if dry:
                        cmd.append("--dry")
                    if force:
                        cmd.append("--force")
                    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env)
                    log.code(r.stdout or r.stderr)
            elif stage == "apply":
                excel = cfg.get("jobs_excel") or ""
                if day:
                    upd = ROOT / "data" / "Input" / day / "updated"
                    hits = list(upd.glob("*_updated.xlsx")) if upd.is_dir() else []
                    if hits:
                        excel = str(hits[0])
                if not excel:
                    st.error("No Excel path")
                else:
                    cmd = [py, "-m", "pipeline.run", "apply", "--excel", excel, "--headed"]
                    if dry:
                        cmd.append("--dry")
                    if limit:
                        cmd += ["--limit", str(int(limit))]
                    chrome = cfg.get("chrome_profile_path") or str(default_chrome_user_data_dir())
                    cmd += ["--chrome-profile", chrome]
                    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env)
                    log.code(r.stdout or r.stderr)
        except Exception as e:
            st.exception(e)

    st.markdown("---")
    st.code(
        "cd /path/to/automata\n"
        "python -m pipeline.run doctor\n"
        "python -m pipeline.run --help\n"
        "streamlit run ui/app.py",
        language="bash",
    )

with tab_status:
    st.subheader("Current config (reloaded from disk)")
    cfg_now = load_config()
    safe = {k: v for k, v in cfg_now.items()}
    st.json(safe)
    st.write("`.env` present:", (ROOT / ".env").is_file())
    st.write("LLM key set:", bool(secret("LLM_API_KEY")))
    st.write("CapSolver key set:", bool(secret("CAPSOLVER_API_KEY")))
    st.write("Apply email set:", bool(secret("APPLY_EMAIL") or secret("GMAIL_ADDRESS")))
    lst2 = latex_status()
    st.write("xelatex:", lst2["xelatex"] or "MISSING")
    st.write("pdflatex:", lst2["pdflatex"] or "MISSING")
    st.write("Chrome profile:", cfg_now.get("chrome_profile_path") or str(default_chrome_user_data_dir()))
    st.info("Secrets are never shown in full here after save. Config fields show last saved values.")
