from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Sequence


def json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError("Object of type %s is not JSON serialisable" % type(value).__name__)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def timestamp_slug(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, payload: Any) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")
    return path


def write_json_artifact(base_dir: Path, stem: str, payload: Any, now: datetime) -> Path:
    return write_json(base_dir / ("%s_%s.json" % (stem, timestamp_slug(now))), payload)


def append_jsonl(path: Path, payload: Any) -> Path:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=json_default))
        handle.write("\n")
    return path


def read_jsonl(path: Path) -> Sequence[Any]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> Path:
    ensure_dir(path.parent)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
    return path


def write_csv_artifact(base_dir: Path, stem: str, rows: Sequence[Dict[str, Any]], now: datetime) -> Path:
    return write_csv(base_dir / ("%s_%s.csv" % (stem, timestamp_slug(now))), rows)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if is_dataclass(value):
        return json.dumps(asdict(value), default=json_default)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=json_default)
    return value
