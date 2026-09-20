"""Doctor + LaTeX discovery: no hardcoded usernames; clear failure when missing."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.resume_engine import render
from pipeline import doctor


class TestLatexDiscovery(unittest.TestCase):
    def test_no_hardcoded_bbath_path(self):
        src = Path(render.__file__).read_text(encoding="utf-8")
        self.assertNotIn(r"C:\Users\bbath", src)
        self.assertNotIn("bbath", src.lower())

    def test_find_respects_env(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / ("xelatex.exe" if os.name == "nt" else "xelatex")
            fake.write_text("#!/bin/sh\n", encoding="utf-8")
            fake.chmod(0o755)
            with mock.patch.dict(os.environ, {"XELATEX": str(fake)}, clear=False):
                found = render.find_xelatex()
            self.assertEqual(found, str(fake))

    def test_require_latex_raises_clearly(self):
        with mock.patch.object(render, "find_xelatex", return_value=None):
            with mock.patch.object(render, "find_pdflatex", return_value=None):
                with self.assertRaises(render.LatexNotFoundError) as cm:
                    render.require_latex()
                msg = str(cm.exception)
                self.assertIn("LaTeX required", msg)
                self.assertIn("miktex.org", msg.lower())

    def test_build_job_fails_without_latex(self):
        with tempfile.TemporaryDirectory() as td:
            spec = dict(render.BASE_SPEC) if render.BASE_SPEC else {
                "title": "AI Engineer",
                "objective": " ".join(["word"] * 60),
                "profile": [{"label": "A", "text": "x"}] * 4,
                "skills": [{"category": "Lang", "items": "Python"}] * 7,
                "mondee_bullets": ["b"] * 6,
                "cosmic_bullets": ["c"] * 4,
            }
            cl = {"p1": "a", "p2": "b", "p3": "c", "p4": "d", "addr": "Houston, TX"}
            with mock.patch.object(render, "find_xelatex", return_value=None):
                with mock.patch.object(render, "find_pdflatex", return_value=None):
                    r = render.build_job(
                        td, spec, cl, "Houston, TX", "Acme", "AI Engineer",
                        require_pdf=True,
                    )
            self.assertFalse(r["ok"])
            self.assertFalse(r.get("compiled"))
            self.assertIsNone(r.get("resume_pdf"))
            self.assertTrue(any("LaTeX" in e for e in (r.get("errors") or [])))
            # .tex may still be written, but must not pretend PDF exists
            self.assertFalse(os.path.isfile(os.path.join(td, "Bhanu_Prakash_Bathini.pdf")))

    def test_latex_status_structure(self):
        st = render.latex_status()
        for k in ("xelatex", "pdflatex", "ok", "install_windows", "install_linux"):
            self.assertIn(k, st)
        self.assertIn("miktex.org", st["install_windows"])


class TestDoctor(unittest.TestCase):
    def test_doctor_report_shape(self):
        report = doctor.run_doctor(probe_playwright=False)
        self.assertIn("ok", report)
        self.assertIn("checks", report)
        self.assertIn("failed", report)
        names = [c["check"] for c in report["checks"]]
        self.assertIn("xelatex", names)
        self.assertIn("pdflatex", names)
        self.assertTrue(any(n.startswith("env:LLM_API_KEY") for n in names))
        # Never leak secret values
        blob = str(report)
        self.assertNotIn("sk-", blob)  # best-effort; keys are presence-only

    def test_env_keys_presence_only(self):
        present = doctor._env_keys_present()
        self.assertIsInstance(present, dict)
        for k, v in present.items():
            self.assertIsInstance(v, bool)


if __name__ == "__main__":
    unittest.main()
