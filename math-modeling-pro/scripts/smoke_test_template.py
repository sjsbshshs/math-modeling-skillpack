from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from audit_project import extract_pdf_pages, inspect_pdf


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "latex-template"


def find_pwsh() -> str:
    explicit = Path(r"C:\Program Files\PowerShell\7\pwsh.exe")
    if explicit.is_file():
        return str(explicit)
    found = shutil.which("pwsh")
    if found:
        return found
    raise FileNotFoundError("PowerShell 7 was not found")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="math-modeling-pro-template-") as temporary:
        work = Path(temporary)
        shutil.copytree(TEMPLATE_ROOT / "templates", work, dirs_exist_ok=True)
        shutil.copy2(TEMPLATE_ROOT / "format.cls", work / "format.cls")
        shutil.copytree(TEMPLATE_ROOT / "fonts", work / "fonts")
        process = subprocess.run(
            [
                find_pwsh(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SKILL_ROOT / "scripts" / "compile_paper.ps1"),
                "-PaperDirectory",
                str(work),
                "-MainTex",
                "论文.tex",
            ],
            cwd=work,
            env={**os.environ, "PYTHONUTF8": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if process.returncode != 0:
            raise RuntimeError(
                "Template smoke test failed\n"
                f"STDOUT:\n{process.stdout[-6000:]}\n"
                f"STDERR:\n{process.stderr[-6000:]}"
            )
        pdf_path = work / "论文.pdf"
        pdf_report, pdf_errors, _ = inspect_pdf(pdf_path, "generic", False)
        if pdf_errors:
            raise RuntimeError(f"Template PDF audit failed: {pdf_errors}")
        pages, _ = extract_pdf_pages(pdf_path)
        if not pages:
            raise RuntimeError("no text could be extracted from the compiled PDF")
        if not pages or "摘要" not in pages[0] or "关键词" not in pages[0]:
            raise RuntimeError("Template first page is not a complete abstract page")
        for index, page in enumerate(pages, start=1):
            lines = [line.strip() for line in page.splitlines() if line.strip()]
            if not lines or lines[-1] != str(index):
                raise RuntimeError(f"Template footer page number check failed on page {index}")
        if not pdf_report.get("fonts_embedded"):
            raise RuntimeError("Template PDF contains unembedded fonts")
        print(process.stdout.strip())
        print("Template smoke test: PASS")


if __name__ == "__main__":
    main()
