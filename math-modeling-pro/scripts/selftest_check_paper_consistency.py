# -*- coding: utf-8 -*-
"""Self-test for check_paper_consistency.py.

Builds a minimal fixture project in a temp directory (summary + result JSON +
fake PDF text) and asserts the checker's behavior on:
  1. numeric claims (pass / wrong-value fail)
  2. string claims (normalized match pass / mismatch fail)
  3. string absent from PDF (layer-3 fail)
  4. old-format numeric-only summaries still parse (backward compat)

Run:  python selftest_check_paper_consistency.py
Exit: 0 = all cases behave as expected.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_paper_consistency.py"

SUMMARY = {
    "key_results": {
        "best_profit": 51.9,
        "best_bits": "11111111 111 111 0 1",
    },
    "paper_claims": [
        {"key": "num_ok", "value": 51.9, "source": "results/r.json#best_profit", "decimals": 2},
        {"key": "num_bad", "value": 7.77, "source": "results/r.json#best_profit", "decimals": 2},
        {"key": "bits_ok", "value": "11111111 111 111 0 1", "source": "results/r.json#best_bits", "decimals": 0},
        {"key": "bits_bad", "value": "11010101 111 111 0 1", "source": "results/r.json#best_bits", "decimals": 0},
    ],
    "cross_checks": [
        {"a": "key_results.best_profit", "b": 51.9, "tol": 1e-9},
    ],
}

# Fake PDF text: contains 51.9 and the TRUE bit string but not the wrong one.
PDF_TEXT = ("最优单件平均利润为 51.90 元/件，最优决策位串为 11111111 111 111 0 1。")


def build_fixture(root: Path) -> None:
    (root / "results").mkdir(parents=True)
    (root / "results" / "r.json").write_text(
        json.dumps({"best_profit": 51.9, "best_bits": "11111111 111 111 0 1"},
                   ensure_ascii=False), encoding="utf-8")
    (root / "summary.json").write_text(
        json.dumps(SUMMARY, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / "fake.pdf").write_text("%PDF-1.4 fake " + PDF_TEXT, encoding="utf-8")


def run_checker(project: Path, paper: Path | None) -> dict:
    cmd = [sys.executable, str(CHECKER), "--project", str(project),
           "--summary", "summary.json", "--output", str(project / "report.json")]
    if paper is not None:
        cmd += ["--paper", str(paper)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    report = json.loads((project / "report.json").read_text(encoding="utf-8"))
    report["_exit"] = proc.returncode
    return report


def status_of(report: dict, layer: str, key: str) -> str:
    for entry in report["layers"][layer]["detail"]:
        if entry["key"] == key:
            return entry["status"]
    return "<missing>"


def write_fake_pdf(path: Path, text: str) -> bool:
    """Create a real one-page PDF containing `text` so pdftotext/pypdf can
    extract it. Returns False when no PDF writer is available."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return False
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 200), text, fontsize=11)
    doc.save(str(path))
    doc.close()
    return True


def main() -> None:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        build_fixture(root)
        pdf_ok = write_fake_pdf(root / "fake.pdf",
                                "best profit 51.90 yuan; best bits 11111111 111 111 0 1")
        rep = run_checker(root, root / "fake.pdf" if pdf_ok else None)
        cases = [
            ("numeric ok passes layer2", status_of(rep, "claims_vs_results", "num_ok") == "pass"),
            ("numeric bad fails layer2", status_of(rep, "claims_vs_results", "num_bad") == "fail"),
            ("string ok passes layer2 (normalized)", status_of(rep, "claims_vs_results", "bits_ok") == "pass"),
            ("string mismatch fails layer2", status_of(rep, "claims_vs_results", "bits_bad") == "fail"),
        ]
        if pdf_ok:
            cases += [
                ("string ok found in fake PDF", status_of(rep, "claims_vs_pdf", "bits_ok") == "pass"),
                ("string mismatch absent from PDF fails layer3",
                 status_of(rep, "claims_vs_pdf", "bits_bad") == "fail"),
            ]
        else:
            print("  [SKIP] PDF writer unavailable; layer-3 cases skipped")
        cases.append(("overall failed (bad claims present)", rep["passed"] is False))

        # ---- 向后兼容：仅数值的旧格式摘要 ----
        old = dict(SUMMARY)
        old["paper_claims"] = [c for c in SUMMARY["paper_claims"] if c["key"] == "num_ok"]
        root2 = Path(tmp) / "proj_old"
        root2.mkdir()
        (root2 / "results").mkdir()
        (root2 / "results" / "r.json").write_text(
            json.dumps({"best_profit": 51.9}, ensure_ascii=False), encoding="utf-8")
        (root2 / "summary.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        legacy_pdf = write_fake_pdf(root2 / "fake.pdf", "best profit 51.90 yuan")
        rep2 = run_checker(root2, root2 / "fake.pdf" if legacy_pdf else None)
        cases.append(("legacy numeric-only summary still parses", "_exit" in rep2))
        cases.append(("legacy summary overall passes", rep2["passed"] is True))

        for name, ok in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
            if not ok:
                failures.append(name)

    if failures:
        print(f"selftest FAILED: {failures}")
        raise SystemExit(1)
    print("selftest OK: all cases behave as expected")


if __name__ == "__main__":
    main()
