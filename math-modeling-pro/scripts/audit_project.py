from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


LIMIT_20_MB = 20 * 1024 * 1024
IDENTITY_TERMS = ("参赛学校", "参赛队号", "指导教师", "队员姓名", "赛区评阅编号")
LOG_PATTERNS = re.compile(
    r"Overfull \\[hv]box|Underfull \\[hv]box|Float too large|"
    r"LaTeX Font Warning|There were undefined references|"
    r"Citation .+ undefined|Reference .+ undefined|Rerun to get cross-references right"
)


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found and Path(found).suffix.lower() not in {".cmd", ".bat"}:
        return found
    if os.name == "nt":
        for drive in ("C:", "D:"):
            root = Path(drive + "\\texlive")
            if not root.is_dir():
                continue
            for version in sorted(root.iterdir(), reverse=True):
                candidate = version / "bin" / "windows" / f"{name}.exe"
                if candidate.is_file():
                    return str(candidate)
    return None


def run_tool(executable: str, *arguments: str) -> str:
    process = subprocess.run(
        [executable, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        raise RuntimeError(f"{Path(executable).name} failed: {process.stderr.strip()}")
    return process.stdout


def extract_pdf_pages(path: Path) -> tuple[list[str], str]:
    """Return per-page text plus the full text, choosing the richer backend.

    Some poppler builds (notably MinGW's pdftotext) drop every CJK glyph from
    CID fonts even when ToUnicode maps exist, which would silently disable all
    CJK-dependent checks. pypdf reads the embedded ToUnicode maps directly, so
    run both and keep whichever extracts more non-whitespace content. pypdf
    pages are kept as a per-page list: a stray form feed inside an extracted
    page must not become a phantom page boundary.
    """
    poppler_text = ""
    pdftotext = find_tool("pdftotext")
    if pdftotext is not None:
        try:
            poppler_text = run_tool(pdftotext, "-layout", str(path), "-")
        except RuntimeError:
            poppler_text = ""
    pypdf_pages: list[str] | None = None
    try:
        import pypdf

        reader = pypdf.PdfReader(str(path))
        pypdf_pages = [(page.extract_text() or "").replace("\f", "\n")
                       for page in reader.pages]
        pypdf_text = "\f".join(pypdf_pages)
    except Exception:
        pypdf_pages, pypdf_text = None, ""
    if pypdf_pages is not None and len(pypdf_text.split()) > len(poppler_text.split()):
        return pypdf_pages, pypdf_text
    pages = poppler_text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages, poppler_text


def workbook_identity(archive: zipfile.ZipFile, member: str) -> dict[str, str]:
    with zipfile.ZipFile(archive.open(member)) as workbook:
        try:
            raw = workbook.read("docProps/core.xml")
        except KeyError:
            return {}
    root = ElementTree.fromstring(raw)
    values: dict[str, str] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in {"creator", "lastModifiedBy", "title", "subject", "description", "keywords"}:
            text = (element.text or "").strip()
            if text:
                values[name] = text
    return values


def inspect_pdf(path: Path, competition: str, ai_excluded: bool) -> tuple[dict[str, object], list[str], list[str]]:
    errors: list[str] = []
    exclusions: list[str] = []
    tools = {name: find_tool(name) for name in ("pdfinfo", "pdftotext", "pdffonts")}
    required = [name for name in ("pdfinfo", "pdffonts") if tools[name] is None]
    if required:
        errors.append(f"PDF checks unavailable; missing tools: {required}")
        return {"tools": tools}, errors, exclusions
    if tools["pdftotext"] is None:
        try:
            import pypdf  # noqa: F401
        except ImportError:
            errors.append("PDF checks unavailable; missing tools: ['pdftotext'] and pypdf")
            return {"tools": tools}, errors, exclusions

    info = run_tool(tools["pdfinfo"], str(path))  # type: ignore[arg-type]
    pages_match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    page_size_match = re.search(r"^Page size:\s+(.+)$", info, re.MULTILINE)
    pages = int(pages_match.group(1)) if pages_match else 0
    if pages <= 0:
        errors.append("PDF page count could not be read")

    page_text, text = extract_pdf_pages(path)
    footer_errors: list[int] = []
    for index, content in enumerate(page_text, start=1):
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines or lines[-1] != str(index):
            footer_errors.append(index)

    identity_hits = [term for term in IDENTITY_TERMS if term in text]
    if identity_hits:
        errors.append(f"PDF contains possible identity fields: {identity_hits}")

    fonts = run_tool(tools["pdffonts"], str(path))  # type: ignore[arg-type]
    rows = re.findall(r"\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", fonts, re.MULTILINE)
    fonts_embedded = bool(rows) and all(row[0] == "yes" for row in rows)
    if not fonts_embedded:
        errors.append("PDF contains an unembedded font or font table could not be parsed")

    references_page = None
    appendix_page = None
    for index, content in enumerate(page_text, start=1):
        if references_page is None and ("参考文献" in content or "References" in content):
            references_page = index
        if appendix_page is None and ("附录" in content or "Appendix" in content):
            appendix_page = index

    if competition == "cumcm":
        first = page_text[0] if page_text else ""
        if "摘要" not in first or "关键词" not in first:
            errors.append("CUMCM electronic paper first page is not a complete abstract page")
        normalized_lines = {line.strip() for line in text.splitlines() if line.strip()}
        if normalized_lines.intersection({"目录", "Contents", "Table of Contents"}):
            errors.append("CUMCM paper appears to contain a table of contents")
        if footer_errors:
            errors.append(f"continuous footer page numbers were not recognized on pages: {footer_errors}")
        if references_page is None:
            errors.append("references section was not recognized")
        else:
            body_pages = references_page - 2
            if body_pages > 30:
                errors.append(f"CUMCM main body has {body_pages} pages, exceeding 30")
        has_ai_statement = bool(re.search(r"AI\s*工\s*具\s*使\s*用\s*声明|人工智能\s*工具\s*使用\s*声明", text))
        if not has_ai_statement:
            if ai_excluded:
                exclusions.append("AI tool declaration was explicitly excluded and was not validated")
            else:
                errors.append("2026 CUMCM AI tool declaration was not found")
    else:
        body_pages = None

    return {
        "pages": pages,
        "page_size": page_size_match.group(1).strip() if page_size_match else None,
        "bytes": path.stat().st_size,
        "under_20_mb": path.stat().st_size <= LIMIT_20_MB,
        "footer_pages_continuous": not footer_errors,
        "identity_hits": identity_hits,
        "fonts_embedded": fonts_embedded,
        "references_page": references_page,
        "appendix_page": appendix_page,
        "body_pages": body_pages,
        "md5": digest(path, "md5"),
        "sha256": digest(path, "sha256"),
        "tools": tools,
    }, errors, exclusions


def inspect_support(path: Path) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    identity_metadata: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        members = archive.namelist()
        for member in members:
            if any(term in member for term in IDENTITY_TERMS):
                errors.append(f"support member name may reveal identity: {member}")
            if member.lower().endswith(".xlsx"):
                metadata = workbook_identity(archive, member)
                if metadata:
                    identity_metadata[member] = metadata
    if bad_member:
        errors.append(f"support archive CRC failed: {bad_member}")
    if identity_metadata:
        errors.append(f"Excel metadata is not anonymous: {sorted(identity_metadata)}")
    if path.stat().st_size > LIMIT_20_MB:
        errors.append("support archive exceeds 20 MB")
    return {
        "bytes": path.stat().st_size,
        "under_20_mb": path.stat().st_size <= LIMIT_20_MB,
        "member_count": len(members),
        "crc_ok": bad_member is None,
        "excel_metadata": identity_metadata,
        "md5": digest(path, "md5"),
        "sha256": digest(path, "sha256"),
    }, errors


ABS_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\|/home/|/Users/|/mnt/)")
SCAN_SUFFIXES = {".py", ".md", ".txt", ".tex", ".json", ".csv", ".r", ".m"}


def scan_support_paths(path: Path) -> list[dict[str, object]]:
    """Flag workspace-absolute path patterns inside text members of the support
    archive. Such paths are implicit machine premises (they break relocation and,
    worse, can silently resolve imports against the original workspace during an
    isolation re-run). Default severity is warning; --strict-paths promotes to error."""
    findings: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if Path(member).suffix.lower() not in SCAN_SUFFIXES:
                continue
            try:
                text = archive.read(member).decode("utf-8", errors="replace")
            except OSError:
                continue
            hits = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                if ABS_PATH_PATTERN.search(line):
                    hits.append(line_no)
            if hits:
                findings.append({"member": member, "lines": hits[:8], "total": len(hits)})
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit observable mathematical-modeling submission invariants")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--competition", choices=("cumcm", "mcm", "generic"), default="cumcm")
    parser.add_argument("--ai-excluded", action="store_true")
    parser.add_argument("--strict-paths", action="store_true",
                        help="treat workspace-absolute paths inside the support archive as failures")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project = args.project.resolve()
    paper = args.paper if args.paper.is_absolute() else project / args.paper
    support = None if args.support is None else (args.support if args.support.is_absolute() else project / args.support)
    log = None if args.log is None else (args.log if args.log.is_absolute() else project / args.log)
    errors: list[str] = []
    exclusions: list[str] = []

    if not paper.is_file():
        errors.append(f"paper not found: {paper}")
        pdf_report: dict[str, object] = {}
    else:
        pdf_report, pdf_errors, pdf_exclusions = inspect_pdf(paper, args.competition, args.ai_excluded)
        errors.extend(pdf_errors)
        exclusions.extend(pdf_exclusions)
        if paper.stat().st_size > LIMIT_20_MB:
            errors.append("paper exceeds 20 MB")

    support_report: dict[str, object] | None = None
    path_findings: list[dict[str, object]] = []
    if support is not None:
        if not support.is_file():
            errors.append(f"support archive not found: {support}")
        else:
            try:
                support_report, support_errors = inspect_support(support)
                errors.extend(support_errors)
            except zipfile.BadZipFile:
                errors.append(f"support archive is not a valid ZIP: {support}")
            if support_report is not None:
                try:
                    path_findings = scan_support_paths(support)
                except zipfile.BadZipFile:
                    path_findings = []
                support_report["path_scan"] = {
                    "members_flagged": len(path_findings),
                    "detail": path_findings[:20],
                }
                if path_findings:
                    message = (
                        f"support archive contains workspace-absolute paths in "
                        f"{len(path_findings)} member(s); disclose them in 复现说明 or relocate"
                    )
                    if args.strict_paths:
                        errors.append(message)
                    else:
                        exclusions.append(message + " (warning; use --strict-paths to enforce)")

    log_report: dict[str, object] | None = None
    if log is not None:
        if not log.is_file():
            errors.append(f"LaTeX log not found: {log}")
        else:
            matches = sorted(set(LOG_PATTERNS.findall(log.read_text(encoding="utf-8", errors="replace"))))
            log_report = {"target_warning_tokens": matches}
            if matches:
                errors.append(f"LaTeX log contains target warnings: {matches}")

    report = {
        "passed": not errors,
        "scope": "observable submission checks; model validity and current official rules require project-level review",
        "competition": args.competition,
        "pdf": pdf_report,
        "support": support_report,
        "latex_log": log_report,
        "exclusions": exclusions,
        "errors": errors,
    }
    output = args.output or project / "submission_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
