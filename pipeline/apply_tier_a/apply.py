"""
Tier A sequential Playwright auto-apply.

Hard rules (never weaken):
  - Skip ITAR / citizenship / clearance gates
  - Never enter SSN or DOB (fieldmap ABORT)
  - Mark applied ONLY on confirmation string/URL
  - One job at a time (sequential)
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import fieldmap as FM
from .capsolver import CapSolverClient
from .gmail_otp import GmailOTPHelper
from . import live_status

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"

# Excel columns (0-based) matching COMPLETE_WORKFLOW
COL_TITLE, COL_COMPANY, COL_LINK = 1, 2, 4
COL_RESUME, COL_COVER = 19, 21
COL_STATUS, COL_TS = 22, 23

# Rows with these statuses are skipped so mid-batch resume is safe.
TERMINAL_STATUSES = frozenset({
    "applied",
    "job_closed",
    "captcha",
    "blocked_platform",
    "aggregator",
    "gate_skip",
    "needs_human",
    "form_blocked",
    "left for LinkedIn - apply manually",
    "error",
})

BLOCKED_HOSTS = {
    "icims.com": "captcha",
    "jobs.bytedance.com": "captcha",
    "joinbytedance.com": "captcha",
    "careers.tiktok.com": "captcha",
    "app.jazz.co": "captcha",
    "applytojob.com": "captcha",
    "eightfold.ai": "form_blocked",
    "silkroad.com": "form_blocked",
    "contacthr.com": "form_blocked",
    "njoyn.com": "form_blocked",
    "dayforcehcm.com": "form_blocked",
}
AGGREGATORS = (
    "linkedin.com", "dice.com", "indeed.com", "ziprecruiter.com", "monster.com",
    "glassdoor.com", "jobdiva.com", "randstad", "consulting.us", "recruiter.com", "talent.com",
)

DEAD_RX = re.compile(
    r"no longer (available|accepting|open)|posting (has )?(closed|expired|been removed)"
    r"|job (not found|has been filled|is closed)|position (has been )?filled"
    r"|page (not found|doesn'?t exist)|404|requisition .{0,20}(closed|not found)"
    r"|this job is no longer|we're sorry.{0,40}(not|no longer)", re.I,
)
CONFIRM_RX = re.compile(
    r"thank you for (applying|your (application|interest|submission))"
    r"|application (was )?(successfully )?(submitted|received|complete|sent)"
    r"|successfully applied|your application has been (sent|received|submitted)"
    r"|we (have )?received your application|application submitted"
    r"|thanks for applying|submission (was )?successful|application (has been )?received|we.?ll be in touch|successfully submitted|your application was submitted", re.I,
)
CONFIRM_URL_RX = re.compile(
    r"/confirmation|/thanks|/success|application-success|applied=1"
    r"|/jobTasks/completed|/thank-?you", re.I,
)
GATE_RX = re.compile(
    r"(must|required to) (be|possess|hold|have).{0,40}(u\.?s\.?\s*citizen|security clearance|active clearance)"
    r"|(active|current|existing)\s+(ts/sci|top secret|secret|dod)\s+clearance"
    r"|clearance (is )?required|requires? .{0,20}clearance"
    r"|u\.?s\.?\s*citizenship (is )?required|must be a u\.?s\.? citizen"
    r"|\bitar\b|export control", re.I,
)
GATE_FALSE_POSITIVE = re.compile(
    r"equal opportunity|eeo|vevraa|affirmative action|without regard to"
    r"|regardless of|protected veteran|disability status|e-verify", re.I,
)


def _load_blocklist():
    p = ROOT / "config" / "blocklist.example.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("blocked_hosts") or BLOCKED_HOSTS, tuple(data.get("aggregators") or AGGREGATORS)
        except Exception:
            pass
    return BLOCKED_HOSTS, AGGREGATORS


def preclassify(url: str) -> tuple[str | None, str]:
    blocked, aggs = _load_blocklist()
    u = (url or "").lower()
    for host, why in blocked.items():
        if host in u:
            return ("captcha" if why == "captcha" else "blocked_platform"), f"blocked host {host}"
    if "linkedin.com" in u:
        return "left for LinkedIn - apply manually", "linkedin"
    for agg in aggs:
        if agg in u:
            return "aggregator", f"aggregator {agg}"
    return None, ""


def gate_scan(txt: str) -> str | None:
    for m in GATE_RX.finditer(txt or ""):
        ctx = (txt or "")[max(0, m.start() - 320): m.end() + 320]
        if GATE_FALSE_POSITIVE.search(ctx):
            continue
        return m.group(0)[:90]
    return None


def looks_dead(txt: str) -> bool:
    return bool(DEAD_RX.search((txt or "")[:1500]))


def confirm(page_or_url: str, body: str = "") -> str | None:
    if CONFIRM_URL_RX.search(page_or_url or ""):
        return f"url:{page_or_url[:120]}"
    m = CONFIRM_RX.search(body or "")
    if m:
        return m.group(0)[:120]
    return None


def dismiss_banners(page):
    ids = [
        "#truste-consent-button", "#onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyButtonAccept", ".cc-allow",
    ]
    for sel in ids:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=2000)
                page.wait_for_timeout(400)
        except Exception:
            pass


def has_blocking_captcha(page) -> bool:
    try:
        info = page.evaluate("""()=>{
          const fr=[...document.querySelectorAll('iframe')];
          const box=f=>f.getBoundingClientRect();
          const hard=fr.some(f=>/hcaptcha|turnstile|geetest|funcaptcha/i.test(f.src||''));
          const challenge=fr.some(f=>{const r=box(f);
            return /recaptcha.*bframe/i.test(f.src||'')&&f.offsetParent!==null&&r.height>100;});
          const v2=fr.some(f=>{const r=box(f);
            return /recaptcha.*anchor/i.test(f.src||'')&&f.offsetParent!==null
                   &&r.height>=70&&r.width>=270;});
          return {hard,v2,challenge};
        }""")
        return bool(info.get("hard") or info.get("v2") or info.get("challenge"))
    except Exception:
        return False


def label_for(el) -> str:
    try:
        return el.evaluate("""(el)=>{
          if(el.labels&&el.labels[0]) return el.labels[0].innerText;
          const id=el.id; if(id){const l=document.querySelector('label[for="'+id+'"]');
            if(l) return l.innerText;}
          const wrap=el.closest('label'); if(wrap) return wrap.innerText;
          return el.getAttribute('aria-label')||el.getAttribute('placeholder')
                 ||el.getAttribute('name')||el.id||'';
        }""") or ""
    except Exception:
        return ""



def click_yes_no_for_question(page, question_rx: str, want_yes: bool) -> bool:
    """Click Yes/No near a question — Ashby often uses buttons/divs, not radios."""
    import re as _re
    label = "Yes" if want_yes else "No"
    try:
        # Playwright text locators (more reliable than DOM heuristics)
        q = page.get_by_text(_re.compile(question_rx, _re.I)).first
        if q.count() == 0:
            return False
        # scope: ancestor section
        root = q.locator("xpath=ancestor::*[self::section or self::fieldset or self::div][1]")
        btn = root.get_by_text(label, exact=True).first
        if btn.count() == 0:
            btn = page.get_by_role("radio", name=label).first
        if btn.count() == 0:
            return False
        btn.scroll_into_view_if_needed(timeout=3000)
        btn.click(timeout=5000, force=True)
        page.wait_for_timeout(400)
        return True
    except Exception:
        # fallback evaluate
        try:
            return bool(page.evaluate(
                """({q, yes})=>{
                  const re=new RegExp(q,'i');
                  const nodes=[...document.querySelectorAll('label,div,span,p,legend,h1,h2,h3,h4')];
                  const qn=nodes.find(n=>re.test((n.innerText||'').trim()) && (n.innerText||'').length<240);
                  if(!qn) return false;
                  let root=qn.parentElement;
                  for(let i=0;i<8 && root;i++){
                    const opts=[...root.querySelectorAll('label,button,[role=radio],input[type=radio],div,span')];
                    const hit=opts.find(o=>{
                      const t=(o.innerText||o.getAttribute('aria-label')||o.value||'').trim();
                      return yes ? /^yes$/i.test(t) : /^no$/i.test(t);
                    });
                    if(hit){ hit.click(); return true; }
                    root=root.parentElement;
                  }
                  return false;
                }""",
                {"q": question_rx, "yes": want_yes},
            ))
        except Exception:
            return False


def wait_uploads_idle(page, timeout_s: float = 45) -> None:
    """Ashby blocks submit while: We're updating your forms (e.g. uploading files)..."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            body = page.evaluate("()=>document.body.innerText") or ""
        except Exception:
            break
        if not re.search(r"updating your forms|uploading files|please try again when", body, re.I):
            return
        page.wait_for_timeout(1000)



def fill_ashby_required_radios(page) -> int:
    """Fill common required Yes/No pairs that Ashby surfaces as validation errors."""
    n = 0
    pairs = [
        (r"unrestricted work authorization|authorized to work", True),   # Yes
        (r"require (employment-based )?visa sponsorship|require sponsorship", False),  # No
    ]
    for rx, want_yes in pairs:
        if click_yes_no_for_question(page, rx, want_yes):
            n += 1
    return n



def fix_missing_required(page) -> int:
    """Read Ashby/Greenhouse validation errors and satisfy them."""
    n = 0
    try:
        body = page.evaluate("()=>document.body.innerText") or ""
    except Exception:
        return 0
    # Always enforce work-auth pair (most common blocker)
    n += fill_ashby_required_radios(page)
    for m in re.finditer(r"Missing entry for required field:\s*(.+)", body, re.I):
        label = m.group(1).strip().split("\n")[0][:120]
        low = label.lower()
        if re.search(r"authori[sz]ation|authorized to work", low):
            if click_yes_no_for_question(page, r"unrestricted work authorization|authorized to work", True):
                n += 1
        elif re.search(r"sponsor", low):
            if click_yes_no_for_question(page, r"require .*sponsorship|require sponsorship", False):
                n += 1
        else:
            # try fieldmap resolve + fill by label text
            want = FM.resolve(label)
            if want and want not in (FM.ABORT, FM.PREFER_NOT, None, ""):
                try:
                    # click/fill best-effort via evaluate
                    page.evaluate(
                        """({lab, val})=>{
                          const re=new RegExp(lab.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'i');
                          const labs=[...document.querySelectorAll('label')];
                          const L=labs.find(x=>re.test((x.innerText||'').trim()));
                          if(!L) return false;
                          const id=L.getAttribute('for');
                          const el=id?document.getElementById(id):L.querySelector('input,textarea,select');
                          if(!el) return false;
                          if(el.type==='radio'||el.type==='checkbox'){ el.click(); return true; }
                          el.focus(); el.value=val; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
                        }""",
                        {"lab": label[:80], "val": str(want)[:500]},
                    )
                    n += 1
                except Exception:
                    pass
    return n


def click_submit_application(page) -> bool:
    """Prefer the real Submit Application button."""
    try:
        return bool(page.evaluate(
            """()=>{
              const re=/^\s*submit application\s*$/i;
              const els=[...document.querySelectorAll('button,a,input[type=submit],span[role=button]')];
              const hit=els.find(e=>e.offsetParent!==null && re.test((e.innerText||e.value||'').trim()));
              if(hit){ hit.click(); return true; }
              const re2=/submit application/i;
              const hit2=els.find(e=>e.offsetParent!==null && re2.test((e.innerText||e.value||'').trim())
                && !/sign in|log in/i.test(e.innerText||''));
              if(hit2){ hit2.click(); return true; }
              return false;
            }"""
        ))
    except Exception:
        return False


def upload_resume_files(page, resume: str = "", cover: str = "") -> int:
    """Ashby/Greenhouse often hide file inputs — set files even if not visible."""
    n = 0
    if not resume or not os.path.isfile(resume):
        return 0
    try:
        handles = page.query_selector_all("input[type=file]")
    except Exception:
        return 0
    for el in handles:
        try:
            lab = label_for(el)
            path = resume
            if re.search(r"cover", lab, re.I) and cover and os.path.isfile(cover):
                path = cover
            elif lab and not re.search(r"resume|cv|upload|file|attach", lab, re.I):
                # skip unrelated file inputs when labeled something else
                if re.search(r"transcript|portfolio|other", lab, re.I):
                    continue
            el.set_input_files(path)
            n += 1
        except Exception:
            continue
    return n


def fill_visible_fields(page, resume: str = "", cover: str = "") -> dict:
    """Fill mapped fields; abort on legal attestation. Returns stats."""
    filled, unmapped, aborted = 0, [], None
    filled += upload_resume_files(page, resume, cover)
    filled += fill_ashby_required_radios(page)
    try:
        handles = page.query_selector_all("input, select, textarea")
    except Exception:
        return {"filled": filled, "unmapped": [], "aborted": None}
    for el in handles:
        try:
            typ = (el.get_attribute("type") or "").lower()
            if typ == "file":
                continue  # handled above (including hidden)
            if not el.is_visible():
                continue
            if typ in ("hidden", "submit", "button", "image", "reset"):
                continue
            if el.is_disabled():
                continue
            lab = label_for(el)
            want = FM.resolve(lab)
            if want == FM.ABORT:
                aborted = lab[:80]
                break
            if want is None or want == "":
                if el.get_attribute("required") is not None:
                    unmapped.append(lab[:60] or typ)
                continue
            if want == FM.PREFER_NOT:
                continue
            tag = el.evaluate("e=>e.tagName").lower()
            if tag == "select":
                opts = el.evaluate("e=>[...e.options].map(o=>o.text)")
                choice = FM.fuzzy_option(want if want != FM.PREFER_NOT else FM.PREFER_NOT, opts)
                if choice and FM.polarity_safe(want if want != FM.PREFER_NOT else "prefer not", choice):
                    el.select_option(label=choice)
                    filled += 1
                continue
            if typ in ("checkbox", "radio"):
                if str(want).lower() in ("yes", "true", "1") or want == "Yes":
                    el.check(force=True)
                    filled += 1
                continue
            el.fill("")
            el.fill(str(want)[:2000])
            filled += 1
        except Exception:
            continue
    return {"filled": filled, "unmapped": unmapped[:20], "aborted": aborted}


def click_apply_or_submit(page, prefer_submit: bool = False) -> bool:
    pattern = (
        r"submit application|submit your application|send application|finish application|complete application"
        if prefer_submit
        else r"apply now|apply for this job|apply to this job|apply without an account|start application|continue|next|^apply$"
    )
    try:
        clicked = page.evaluate(
            """(rx)=>{
              const re=new RegExp(rx,'i');
              const els=[...document.querySelectorAll('button,a,input[type=submit],span[role=button]')];
              const hit=els.find(e=>e.offsetParent!==null && re.test((e.innerText||e.value||'').trim())
                && !/sign in|log in|create account/i.test(e.innerText||''));
              if(hit){hit.click(); return true;} return false;
            }""",
            pattern,
        )
        return bool(clicked)
    except Exception:
        return False


def apply_to(
    url: str,
    *,
    resume: str = "",
    cover_letter: str = "",
    chrome_profile: str = "",
    headless: bool = False,
    dry_run: bool = False,
    budget_s: int = 180,
    use_capsolver: bool = True,
) -> dict[str, Any]:
    """Apply to one URL. Sequential caller must not parallelize."""
    t0 = time.time()
    status, detail = "error", ""
    filled_stats: dict = {}

    st, why = preclassify(url)
    if st:
        return {"status": st, "detail": why, "url": url, "elapsed": 0, "filled": 0}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "error",
            "detail": "playwright not installed - pip install playwright && playwright install chromium",
            "url": url,
            "elapsed": 0,
        }

    # Durable default: data/browser_state - log into Gmail once; sessions persist.
    user_data = (
        chrome_profile
        or os.environ.get("CHROME_USER_DATA_DIR")
        or str(DATA / "browser_state")
    )
    Path(user_data).mkdir(parents=True, exist_ok=True)
    cap = CapSolverClient() if use_capsolver else None
    otp = GmailOTPHelper()

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data,
                headless=headless,
                channel="chrome" if os.name == "nt" else None,
                args=["--disable-blink-features=AutomationControlled"],
                accept_downloads=True,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            live_status.update(state="running", url=url, action="opened job page", message=f"Opened {url}")
            page.wait_for_timeout(3500)
            dismiss_banners(page)
            body = ""
            try:
                body = page.evaluate("()=>document.body.innerText") or ""
            except Exception:
                pass

            if looks_dead(body):
                status, detail = "job_closed", "dead posting"
            else:
                gate = gate_scan(body)
                if gate:
                    status, detail = "gate_skip", f"eligibility gate: {gate}"
                elif has_blocking_captcha(page):
                    # CapSolver attempt for visible reCAPTCHA only (not hCaptcha)
                    solved = False
                    if cap and cap.configured:
                        try:
                            sitekey = page.evaluate(
                                """()=>{const el=document.querySelector('[data-sitekey]');
                                   return el?el.getAttribute('data-sitekey'):'';}"""
                            )
                            if sitekey:
                                token = cap.solve_recaptcha_v2(page.url, sitekey)
                                if token:
                                    page.evaluate(
                                        """(t)=>{const ta=document.querySelector('#g-recaptcha-response,textarea[name=g-recaptcha-response]');
                                           if(ta){ta.value=t; ta.style.display='block';}
                                           if(window.___grecaptcha_cfg){/* injected */} }""",
                                        token,
                                    )
                                    solved = True
                        except Exception as e:
                            detail = f"capsolver: {e}"
                    if not solved:
                        status, detail = "captcha", detail or "blocking captcha"
                else:
                    click_apply_or_submit(page, prefer_submit=False)
                    page.wait_for_timeout(2500)
                    if len(context.pages) > 1:
                        page = context.pages[-1]
                        page.bring_to_front()
                    dismiss_banners(page)
                    filled_stats = {"filled": 0, "unmapped": [], "aborted": None}
                    confirmed = False
                    # Multi-step ATS (Ashby/Greenhouse): fill -> Next/Continue/Submit up to 8 rounds
                    for step in range(12):
                        live_status.update(action=f"wizard step {step+1}/8", message=f"Filling / navigating step {step+1}")
                        if time.time() - t0 > budget_s:
                            break
                        dismiss_banners(page)
                        # OTP / magic-link assist
                        try:
                            otp.maybe_handle(page, context)
                        except Exception:
                            pass
                        stats = fill_visible_fields(page, resume, cover_letter)
                        fill_ashby_required_radios(page)
                        filled_stats["filled"] = filled_stats.get("filled", 0) + int(stats.get("filled") or 0)
                        filled_stats["unmapped"] = stats.get("unmapped") or filled_stats.get("unmapped") or []
                        if stats.get("aborted"):
                            filled_stats["aborted"] = stats["aborted"]
                            break
                        try:
                            body2 = page.evaluate("()=>document.body.innerText") or ""
                        except Exception:
                            body2 = ""
                        if CONFIRM_RX.search(body2) or CONFIRM_URL_RX.search(page.url or ""):
                            confirmed = True
                            break
                        # validation errors left?
                        if re.search(r"is required|please (upload|attach|enter|complete)|fix\'t forget", body2, re.I):
                            # try one more fill pass then continue
                            fill_visible_fields(page, resume, cover_letter)
                        # Next vs Submit: prefer Next/Continue early, Submit late
                        # Fix validation errors before clicking submit
                        fix_missing_required(page)
                        wait_uploads_idle(page)
                        if step >= 1:
                            clicked = click_submit_application(page)
                            if not clicked:
                                clicked = click_apply_or_submit(page, prefer_submit=True)
                        else:
                            clicked = click_apply_or_submit(page, prefer_submit=False)
                        if not clicked:
                            clicked = click_submit_application(page) or click_apply_or_submit(page, prefer_submit=True)
                        page.wait_for_timeout(3500)
                        if len(context.pages) > 1:
                            page = context.pages[-1]
                            page.bring_to_front()
                        try:
                            body3 = page.evaluate("()=>document.body.innerText") or ""
                        except Exception:
                            body3 = ""
                        if CONFIRM_RX.search(body3) or CONFIRM_URL_RX.search(page.url or ""):
                            confirmed = True
                            break
                    if filled_stats.get("aborted"):
                        status, detail = "gate_skip", f"ABORT field: {filled_stats['aborted']}"
                    elif dry_run:
                        status, detail = "needs_human", "dry_run - filled, not submitted"
                    elif confirmed:
                        status, detail = "applied", "confirmation detected"
                    elif filled_stats.get("unmapped"):
                        status, detail = "needs_human", "unmapped: " + ", ".join(filled_stats["unmapped"][:8])
                    else:

                        fix_missing_required(page)
                        wait_uploads_idle(page)
                        click_submit_application(page)
                        page.wait_for_timeout(5000)
                        # spam retry once (Ashby anti-bot)
                        try:
                            _bspam = page.evaluate("()=>document.body.innerText") or ""
                        except Exception:
                            _bspam = ""
                        if looks_spam_flag(_bspam):
                            live_status.update(action="spam flag — slow retry", message="Ashby spam filter; waiting then resubmit")
                            page.wait_for_timeout(12000)
                            fix_missing_required(page)
                            wait_uploads_idle(page)
                            click_submit_application(page)
                            page.wait_for_timeout(8000)
                        try:
                            body_final = page.evaluate("()=>document.body.innerText") or ""
                        except Exception:
                            body_final = ""
                        if CONFIRM_RX.search(body_final) or CONFIRM_URL_RX.search(page.url or ""):
                            status, detail = "applied", "confirmation detected (final pass)"
                        elif re.search(r"Missing entry for required field", body_final, re.I):
                            status, detail = "needs_human", "still missing required after retries"
                        elif looks_spam_flag(body_final):
                            status, detail = "needs_human", "ATS spam filter - turn off VPN/extensions and retry"
                        else:
                            status, detail = "form_blocked", "no confirmation after submit"
            # OTP hook (no-op unless page looks like a verify screen)
            try:
                if re.search(r"verif|one.?time|enter.?code|otp", body[:2000], re.I) and otp.configured:
                    code = otp.fetch_otp(wait_s=45)
                    if code:
                        page.fill("input[type=text],input[type=tel],input[name*=code]", code)
                        detail = (detail + f" | otp:{code[:2]}****")[:150]
            except Exception:
                pass
            context.close()
    except Exception as e:
        status = "error"
        detail = f"{type(e).__name__}: {e}"[:200]
        traceback.print_exc()

    live_status.update(
        state="done" if status == "applied" else ("watching" if status in ("needs_human", "form_blocked") else "idle"),
        status=status,
        detail=detail,
        url=url,
        filled=filled_stats.get("filled", 0),
        unmapped=filled_stats.get("unmapped", []),
        action=f"finished: {status}",
        message=detail or status,
    )
    return {
        "status": status,
        "detail": detail,
        "url": url,
        "elapsed": round(time.time() - t0, 1),
        "filled": filled_stats.get("filled", 0),
        "unmapped": filled_stats.get("unmapped", []),
    }


def write_status(xlsx: str, wb, ws, row: int, status: str, detail: str) -> bool:
    """Flush status to Excel immediately (after EACH job)."""
    ws.cell(row=row, column=COL_STATUS + 1).value = status
    ws.cell(row=row, column=COL_TS + 1).value = (
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + " | " + (detail or "")[:150]
    )
    for attempt in range(3):
        try:
            wb.save(xlsx)
            return True
        except PermissionError:
            time.sleep(3)
    logdir = DATA / "applications" / datetime.date.today().strftime("%Y-%m-%d")
    logdir.mkdir(parents=True, exist_ok=True)
    with open(logdir / "pending_excel_writes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"row": row, "status": status, "detail": detail}) + "\n")
    return False


def run_excel_batch(
    excel: str,
    *,
    limit: int = 0,
    dry_run: bool = False,
    headed: bool = True,
    chrome_profile: str = "",
    budget_s: int = 180,
) -> dict[str, Any]:
    """Sequential one-by-one apply over pending Excel rows.

    Skips rows whose status is already terminal. Flushes Excel after EACH job
    so a crash mid-batch can resume without re-applying.
    """
    import openpyxl

    wb = openpyxl.load_workbook(excel)
    ws = wb.active
    rows = []
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not r or len(r) <= COL_LINK or not r[COL_LINK]:
            continue
        status = str(r[COL_STATUS] or "").strip() if len(r) > COL_STATUS else ""
        # Skip terminal / already-processed rows - enables mid-batch resume
        if status and status.lower() in {s.lower() for s in TERMINAL_STATUSES}:
            continue
        if status:
            # Any other non-empty status also treated as done (idempotent)
            continue
        resume = str(r[COL_RESUME] or "").strip() if len(r) > COL_RESUME else ""
        cover = str(r[COL_COVER] or "").strip() if len(r) > COL_COVER else ""
        rows.append({
            "row": i,
            "title": str(r[COL_TITLE] or "")[:60],
            "company": str(r[COL_COMPANY] or "")[:34],
            "url": str(r[COL_LINK]).strip(),
            "resume": resume,
            "cover": cover,
        })
    if limit:
        rows = rows[:limit]

    counts: dict[str, int] = {}
    logdir = DATA / "applications" / datetime.date.today().strftime("%Y-%m-%d")
    logdir.mkdir(parents=True, exist_ok=True)
    jsonl = logdir / "tier_a_runner.jsonl"

    for rec in rows:  # SEQUENTIAL - never parallel
        print(f"-> row {rec['row']} {rec['company']} | {rec['title'][:40]}", flush=True)
        live_status.update(state="running", company=rec.get("company"), title=rec.get("title"), url=rec.get("url"), action="applying", row=rec.get("row"))
        result = apply_to(
            rec["url"],
            resume=rec["resume"],
            cover_letter=rec["cover"],
            chrome_profile=chrome_profile,
            headless=not headed,
            dry_run=dry_run,
            budget_s=budget_s,
        )
        write_status(excel, wb, ws, rec["row"], result["status"], result.get("detail", ""))
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        with open(jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps({**rec, **result}) + "\n")
        print(f"   {result['status']} ({result.get('elapsed')}s) {result.get('detail','')[:80]}", flush=True)

    return {"processed": len(rows), "counts": counts, "excel": excel, "log": str(jsonl)}
