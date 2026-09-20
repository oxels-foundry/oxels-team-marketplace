"""Shared records for the optional final-document QA commands."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from redline_guard.resolution_log import file_sha256


class QAError(ValueError):
    """QA could not finish or its evidence is no longer current."""


def file_record(path: str | Path) -> dict:
    path = Path(path).resolve()
    return {"path": str(path), "sha256": file_sha256(path)}


def check_record(record: dict) -> Path:
    path = Path(record["path"])
    if not path.is_file() or file_sha256(path) != record["sha256"]:
        raise QAError(f"QA evidence changed or is missing: {path}. Run finalization again.")
    return path


def stable_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path: str | Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise QAError(f"Expected a JSON object in {path}.")
    return data
