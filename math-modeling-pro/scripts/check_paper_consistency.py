"""Paper-results consistency checker (three machine-checked layers).

Layer 1  summary self-consistency: non-finite scan + declared cross_checks
         (each sub-problem must register at least one problem-semantic invariant).
Layer 2  paper_claims vs result files: every claimed number or string (e.g. a
         decision bit string) must be reproducible from its declared source
         (xlsx cell/sheet scan, csv, or JSON dot path).
Layer 3  paper_claims vs compiled PDF: every claimed value must appear in the
         PDF text (numeric: 2-6 decimal variants; string: comma/space/dash
         normalized containment).

Also provides --lint-xref: source-code comments citing "论文 X.Y 节" are checked
against the actual \\section/\\subsection numbering of the main tex file.

Exit codes: 0 = pass, 1 = failures (any layer), 2 = configuration error.
Skipped checks are reported as exclusions, never as passes.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from audit_project import extract_pdf_pages

DECIMALS = (2, 3, 4, 5, 6)
XREF_PATTERN = re.compile(r"(?:论文|正文)\s*(\d+(?:\.\d+)*)\s*节")


# ---------------------------------------------------------------- basics

def iter_numbers(node, prefix=""):
    """Yield (dotted_path, number) for every finite numeric leaf."""
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield prefix, node
    elif isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from iter_numbers(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_numbers(value, f"{prefix}[{index}]")


def lookup(doc, dotted):
    node = doc
    for part in str(dotted).split("."):
        match = re.fullmatch(r"(.+)\[(\d+)\]", part)
        if match:
            node = node[match.group(1)]
            node = node[int(match.group(2))]
        else:
            node = node[part]
    return node


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def approx_equal(left, right, tol):
    if is_number(left) and is_number(right):
        return abs(float(left) - float(right)) <= tol
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            is_number(a) and is_number(b) and abs(float(a) - float(b)) <= tol
            for a, b in zip(left, right)
        )
    return False


# ------------------------------------------------------- PDF matching

def pdf_variants(value) -> set[str]:
    v = float(value)
    variants = {repr(v), f"{v:g}"}
    if v == int(v) and abs(v) < 1e15:
        variants.add(str(int(v)))
    for k in DECIMALS:
        s = f"{v:.{k}f}"
        variants.add(s)
        if "." in s:
            variants.add(s.rstrip("0").rstrip("."))
    return {s.replace("-", "-") for s in variants}


def normalize_pdf_text(text: str) -> str:
    for dash in ("\u2212", "\u2013", "\u2014", "\u2010"):
        text = text.replace(dash, "-")
    return re.sub(r"[,\s]", "", text)


def number_in_text(value, normalized: str) -> bool:
    for variant in pdf_variants(value):
        if variant in normalized:
            return True
    return False


# ------------------------------------------------------- result sources

def read_source_values(spec: str, base: Path) -> tuple[list[float], str | None]:
    """Return (numbers, error). spec: file[#sheet[!Cell]] or file#json.dot.path"""
    path_part, _, anchor = spec.partition("#")
    path = (base / path_part) if not Path(path_part).is_absolute() else Path(path_part)
    if not path.is_file():
        return [], f"source file not found: {path}"
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx(path, anchor)
    if suffix == ".csv":
        return read_csv(path), None
    if suffix == ".json":
        return read_json_source(path, anchor)
    return [], f"unsupported source type: {path.name}"


def read_xlsx(path: Path, anchor: str) -> tuple[list[float], str | None]:
    try:
        from openpyxl import load_workbook
        from openpyxl.utils import column_index_from_string
    except ImportError:
        return [], "openpyxl is not installed; cannot read xlsx sources"
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as error:  # noqa: BLE001
        return [], f"cannot open {path.name}: {error}"
    sheet_name, _, cell = anchor.partition("!")
    try:
        sheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]
    except KeyError:
        return [], f"sheet not found in {path.name}: {sheet_name!r}"
    numbers: list[float] = []
    if cell:
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", cell.strip())
        if not match:
            return [], f"bad cell reference: {cell!r}"
        col = column_index_from_string(match.group(1).upper())
        row = int(match.group(2))
        value = sheet.cell(row=row, column=col).value
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                return [], f"cell {sheet_name}!{cell} does not hold a number"
        if is_number(value):
            numbers.append(float(value))
    else:
        for row_values in sheet.iter_rows(values_only=True):
            for value in row_values:
                if isinstance(value, str):
                    try:
                        value = float(value)
                    except ValueError:
                        continue
                if is_number(value):
                    numbers.append(float(value))
    workbook.close()
    return numbers, None


def read_csv(path: Path) -> list[float]:
    numbers: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for token in line.split(","):
            token = token.strip().strip('"')
            try:
                numbers.append(float(token))
            except ValueError:
                continue
    return numbers


def read_json_source(path: Path, dotted: str) -> tuple[list, str | None]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        return [], f"cannot parse {path.name}: {error}"
    if not dotted:
        return [v for _, v in iter_numbers(doc)], None
    try:
        node = lookup(doc, dotted)
    except (KeyError, IndexError, TypeError):
        return [], f"json path not found in {path.name}: {dotted}"
    if is_number(node):
        return [float(node)], None
    if isinstance(node, str):
        return [node], None
    if isinstance(node, list):
        return [float(v) for v in node if is_number(v)], None
    return [], f"json path is not a number or string in {path.name}: {dotted}"


def claim_matches(claimed, found: list, decimals: int) -> bool:
    if isinstance(claimed, str):
        target = normalize_pdf_text(claimed)
        return any(isinstance(f, str) and normalize_pdf_text(f) == target for f in found)
    tol = 0.51 * 10 ** (-decimals)
    if isinstance(claimed, list):
        return all(any(abs(float(c) - f) <= tol for f in found) for c in claimed)
    if is_number(claimed):
        return any(abs(float(claimed) - f) <= tol for f in found)
    return False


# ------------------------------------------------------- xref lint

def tex_sections(main_tex: Path) -> set[str]:
    """Collect section numbers from the main tex, following \\input recursively."""
    base = main_tex.parent
    seen: set[Path] = set()
    pieces: list[str] = []

    def gather(path: Path) -> None:
        if path in seen or not path.is_file():
            return
        seen.add(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        pieces.append(text)
        for name in re.findall(r"\\(?:input|include)\{([^}]+)\}", text):
            candidate = base / name
            if not candidate.suffix:
                candidate = candidate.with_suffix(".tex")
            gather(candidate)

    gather(main_tex)
    full = "\n".join(pieces)
    valid: set[str] = set()
    section_no = 0
    subsection_no = 0
    in_appendix = False
    for command, starred, content in re.findall(
        r"\\(section|subsection)(\*?)\{([^}]*)\}", full
    ):
        if "\\appendix" in full[: full.find(content)] and not in_appendix:
            if re.search(r"\\appendix\b", full[: full.find(content) + len(content)]):
                in_appendix = True
        if in_appendix:
            continue
        if command == "section":
            if not starred:
                section_no += 1
                subsection_no = 0
                valid.add(str(section_no))
        elif not starred:
            subsection_no += 1
            valid.add(f"{section_no}.{subsection_no}")
    return valid


def lint_xref(project: Path, main_tex: Path) -> list[str]:
    valid = tex_sections(main_tex)
    warnings: list[str] = []
    skip_dirs = {".git", "node_modules", "__pycache__", "评审_render", "_render"}
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".m"}:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in XREF_PATTERN.finditer(text):
            if valid and match.group(1) not in valid:
                line_no = text[: match.start()].count("\n") + 1
                warnings.append(
                    f"{path.relative_to(project)}:{line_no} cites 论文 {match.group(1)} 节, "
                    f"which does not exist in {main_tex.name}"
                )
    return warnings


# ------------------------------------------------------- main checks

def run_checks(args) -> tuple[dict, list[str], list[str]]:
    errors: list[str] = []
    exclusions: list[str] = []
    report: dict = {"layers": {}}

    summary_path = args.summary if args.summary.is_absolute() else args.project / args.summary
    if not summary_path.is_file():
        raise SystemExit(f"summary file not found: {summary_path}")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"summary is not valid JSON: {error}")
    base = args.project.resolve()
    report["summary"] = str(summary_path)

    numbers = list(iter_numbers(summary))
    non_finite = [p for p, v in numbers if not math.isfinite(v)]
    report["layers"]["non_finite"] = {"count": len(numbers), "violations": non_finite}
    if non_finite:
        errors.append(f"summary contains non-finite values: {non_finite[:5]}")

    claims = summary.get("paper_claims")
    cross_checks = summary.get("cross_checks")
    mode = "claims" if claims is not None or cross_checks is not None else "scan"
    report["mode"] = mode
    if mode == "scan" and args.strict:
        errors.append(
            "--strict requires the summary to declare paper_claims and cross_checks; "
            "unregistered paper numbers cannot pass a strict gate"
        )

    # Layer 1: cross_checks
    cross_report = []
    for check in cross_checks or []:
        try:
            left = lookup(summary, check["a"]) if not is_number(check["a"]) else check["a"]
            right = lookup(summary, check["b"]) if not is_number(check["b"]) else check["b"]
        except (KeyError, IndexError, TypeError) as error:
            cross_report.append({"check": check, "status": "error", "detail": str(error)})
            errors.append(f"cross_check path missing: {error}")
            continue
        tol = float(check.get("tol", 1e-9))
        ok = approx_equal(left, right, tol)
        cross_report.append({"check": check, "status": "pass" if ok else "fail"})
        if not ok:
            errors.append(f"cross_check failed: {check} (got {left} vs {right})")
    report["layers"]["cross_checks"] = {
        "total": len(cross_report),
        "failed": sum(1 for c in cross_report if c["status"] == "fail"),
        "detail": cross_report,
    }
    if mode == "claims" and not cross_checks:
        errors.append(
            "paper_claims present but cross_checks is empty; register at least one "
            "problem-semantic invariant per sub-problem (see references/paper-consistency.md)"
        )

    # Layer 2: claims vs result files
    claim_report = []
    if claims is not None:
        for claim in claims:
            key = claim.get("key", "<unnamed>")
            decimals = int(claim.get("decimals", 6))
            source = claim.get("source")
            entry: dict = {"key": key, "source": source}
            if not source:
                entry["status"] = "error"
                errors.append(f"claim {key} has no source")
            else:
                found, error = read_source_values(source, base)
                if error:
                    entry["status"] = "skipped"
                    entry["detail"] = error
                    exclusions.append(f"claim {key}: {error}")
                else:
                    ok = claim_matches(claim.get("value"), found, decimals)
                    entry["status"] = "pass" if ok else "fail"
                    if not ok:
                        errors.append(
                            f"claim {key}={claim.get('value')} not reproduced from {source} "
                            f"at {decimals} decimals"
                        )
            claim_report.append(entry)
        report["layers"]["claims_vs_results"] = {
            "total": len(claim_report),
            "failed": sum(1 for c in claim_report if c["status"] == "fail"),
            "skipped": sum(1 for c in claim_report if c["status"] == "skipped"),
            "detail": claim_report,
        }

    # Layer 3: claims vs PDF
    if args.paper is not None:
        paper = args.paper if args.paper.is_absolute() else args.project / args.paper
        if not paper.is_file():
            exclusions.append(f"paper not found, layer 3 skipped: {paper}")
        else:
            try:
                _, text = extract_pdf_pages(paper)
            except Exception as error:  # noqa: BLE001
                exclusions.append(f"PDF text extraction failed: {error}")
                text = ""
            normalized = normalize_pdf_text(text)
            if claims is not None:
                pdf_report = []
                for claim in claims:
                    key = claim.get("key", "<unnamed>")
                    value = claim.get("value")
                    components = value if isinstance(value, list) else [value]
                    missing = []
                    for c in components:
                        if is_number(c):
                            if not number_in_text(c, normalized):
                                missing.append(c)
                        elif isinstance(c, str):
                            if normalize_pdf_text(c) not in normalized:
                                missing.append(c)
                    status = "pass" if not missing else "fail"
                    pdf_report.append({"key": key, "status": status, "missing": missing})
                    if missing:
                        errors.append(f"claim {key} not found in PDF: {missing}")
                report["layers"]["claims_vs_pdf"] = {
                    "total": len(pdf_report),
                    "failed": sum(1 for c in pdf_report if c["status"] == "fail"),
                    "detail": pdf_report,
                }
            else:
                sample = [p for p, _ in numbers[:200]]
                missing = [p for p, v in numbers if not number_in_text(v, normalized)]
                report["layers"]["scan_pdf_presence"] = {
                    "checked": len(numbers),
                    "missing_in_pdf": len(missing),
                    "sample_missing": missing[:10],
                }
                if args.strict and missing:
                    errors.append(
                        f"{len(missing)} summary numbers absent from PDF (scan mode, strict)"
                    )

    if args.lint_xref:
        if args.main_tex is None:
            exclusions.append("--lint-xref needs --main-tex")
        else:
            main_tex = args.main_tex if args.main_tex.is_absolute() else args.project / args.main_tex
            if not main_tex.is_file():
                exclusions.append(f"main tex not found: {main_tex}")
            else:
                warnings_found = lint_xref(base, main_tex)
                report["layers"]["xref_lint"] = {"warnings": warnings_found}
                if warnings_found:
                    if args.strict:
                        errors.append(f"dangling paper-section citations: {warnings_found}")
                    else:
                        print("[warn] dangling paper-section citations:", file=sys.stderr)
                        for w in warnings_found:
                            print("  " + w, file=sys.stderr)

    return report, errors, exclusions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, required=True,
                        help="results summary JSON containing paper_claims/cross_checks")
    parser.add_argument("--paper", type=Path, help="compiled PDF for layer-3 presence check")
    parser.add_argument("--project", type=Path, default=Path.cwd(),
                        help="base directory for resolving relative source paths")
    parser.add_argument("--main-tex", type=Path, help="main .tex for --lint-xref")
    parser.add_argument("--lint-xref", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="unregistered summaries and lint warnings become failures")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    report, errors, exclusions = run_checks(args)
    report.update({
        "passed": not errors,
        "scope": "paper-results consistency; semantic invariants are only as good as "
                 "the declared cross_checks",
        "exclusions": exclusions,
        "errors": errors,
    })
    output = args.output or (args.project / "consistency_report.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
