"""Selftest for check_official_compliance.py.

Builds two synthetic projects in a temp dir:
  GOOD  — full citations, complete code in appendix, clean log, consistent
          support zip, abstract first page  -> expect passed=True
  BAD   — zero citations, code excerpt, overfull log, extra zip file not in
          tex, abstract missing 关键词                    -> expect passed=False
          with all five checks failing.

Run: python selftest_official_compliance.py
Exit 0 if the gate behaves as expected, 1 otherwise.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_official_compliance.py"

CODE_A = "\n".join(f"line_{i} = {i}  # keep" for i in range(1, 21))  # 20 non-empty lines
CODE_B = "\n".join(f"x_{i} = {i}" for i in range(1, 11))


def make_project(root: Path, *, good: bool) -> dict:
    (root / "src").mkdir(parents=True)
    (root / "src" / "model.py").write_text(CODE_A + "\n" + CODE_B + "\n", encoding="utf-8")
    cite_keys = "\\cite{kuang2012}\\cite{winston2004}" if good else ""
    bib = ("\\begin{thebibliography}{2}\n"
           "  \\bibitem{kuang2012} 运筹学教材. 2012.\n"
           "  \\bibitem{winston2004} Winston W L. Operations Research. 2004.\n"
           "\\end{thebibliography}\n")
    first_page = ("\\title{测试}\\begin{document}\n"
                  "摘要 本文做了测试。\n"
                  + ("关键词 测试\n" if good else "关键字 测试\n"))
    full_code = CODE_A + "\n" + CODE_B
    if good:
        code_listing = "\\begin{lstlisting}\n" + full_code + "\n\\end{lstlisting}\n"
    else:
        code_listing = "\\begin{lstlisting}\n" + "\n".join(CODE_A.splitlines()[:3]) + "\n\\end{lstlisting}\n"
    support_note = "\\texttt{model.py}\\texttt{结果.json}\\texttt{复现说明.md}\n" if good else \
                   "\\texttt{model.py}\n"
    tex = (first_page
           + "正文引用一处：" + cite_keys + "。\n"
           + code_listing
           + support_note
           + bib
           + "\\end{document}\n")
    (root / "main.tex").write_text(tex, encoding="utf-8")
    (root / "build.log").write_text("" if good else
                                    "Overfull \\hbox (55.84pt too wide) in paragraph\n",
                                    encoding="utf-8")
    zip_path = root / "support.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("code/model.py", CODE_A + "\n" + CODE_B + "\n")
        zf.writestr("results/结果.json", "{}")
        if good:
            zf.writestr("复现说明.md", "运行 model.py")
        else:
            zf.writestr("code/audit_extra.py", "print(1)\n")  # 未在 tex 出现
    return {"paper": None, "tex": root / "main.tex", "support": zip_path,
            "log": root / "build.log"}


def make_pdf(root: Path, *, good: bool) -> Path:
    """最小测试 PDF：嵌入 CJK 字体保证文本可提取。"""
    pdf = root / "paper.pdf"
    font = HERE.parent / "latex-template" / "fonts" / "fonts" / "SourceHanSerifCN-Regular.otf"
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        text = "摘要 本文做了测试。关键词 测试" if good else "摘要 本文做了测试。关键字 测试"
        page.insert_text((72, 100), text, fontname="cjk", fontfile=str(font))
        doc.save(str(pdf))
        doc.close()
    except Exception:
        return None
    return pdf


def run(args: list[str]) -> dict:
    proc = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), *args],
                          capture_output=True, text=True, encoding="utf-8")
    try:
        return {"code": proc.returncode, "report": json.loads(proc.stdout)}
    except json.JSONDecodeError:
        return {"code": proc.returncode, "report": {"stdout": proc.stdout, "stderr": proc.stderr}}


def main() -> None:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # GOOD
        good_dir = root / "good"
        good_dir.mkdir()
        info = make_project(good_dir, good=True)
        pdf = make_pdf(good_dir, good=True)
        if pdf is None:
            print("SKIP: no pdf writer available")
            return
        good = run(["--paper", str(pdf), "--tex", str(info["tex"]),
                    "--support", str(info["support"]), "--log", str(info["log"])])
        if good["code"] != 0 or not good["report"].get("passed"):
            failures.append(f"GOOD fixture should pass: {json.dumps(good['report'], ensure_ascii=False)}")
        # BAD
        bad_dir = root / "bad"
        bad_dir.mkdir()
        info = make_project(bad_dir, good=False)
        pdf = make_pdf(bad_dir, good=False)
        bad = run(["--paper", str(pdf), "--tex", str(info["tex"]),
                   "--support", str(info["support"]), "--log", str(info["log"])])
        rep = bad["report"]
        if bad["code"] == 0 or rep.get("passed"):
            failures.append("BAD fixture should fail")
        expected_fail = {"citations", "appendix_code", "overfull", "support_list", "first_page"}
        got_fail = set(rep.get("failures", []))
        if got_fail != expected_fail:
            failures.append(f"BAD failures mismatch: got {sorted(got_fail)}")
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("selftest OK: GOOD passes, BAD fails on all five checks")


if __name__ == "__main__":
    main()
