from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from .models import NmonFile

TSTAMP_RE = re.compile(r"^T\d+", re.IGNORECASE)


class NmonParseError(ValueError):
    pass


def parse_nmon(path: str | Path) -> NmonFile:
    file_path = Path(path)
    if not file_path.exists():
        raise NmonParseError(f"File does not exist: {file_path}")

    metadata: dict[str, str] = {}
    headers: dict[str, list[str]] = {}
    rows: dict[str, list[tuple[int, list[str]]]] = defaultdict(list)
    timestamps: dict[str, pd.Timestamp] = {}
    warnings: list[str] = []

    with file_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for line_number, raw in enumerate(reader, start=1):
            if not raw:
                continue
            row = [cell.strip() for cell in raw]
            section = row[0]
            if not section:
                continue

            if section == "AAA":
                _read_metadata(row, metadata)
                continue
            if section == "ZZZZ":
                stamp = _read_timestamp(row)
                if stamp is not None:
                    timestamps[row[1]] = stamp
                else:
                    warnings.append(f"Could not parse timestamp row: {','.join(row)}")
                continue
            if len(row) < 2:
                continue

            second = row[1]
            if TSTAMP_RE.match(second):
                rows[section].append((line_number, row[1:]))
            else:
                headers[section] = _normalize_header(row)

    if not timestamps:
        raise NmonParseError("No ZZZZ timestamp rows found")

    sections: dict[str, pd.DataFrame] = {}
    for section, section_rows in rows.items():
        frame = _build_frame(section, section_rows, headers.get(section), timestamps)
        if frame.empty:
            warnings.append(f"Section {section} has no rows with known timestamps")
        else:
            sections[section] = frame

    if not sections:
        raise NmonParseError("No time-series sections found")

    host = _derive_host(file_path, metadata)
    return NmonFile(
        path=file_path,
        host=host,
        metadata=metadata,
        timestamps=timestamps,
        sections=sections,
        section_headers=headers,
        warnings=warnings,
    )


def _read_metadata(row: list[str], metadata: dict[str, str]) -> None:
    if len(row) >= 3:
        key = row[1].strip().lower().replace(" ", "_")
        metadata[key] = row[2].strip()
    elif len(row) == 2:
        metadata.setdefault("note", row[1].strip())


def _read_timestamp(row: list[str]) -> pd.Timestamp | None:
    if len(row) < 4:
        return None
    strict_candidates = (
        (f"{row[3]} {row[2]}", ("%d-%b-%Y %H:%M:%S", "%d-%B-%Y %H:%M:%S")),
        (f"{row[2]} {row[3]}", ("%H:%M:%S %d-%b-%Y", "%H:%M:%S %d-%B-%Y")),
    )
    for candidate, formats in strict_candidates:
        for fmt in formats:
            try:
                return pd.Timestamp(datetime.strptime(candidate, fmt))
            except ValueError:
                continue
    for candidate, _formats in strict_candidates:
        stamp = pd.to_datetime(candidate, errors="coerce", dayfirst=True)
        if not pd.isna(stamp):
            return pd.Timestamp(stamp).tz_localize(None)
    return None


def _normalize_header(row: list[str]) -> list[str]:
    names = ["timestamp_id"]
    for index, raw_name in enumerate(row[1:], start=1):
        name = raw_name.strip() or f"value_{index}"
        if index == 1 and TSTAMP_RE.match(name):
            name = "timestamp_id"
        names.append(_dedupe_name(name, names))
    return names


def _dedupe_name(name: str, existing: list[str]) -> str:
    candidate = name
    counter = 2
    while candidate in existing:
        candidate = f"{name}_{counter}"
        counter += 1
    return candidate


def _build_frame(
    section: str,
    rows: list[tuple[int, list[str]]],
    header: list[str] | None,
    timestamps: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    max_width = max(len(row) for _line_number, row in rows)
    if header is None:
        columns = ["timestamp_id"] + [f"value_{index}" for index in range(1, max_width)]
    else:
        columns = header[:]
        if len(columns) == max_width + 1:
            columns = [columns[0]] + columns[2:]
        if len(columns) > max_width:
            columns = [column for column in columns if not column.startswith("value_")]
        while len(columns) < max_width:
            columns.append(f"value_{len(columns)}")
        columns = columns[:max_width]

    line_numbers = [line_number for line_number, _row in rows]
    normalized_rows = [row + [""] * (max_width - len(row)) for _line_number, row in rows]
    frame = pd.DataFrame(normalized_rows, columns=columns)
    frame.insert(0, "source_line", line_numbers)
    frame = frame[frame["timestamp_id"].isin(timestamps)].copy()
    if frame.empty:
        return frame

    frame.insert(0, "timestamp", frame["timestamp_id"].map(timestamps))
    for column in frame.columns:
        if column in {"timestamp", "timestamp_id", "source_line"}:
            continue
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().any():
            frame[column] = converted
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame.attrs["section"] = section
    return frame


def _derive_host(path: Path, metadata: dict[str, str]) -> str:
    for key in ("host", "hostname", "node", "server"):
        value = metadata.get(key)
        if value:
            return value
    return path.stem
