"""Generate a simple JSON test report for NEA evidence.

Why this exists:
    The AQA NEA benefits from clear, reproducible testing evidence.
    This script produces a `test_report.json` file without relying on
    third-party pytest reporting plugins.

How it works:
    1) Uses `pytest --collect-only -q` to list tests.
    2) Runs each test node individually and records pass/fail and duration.

Run:
    python tools/generate_test_report.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "test_report.json"


@dataclass
class TestCaseResult:
    nodeid: str
    passed: bool
    duration_s: float
    stdout: str
    stderr: str


def _run(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )


def main() -> int:
    # pytest 9 may suppress node ids under -q, so collect without -q.
    collect = _run([sys.executable, "-m", "pytest", "--collect-only"])
    if collect.returncode != 0:
        REPORT_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "python": sys.version,
                    "platform": sys.platform,
                    "root": str(ROOT),
                    "ok": False,
                    "error": "pytest collection failed",
                    "stdout": collect.stdout,
                    "stderr": collect.stderr,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 1

    nodeids = [
        line.strip()
        for line in collect.stdout.splitlines()
        if line.strip() and "::" in line and not line.strip().startswith("=")
    ]

    results: List[TestCaseResult] = []
    started = time.perf_counter()
    for nodeid in nodeids:
        t0 = time.perf_counter()
        run = _run([sys.executable, "-m", "pytest", "-q", nodeid])
        t1 = time.perf_counter()
        results.append(
            TestCaseResult(
                nodeid=nodeid,
                passed=(run.returncode == 0),
                duration_s=round(t1 - t0, 4),
                stdout=run.stdout.strip(),
                stderr=run.stderr.strip(),
            )
        )

    total_s = round(time.perf_counter() - started, 4)
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "root": str(ROOT),
        "ok": failed == 0,
        "summary": {
            "tests": len(results),
            "passed": passed,
            "failed": failed,
            "total_duration_s": total_s,
        },
        "cases": [asdict(r) for r in results],
    }

    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Tests: {passed}/{len(results)} passed")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
