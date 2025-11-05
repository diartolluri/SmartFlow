"""Result export helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable


def export_csv(path: Path, rows: Iterable[dict]) -> None:
    """Write simulation metrics to CSV."""

    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    header = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def export_pdf(path: Path, report_data: Any) -> None:
    """Optional PDF report generation hook."""

    raise NotImplementedError("Integrate ReportLab or similar here")
