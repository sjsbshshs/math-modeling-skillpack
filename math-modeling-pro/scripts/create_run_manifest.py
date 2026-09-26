#!/usr/bin/env python3
"""Create a reproducibility manifest for a modeling project.

The script is intentionally standard-library-only so it can run before the
project's scientific dependencies are installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import locale
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tool_version(tool: str) -> str | None:
    resolved = shutil.which(tool)
    if not resolved:
        return None
    for args in (("--version",), ("-version",)):
        try:
            result = subprocess.run(
                [resolved, *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        text = (result.stdout or result.stderr).strip().splitlines()
        if text:
            return text[0][:300]
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--file", dest="files", action="append", default=[],
        help="Project-relative file to hash; repeat for multiple files.",
    )
    args = parser.parse_args()
    project = args.project.resolve()
    output = args.output.resolve()
    if not project.is_dir():
        parser.error(f"project is not a directory: {project}")

    files: dict[str, str] = {}
    for raw in args.files:
        candidate = (project / raw).resolve()
        try:
            relative = candidate.relative_to(project).as_posix()
        except ValueError:
            parser.error(f"file is outside project: {raw}")
        if not candidate.is_file():
            parser.error(f"file does not exist: {raw}")
        files[relative] = sha256(candidate)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "locale_encoding": locale.getpreferredencoding(False),
            "filesystem_encoding": sys.getfilesystemencoding(),
            "timezone": os.environ.get("TZ"),
        },
        "tools": {
            name: tool_version(name)
            for name in ("xelatex", "pdflatex", "pdftotext", "pdfinfo", "pdffonts")
        },
        "files_sha256": files,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "hashed_files": len(files)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
