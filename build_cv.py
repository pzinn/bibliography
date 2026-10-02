#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


CV_DIR = Path(__file__).resolve().parent / "cv"
DOCUMENTS = ("cv-only", "publications-only", "cv-full")


def build() -> None:
    for executable in ("pdflatex", "bibtex"):
        if shutil.which(executable) is None:
            raise SystemExit(f"Missing {executable}: install a TeX distribution to build the CV.")

    for document in DOCUMENTS:
        latex_command = [
            "pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{document}.tex"
        ]
        subprocess.run(latex_command, cwd=CV_DIR, check=True)
        if document != "cv-only":
            subprocess.run(["bibtex", document], cwd=CV_DIR, check=True)
        subprocess.run(latex_command, cwd=CV_DIR, check=True)
        subprocess.run(latex_command, cwd=CV_DIR, check=True)
        print(f"Built {CV_DIR / (document + '.pdf')}", flush=True)


if __name__ == "__main__":
    build()
