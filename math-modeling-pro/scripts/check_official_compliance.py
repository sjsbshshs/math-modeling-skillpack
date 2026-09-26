"""Official hard-rule compliance gate (CUMCM format-spec hard clauses).

Catches the failure modes that numeric consistency tooling cannot see. Each
check targets a clause of the official format spec that cost real teams
points in review:

1. citations      clause: references must be cited in the text.
   Parses \\bibitem keys and \\cite-family keys from the tex sources and
   fails on "bibliography exists but zero in-text citations", on uncited
   entries, and on citations without an entry. With a BibTeX/BibLaTeX
   workflow (\\bibliography{...} / \\printbibliography) the entry list lives
   outside the tex, so only "at least one citation" is enforced.

2. appendix_code  clause: the appendix must contain the complete runnable
   source. Compares the code embedded in the tex (lstlisting bodies plus
   \\lstinputlisting targets) against the code shipped in the support
   archive (--support) or source tree (--source-dir). Fails below the
   coverage ratio (default 0.9); intentional excerpts must lower
   --code-coverage explicitly, which keeps the compromise visible.

3. overfull       clause: A4 margins >= 2.5 cm. Scans compile logs for
   "Overfull \\hbox (... pt)" beyond --overfull-tol (default 5 pt); any hit
   fails. vbox overfull is reported as a warning.

4. support_list   clause: the support-material list must appear in the
   appendix. Every file inside the support zip must be named somewhere in
   the tex (escaped-underscore tolerant); every code/doc filename named in
   the tex must exist in the zip. A run-instruction file (复现/README) is
   expected in the archive.

5. first_page     clause: page 1 is the dedicated abstract page. The first
   PDF page must contain 摘要 and 关键词.

Exit codes: 0 = pass, 1 = failures, 2 = configuration error.
Checks without the inputs they need are reported as "excluded", never as
passes.  Run after every recompile; unrun means not passed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from audit_project import extract_pdf_pages

CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citeyear|parencite|textcite|autocite|footcite)"
    r"\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}"
)
BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^{}]+)\}")
EXT_BIB_RE = re.compile(r"\\(?:bibliography|printbibliography|addbibresource)\s*[\[{]")
LST_BODY_RE = re.compile(r"\\begin\{lstlisting\}(?:\[[^\]]*\])?(.*?)\\end\{lstlisting\}", re.S)
LST_INPUT_RE = re.compile(r"\\lstinputlisting(?:\[[^\]]*\])?\{([^{}]+)\}")
TEXTTT_RE = re.compile(r"\\texttt\{([^{}]+)\}")
CODE_EXTS = {".py", ".m", ".jl", ".cpp", ".c", ".java"}
LISTED_EXTS = {".py", ".m", ".md", ".jl", ".cpp", ".c", ".java"}
RUN_DOC_TOKENS = ("复现", "说明", "readme", "运行")


INPUT_RE = re.compile(r"\\input\{([^{}]+)\}")


def read_tex(tex_path: Path) -> str:
    if tex_path.is_file():
        base = tex_path.parent
        seen: set[Path] = set()
        chunks: list[str] = []

        def expand(p: Path) -> None:
            rp = p.resolve()
            if rp in seen or not p.is_file():
                return
            seen.add(rp)
            text = p.read_text(encoding="utf-8", errors="replace")
            for m in INPUT_RE.finditer(text):
                name = m.group(1).strip()
                if not name.lower().endswith(".tex"):
                    name += ".tex"
                expand(p.parent / name)
            chunks.append(text)

        expand(tex_path)
        return "\n".join(chunks), len(seen)
    files = sorted(p for p in tex_path.rglob("*.tex") if p.name != "numbers.tex")
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files), len(files)


def check_citations(tex: str) -> dict:
    bib = set(m.group(1).strip() for m in BIBITEM_RE.finditer(tex))
    cited = set()
    for m in CITE_RE.finditer(tex):
        for key in m.group(1).split(","):
            if key.strip():
                cited.add(key.strip())
    external = bool(EXT_BIB_RE.search(tex))
    issues = []
    if not bib and not cited:
        return {"verdict": "excluded", "note": "论文无参考文献条目，也未使用 \\cite"}
    if bib and not cited:
        issues.append(f"参考文献共 {len(bib)} 条，正文零引用（官方第七条硬性条款）")
    if not external:
        uncited = sorted(bib - cited)
        if uncited:
            issues.append(f"未被正文引用的条目: {uncited}")
        missing = sorted(cited - bib)
        if missing:
            issues.append(f"正文引用但无对应条目: {missing}")
    else:
        if not cited:
            issues.append("使用外部 bib，但正文未找到任何 \\cite")
    return {"verdict": "fail" if issues else "pass", "issues": issues,
            "entries": len(bib), "cited_keys": len(cited), "external_bib": external}


def _embedded_code_lines(tex: str, tex_dir: Path) -> tuple[int, list[str]]:
    lines = sum(1 for chunk in LST_BODY_RE.findall(tex)
                for ln in chunk.splitlines() if ln.strip())
    missing_input = []
    for m in LST_INPUT_RE.finditer(tex):
        target = tex_dir / m.group(1).strip()
        if target.is_file():
            lines += sum(1 for ln in target.read_text(encoding="utf-8", errors="replace").splitlines()
                         if ln.strip())
        else:
            missing_input.append(m.group(1))
    return lines, missing_input


def _code_members(members: list[str]) -> list[str]:
    return [m for m in members if not m.endswith("/") and Path(m).suffix in CODE_EXTS
            and not m.split("/")[-1].startswith("__")]


def check_appendix_code(tex: str, tex_dir: Path, support: Path | None,
                        source_dir: Path | None, coverage_min: float) -> dict:
    embedded, missing_input = _embedded_code_lines(tex, tex_dir)
    source_lines, source_files = 0, []
    if support is not None:
        with zipfile.ZipFile(support) as zf:
            members = zf.namelist()
        code_members = _code_members(members)
        with zipfile.ZipFile(support) as zf:
            for name in code_members:
                data = zf.read(name).decode("utf-8", errors="replace")
                source_lines += sum(1 for ln in data.splitlines() if ln.strip())
        source_files = code_members
    elif source_dir is not None:
        for ext in CODE_EXTS:
            for p in source_dir.rglob(f"*{ext}"):
                if p.name.startswith("__") or "diagnostics" in str(p):
                    continue
                source_lines += sum(1 for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
                                    if ln.strip())
                source_files.append(str(p))
    else:
        return {"verdict": "excluded", "note": "未提供 --support 或 --source-dir，无法计算代码覆盖"}
    if source_lines == 0:
        return {"verdict": "excluded", "note": "支撑材料/源目录中没有代码文件"}
    ratio = embedded / source_lines if source_lines else 0.0
    issues = []
    if missing_input:
        issues.append(f"\\lstinputlisting 指向的文件不存在: {missing_input}")
    if ratio < coverage_min:
        issues.append(
            f"附录代码覆盖不足：嵌入 {embedded} 行 / 支撑源码 {source_lines} 行 = {ratio:.0%} "
            f"< {coverage_min:.0%}（官方第五条要求附录含全部完整可运行源程序）")
    return {"verdict": "fail" if issues else "pass", "issues": issues,
            "embedded_lines": embedded, "source_lines": source_lines,
            "coverage": round(ratio, 3), "code_files": len(source_files)}


def check_overfull(logs: list[Path], tol_pt: float) -> dict:
    if not logs:
        return {"verdict": "excluded", "note": "未提供编译日志 --log"}
    issues, warns = [], []
    for log in logs:
        if not log.is_file():
            issues.append(f"编译日志不存在: {log}")
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt", text):
            if float(m.group(1)) > tol_pt:
                issues.append(f"{log.name}: Overfull \\hbox {m.group(1)}pt > {tol_pt}pt（页边距风险）")
        for m in re.finditer(r"Overfull \\vbox \((\d+(?:\.\d+)?)pt", text):
            if float(m.group(1)) > tol_pt:
                warns.append(f"{log.name}: Overfull \\vbox {m.group(1)}pt")
    return {"verdict": "fail" if issues else "pass", "issues": issues, "warnings": warns}


def _norm_tex_names(tex: str) -> set[str]:
    names = set()
    for m in TEXTTT_RE.finditer(tex):
        names.add(m.group(1).replace(r"\_", "_").strip())
    plain = tex.replace(r"\_", "_")
    for m in re.finditer(r"[\w\-.\u4e00-\u9fff]+\.(?:xlsx|json|md|pdf|csv|txt|zip|py|m|png|jpg|jpeg|svg)\b", plain):
        names.add(m.group(0))
    return names


def check_support_list(tex: str, support: Path | None) -> dict:
    if support is None:
        return {"verdict": "excluded", "note": "未提供 --support"}
    with zipfile.ZipFile(support) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/") and not m.startswith("__")]
    listed = _norm_tex_names(tex)
    issues = []
    unlisted = []
    for m in members:
        base = m.split("/")[-1]
        if base in listed or m in listed:
            continue
        unlisted.append(m)
    if unlisted:
        issues.append(f"支撑包内文件未在论文清单/正文出现: {sorted(unlisted)}")
    for name in sorted(listed):
        base = name.split("/")[-1]
        if Path(base).suffix in LISTED_EXTS and "/" not in name:
            if not any(m.split("/")[-1] == base for m in members):
                issues.append(f"论文清单中的文件不在支撑包内: {base}")
    has_run_doc = any(any(t in m.lower() for t in RUN_DOC_TOKENS) for m in members)
    if not has_run_doc:
        issues.append("支撑包内未找到运行说明（文件名含 复现/说明/README）")
    return {"verdict": "fail" if issues else "pass", "issues": issues,
            "zip_files": len(members), "listed_names": len(listed)}


def check_first_page(pages: list[str]) -> dict:
    if not pages:
        return {"verdict": "excluded", "note": "无法提取 PDF 文本"}
    first = pages[0]
    issues = []
    if "摘要" not in first:
        issues.append("PDF 首页未找到“摘要”（第一条：首页为摘要专用页）")
    if "关键词" not in first.replace(" ", "").replace("\u3000", ""):
        issues.append("PDF 首页未找到“关键词”")
    return {"verdict": "fail" if issues else "pass", "issues": issues}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--tex", type=Path, required=True, help="tex 文件或目录")
    parser.add_argument("--support", type=Path, help="支撑材料 zip")
    parser.add_argument("--source-dir", type=Path, help="代码源目录（无 zip 时计算覆盖用）")
    parser.add_argument("--log", type=Path, action="append", default=[], help="编译日志，可多次")
    parser.add_argument("--overfull-tol", type=float, default=5.0)
    parser.add_argument("--code-coverage", type=float, default=0.9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not args.paper.is_file():
        print(f"paper not found: {args.paper}", file=sys.stderr)
        sys.exit(2)
    tex, n_tex = read_tex(args.tex)
    if not tex.strip():
        print(f"no tex content under: {args.tex}", file=sys.stderr)
        sys.exit(2)
    try:
        pages, _ = extract_pdf_pages(args.paper)
    except Exception as exc:  # noqa: BLE001
        print(f"PDF text extraction failed: {exc}", file=sys.stderr)
        sys.exit(2)

    report = {
        "citations": check_citations(tex),
        "appendix_code": check_appendix_code(tex, args.tex if args.tex.is_dir() else args.tex.parent,
                                              args.support, args.source_dir, args.code_coverage),
        "overfull": check_overfull(args.log, args.overfull_tol),
        "support_list": check_support_list(tex, args.support),
        "first_page": check_first_page(list(pages)),
    }
    failures = [k for k, v in report.items() if v["verdict"] == "fail"]
    excluded = [k for k, v in report.items() if v["verdict"] == "excluded"]
    passed = not failures
    out = {"passed": passed, "failures": failures, "excluded": excluded, "checks": report,
           "tex_files": n_tex}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
