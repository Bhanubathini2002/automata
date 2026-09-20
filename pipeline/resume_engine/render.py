"""
LaTeX render hooks: escape, validate, fabricate guard, compile helpers.

Resume/cover PDFs require xelatex/pdflatex. Missing compilers fail clearly —
never silent-skip pretending a PDF exists.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent.parent

_BASE_PATH = ENGINE / "base_spec.json"
BASE_SPEC = json.loads(_BASE_PATH.read_text(encoding="utf-8")) if _BASE_PATH.is_file() else {}

_bl_path = ENGINE / "blocklist.json"
if _bl_path.is_file():
    BLOCKLIST = set(json.loads(_bl_path.read_text(encoding="utf-8")))
else:
    BLOCKLIST = {
        "kotlin", "swift", "xcode", "rust", "kafka", "scala", "golang", ".net", "c#", "php",
        "tensorrt", "vllm", "tgi", "sas", "dbt", "spring boot",
    }

FIXED_FACTS = [
    "Mondee", "Fremont, CA", "01/2023", "Present",
    "Cosmic Reality", "Missouri", "04/2020", "10/2022",
    "Northwest Missouri State University",
    "Master of Science in Applied Computer Science",
    "Claude Certified Architect",
]

LIMITS = dict(
    title=(3, 60),
    objective_words=(55, 95),
    profile=(4, 9),
    skills=(7, 10),
    mondee=(6, 10),
    cosmic=(4, 6),
)


class LatexNotFoundError(RuntimeError):
    """Raised when a required LaTeX engine cannot be located."""


def esc(s: str) -> str:
    s = str(s)
    s = s.replace("\\", r"\textbackslash{}")
    for a, b in [
        ("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"),
        ("$", r"\$"), ("{", r"\{"), ("}", r"\}"),
    ]:
        s = s.replace(a, b)
    s = s.replace("~", r"\textasciitilde{}").replace("^", r"\^{}")
    s = s.replace("—", "---").replace("–", "--")
    return s


def words(s):
    return len(re.findall(r"\S+", s or ""))


def pages(pdf):
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf).pages)
    except Exception:
        return -1


def _is_executable(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    if p.is_file():
        return os.access(path, os.X_OK) or os.name == "nt"
    return bool(shutil.which(path))


def _candidate_dirs() -> list[Path]:
    """Platform-generic MiKTeX / TeX Live search roots (no hardcoded usernames)."""
    dirs: list[Path] = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or ""
        prog = os.environ.get("ProgramFiles") or r"C:\Program Files"
        prog86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
        userprofile = os.environ.get("USERPROFILE") or ""
        for base in filter(None, [local, prog, prog86, userprofile]):
            dirs.extend([
                Path(base) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
                Path(base) / "MiKTeX" / "miktex" / "bin" / "x64",
                Path(base) / "miktex" / "miktex" / "bin" / "x64",
            ])
        # TeX Live under Program Files: TeX Live\YYYY\bin\windows
        for root in filter(None, [prog, prog86]):
            tl = Path(root) / "TeX Live"
            if tl.is_dir():
                for year_dir in sorted(tl.glob("*"), reverse=True):
                    dirs.append(year_dir / "bin" / "windows")
        # Also expand %LOCALAPPDATA%\Programs\MiKTeX\... pattern explicitly
        if local:
            dirs.insert(
                0,
                Path(local) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
            )
    else:
        dirs.extend([
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/Library/TeX/texbin"),  # macOS MacTeX
            Path.home() / "texlive" / "bin",
        ])
        # ~/texlive/YYYY/bin/<arch>
        home_tl = Path.home() / "texlive"
        if home_tl.is_dir():
            for year_dir in sorted(home_tl.glob("*"), reverse=True):
                bin_root = year_dir / "bin"
                if bin_root.is_dir():
                    for arch in bin_root.iterdir():
                        if arch.is_dir():
                            dirs.append(arch)
        # /usr/local/texlive/YYYY/bin/<arch>
        for root in (Path("/usr/local/texlive"), Path("/opt/texlive")):
            if root.is_dir():
                for year_dir in sorted(root.glob("*"), reverse=True):
                    bin_root = year_dir / "bin"
                    if bin_root.is_dir():
                        for arch in bin_root.iterdir():
                            if arch.is_dir():
                                dirs.append(arch)
    return dirs


def _find_engine(env_key: str, binary: str) -> str | None:
    """Resolve a LaTeX engine via env → PATH → common install locations."""
    env_val = (os.environ.get(env_key) or "").strip()
    if env_val and _is_executable(env_val):
        return env_val
    which = shutil.which(binary)
    if which:
        return which
    exe = f"{binary}.exe" if os.name == "nt" else binary
    for d in _candidate_dirs():
        cand = d / exe
        if cand.is_file() and _is_executable(str(cand)):
            return str(cand)
    return None


def find_xelatex() -> str | None:
    return _find_engine("XELATEX", "xelatex")


def find_pdflatex() -> str | None:
    return _find_engine("PDFLATEX", "pdflatex")


def require_latex(*, need_xelatex: bool = True, need_pdflatex: bool = True) -> dict[str, str]:
    """
    Return resolved engine paths or raise LatexNotFoundError with install hints.
    """
    xel = find_xelatex()
    pdl = find_pdflatex()
    missing = []
    if need_xelatex and not xel:
        missing.append("xelatex (set XELATEX or install MiKTeX / TeX Live)")
    if need_pdflatex and not pdl:
        missing.append("pdflatex (set PDFLATEX or install MiKTeX / TeX Live)")
    if missing:
        hint = (
            "Windows: https://miktex.org/  |  "
            "Linux: sudo apt install texlive-xetex texlive-latex-base  |  "
            "macOS: https://www.tug.org/mactex/"
        )
        raise LatexNotFoundError(
            "LaTeX required for resume/cover PDFs but not found: "
            + "; ".join(missing)
            + f". {hint}"
        )
    out: dict[str, str] = {}
    if xel:
        out["xelatex"] = xel
    if pdl:
        out["pdflatex"] = pdl
    return out


def latex_status() -> dict:
    """Non-raising status dict for doctor / UI."""
    xel = find_xelatex()
    pdl = find_pdflatex()
    return {
        "xelatex": xel,
        "pdflatex": pdl,
        "xelatex_ok": bool(xel),
        "pdflatex_ok": bool(pdl),
        "ok": bool(xel and pdl),
        "install_windows": "https://miktex.org/",
        "install_linux": "https://www.tug.org/texlive/  (or: sudo apt install texlive-xetex texlive-latex-recommended)",
        "install_macos": "https://www.tug.org/mactex/",
    }


_BASE_TEXT = json.dumps(BASE_SPEC, ensure_ascii=False).lower()


def _known(tok: str) -> bool:
    low = tok.lower().strip()
    if low in _BASE_TEXT:
        return True
    parts = [p for p in re.split(r"[\s\-]+", low) if len(p) > 2]
    return bool(parts) and all(p in _BASE_TEXT for p in parts)


def find_fabrications(spec) -> list:
    bad = set()
    for row in spec.get("skills", []) or []:
        if not isinstance(row, dict):
            continue
        for tok in re.split(r"[,;/()\[\]]", row.get("items", "")):
            tok = tok.strip(" .:")
            if not tok:
                continue
            low = tok.lower()
            if any(re.search(rf"\b{re.escape(b)}\b", low) for b in BLOCKLIST):
                bad.add(tok)
                continue
            if len(tok) > 2 and not _known(tok):
                bad.add(tok)
    prose = [spec.get("title", ""), spec.get("objective", "")]
    for b in (spec.get("profile") or []) + (spec.get("mondee_bullets") or []) + (spec.get("cosmic_bullets") or []):
        prose.append(b.get("text", "") if isinstance(b, dict) else str(b))
    low = " ".join(prose).lower()
    for bl in BLOCKLIST:
        if re.search(rf"\b{re.escape(bl)}\b", low):
            bad.add(bl)
    return sorted(bad)


def normalize(spec: dict) -> dict:
    s = dict(BASE_SPEC)
    for k, v in (spec or {}).items():
        if v not in (None, "", [], {}):
            s[k] = v
    prof = []
    for p in s.get("profile") or []:
        if isinstance(p, dict) and "text" in p:
            prof.append({"label": str(p.get("label", "")).strip(), "text": str(p["text"]).strip()})
        elif isinstance(p, str):
            prof.append({"label": "", "text": p.strip()})
    s["profile"] = prof
    s["skills"] = [
        r for r in (s.get("skills") or [])
        if isinstance(r, dict) and r.get("category") and r.get("items")
    ]
    s["mondee_bullets"] = [str(b).strip() for b in (s.get("mondee_bullets") or []) if str(b).strip()]
    s["cosmic_bullets"] = [str(b).strip() for b in (s.get("cosmic_bullets") or []) if str(b).strip()]
    s["title"] = str(s.get("title", "")).strip()[: LIMITS["title"][1]]
    ow = words(s.get("objective", ""))
    if ow < 20:
        s["objective"] = BASE_SPEC.get("objective", s.get("objective", ""))
    floors = {
        "profile": LIMITS["profile"][0],
        "skills": LIMITS["skills"][0],
        "mondee_bullets": LIMITS["mondee"][0],
        "cosmic_bullets": LIMITS["cosmic"][0],
    }
    for key, floor in floors.items():
        have = {
            json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x).lower()[:60]
            for x in s[key]
        }
        for item in BASE_SPEC.get(key) or []:
            if len(s[key]) >= floor:
                break
            sig = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item).lower()[:60]
            if sig not in have:
                s[key].append(item)
                have.add(sig)
    s["profile"] = s["profile"][: LIMITS["profile"][1]]
    s["skills"] = s["skills"][: LIMITS["skills"][1]]
    s["mondee_bullets"] = s["mondee_bullets"][: LIMITS["mondee"][1]]
    s["cosmic_bullets"] = s["cosmic_bullets"][: LIMITS["cosmic"][1]]
    return s


def validate(spec, city_st) -> list:
    errs = []
    if city_st and not re.fullmatch(r"[A-Za-z .\-]+, [A-Z]{2}", city_st):
        if not re.search(r"remote", city_st or "", re.I):
            errs.append(f"city_st must be 'City, ST' — got {city_st!r}")
    fab = find_fabrications(spec)
    if fab:
        errs.append("fabricated/blocked tech: " + ", ".join(fab))
    return errs


def write_resume_tex(job_dir: str, spec: dict, city_st: str, template_tex: str | None = None) -> str:
    """Fill a simple slot template or write a structured .tex body."""
    spec = normalize(spec)
    path = os.path.join(job_dir, "main.tex")
    if template_tex and os.path.isfile(template_tex):
        out = Path(template_tex).read_text(encoding="utf-8")
        replacements = {
            "TITLE": esc(spec["title"]),
            "CITY_ST": esc(city_st),
            "OBJECTIVE": esc(spec["objective"]),
        }
        for k, v in replacements.items():
            out = out.replace("{{" + k + "}}", v)
        Path(path).write_text(out, encoding="utf-8")
        return path

    lines = [
        r"% Auto-generated tailored resume body — compile with xelatex against your preamble",
        rf"% Title: {esc(spec['title'])} | {esc(city_st)}",
        r"\section*{Objective}",
        esc(spec["objective"]),
        r"\section*{Profile}",
        r"\begin{itemize}",
    ]
    for p in spec["profile"]:
        if p.get("label"):
            lines.append(rf"\item \textbf{{{esc(p['label'])}:}} {esc(p['text'])}")
        else:
            lines.append(rf"\item {esc(p['text'])}")
    lines += [r"\end{itemize}", r"\section*{Skills}", r"\begin{itemize}"]
    for r in spec["skills"]:
        lines.append(rf"\item \textbf{{{esc(r['category'])}:}} {esc(r['items'])}")
    lines += [r"\end{itemize}", r"\section*{Experience — Mondee}", r"\begin{itemize}"]
    for b in spec["mondee_bullets"]:
        lines.append(rf"\item {esc(b)}")
    lines += [r"\end{itemize}", r"\section*{Experience — Cosmic Reality}", r"\begin{itemize}"]
    for b in spec["cosmic_bullets"]:
        lines.append(rf"\item {esc(b)}")
    lines.append(r"\end{itemize}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_cover_tex(job_dir: str, cl: dict, company: str, title: str, city_st: str,
                    template_tex: str | None = None) -> str:
    path = os.path.join(job_dir, "coverletter.tex")
    if template_tex and os.path.isfile(template_tex):
        t = Path(template_tex).read_text(encoding="utf-8")
        for a, b in [
            ("<<COMPANY NAME>>", esc(company)),
            ("<<JOB TITLE>>", esc(title)),
            ("<<COMPANY CITY, STATE>>", esc(cl.get("addr") or city_st)),
        ]:
            t = t.replace(a, b)
        Path(path).write_text(t, encoding="utf-8")
        return path
    body = "\n\n".join(esc(cl.get(k, "")) for k in ("p1", "p2", "p3", "p4"))
    Path(path).write_text(
        f"% Cover letter for {esc(company)} — {esc(title)}\n"
        f"% Address: {esc(cl.get('addr') or city_st)}\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def compile_tex(cwd: str, engine: str, tex: str) -> tuple[bool, str]:
    """Compile once×2; return (ok, stderr_tail). Never claims success without PDF."""
    if not engine or not _is_executable(engine):
        return False, f"engine not executable: {engine!r}"
    last_err = ""
    for _ in range(2):
        try:
            r = subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error", tex],
                cwd=cwd, capture_output=True, text=True, timeout=180,
            )
            last_err = (r.stderr or r.stdout or "")[-800:]
            if r.returncode != 0:
                return False, last_err or f"exit {r.returncode}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
    pdf = os.path.join(cwd, Path(tex).with_suffix(".pdf").name)
    if not os.path.isfile(pdf):
        return False, f"compiler returned 0 but PDF missing: {pdf}"
    return True, ""


def build_job(job_dir: str, spec: dict, cl: dict, city_st: str, company: str, title: str,
              resume_template: str | None = None, cover_template: str | None = None,
              require_pdf: bool = True) -> dict:
    """Validate → write tex → compile to PDF. Fails clearly if LaTeX missing."""
    spec = normalize(spec)
    errs = validate(spec, city_st)
    if errs:
        return {"ok": False, "compiled": False, "stage": "validate", "errors": errs}

    write_resume_tex(job_dir, spec, city_st, resume_template)
    write_cover_tex(job_dir, cl or {}, company, title, city_st, cover_template)

    notes: list[str] = []
    resume_pdf = cover_pdf = None
    compile_errors: list[str] = []

    try:
        engines = require_latex(need_xelatex=True, need_pdflatex=True)
    except LatexNotFoundError as e:
        msg = str(e)
        if require_pdf:
            return {
                "ok": False,
                "compiled": False,
                "stage": "latex",
                "errors": [msg],
                "resume_pdf": None,
                "cover_pdf": None,
                "notes": [msg],
            }
        notes.append(msg)
        return {
            "ok": False,
            "compiled": False,
            "stage": "latex",
            "errors": [msg],
            "resume_pdf": None,
            "cover_pdf": None,
            "notes": notes,
        }

    xel = engines["xelatex"]
    pdl = engines["pdflatex"]

    ok_res, err_res = compile_tex(job_dir, xel, "main.tex")
    if ok_res:
        src = os.path.join(job_dir, "main.pdf")
        dst = os.path.join(job_dir, "Bhanu_Prakash_Bathini.pdf")
        shutil.copy(src, dst)
        resume_pdf = dst
        notes.append(f"resume pages={pages(dst)}")
    else:
        compile_errors.append(f"xelatex failed on main.tex: {err_res[:400]}")
        notes.append("xelatex failed — resume PDF not produced")

    ok_cl, err_cl = compile_tex(job_dir, pdl, "coverletter.tex")
    if ok_cl:
        src = os.path.join(job_dir, "coverletter.pdf")
        dst = os.path.join(job_dir, "Bhanu_Prakash_Bathini_Cover_Letter.pdf")
        shutil.copy(src, dst)
        cover_pdf = dst
        notes.append(f"cover pages={pages(dst)}")
    else:
        compile_errors.append(f"pdflatex failed on coverletter.tex: {err_cl[:400]}")
        notes.append("pdflatex failed — cover PDF not produced")

    compiled = bool(resume_pdf and cover_pdf and os.path.isfile(resume_pdf) and os.path.isfile(cover_pdf))
    if not compiled and require_pdf:
        return {
            "ok": False,
            "compiled": False,
            "stage": "compile",
            "errors": compile_errors or ["PDF compile failed"],
            "resume_pdf": resume_pdf,
            "cover_pdf": cover_pdf,
            "notes": notes,
        }

    return {
        "ok": compiled,
        "compiled": compiled,
        "resume_pdf": resume_pdf,
        "cover_pdf": cover_pdf,
        "notes": notes,
        "errors": compile_errors,
    }
