from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .metrics import group_sections, normalize_metric_selection, select_metrics
from .models import MetricInfo, ServerReport
from .parser import NmonParseError, parse_nmon


def discover_nmon_files(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir)
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")
    return sorted(root.rglob("*.nmon"))


def load_servers(
    input_dir: str | Path,
    start: str | None,
    end: str | None,
    metrics: str | list[str] | None,
) -> tuple[list[ServerReport], list[dict[str, str]], dict[str, list[str]], list[str]]:
    selected = normalize_metric_selection(metrics)
    start_ts = _parse_optional_timestamp(start, "start")
    end_ts = _parse_optional_timestamp(end, "end")
    if start_ts and end_ts and start_ts > end_ts:
        raise ValueError("Start time must be before end time")

    servers: list[ServerReport] = []
    failures: list[dict[str, str]] = []
    discovered: dict[str, list[str]] = {}

    for path in discover_nmon_files(input_dir):
        try:
            nmon = parse_nmon(path)
            filtered_sections = {
                name: _filter_time(frame, start_ts, end_ts)
                for name, frame in nmon.sections.items()
            }
            filtered_sections = {
                name: frame for name, frame in filtered_sections.items() if not frame.empty
            }
            grouped = group_sections(list(nmon.sections))
            selected_grouped = select_metrics(grouped, selected)
            selected_sections = {
                info.section
                for infos in selected_grouped.values()
                for info in infos
            }
            report_sections = {
                name: frame
                for name, frame in filtered_sections.items()
                if name in selected_sections
            }
            selected_grouped = _drop_empty_metric_infos(selected_grouped, report_sections)
            warnings = list(nmon.warnings)
            if not report_sections:
                warnings.append("No selected metric data found in the requested time range")

            summaries = summarize_sections(report_sections, selected_grouped)
            servers.append(
                ServerReport(
                    host=nmon.host,
                    path=nmon.path,
                    metadata=nmon.metadata,
                    sections=report_sections,
                    metrics=selected_grouped,
                    summaries=summaries,
                    images=[],
                    warnings=warnings,
                )
            )
            discovered[nmon.host] = nmon.discovered_sections
        except (NmonParseError, OSError, ValueError) as exc:
            failures.append({"path": str(path), "error": str(exc)})

    return servers, failures, discovered, selected


def summarize_sections(
    sections: dict[str, pd.DataFrame],
    grouped: dict[str, list[MetricInfo]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    info_by_section = {
        info.section: info
        for infos in grouped.values()
        for info in infos
    }
    for section, frame in sorted(sections.items()):
        info = info_by_section.get(section)
        numeric_columns = _numeric_columns(frame)
        for column in numeric_columns:
            series = pd.to_numeric(frame[column], errors="coerce").dropna()
            if series.empty:
                continue
            max_index = series.idxmax()
            summaries.append(
                {
                    "theme": info.theme if info else "unclassified",
                    "section": section,
                    "metric": column,
                    "unit": info.unit if info else "",
                    "avg": float(series.mean()),
                    "max": float(series.max()),
                    "p95": float(series.quantile(0.95)),
                    "peak_time": frame.loc[max_index, "timestamp"],
                    "samples": int(series.count()),
                }
            )
    return summaries


def build_overall_summary(servers: list[ServerReport]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for server in servers:
        for summary in server.summaries:
            rows.append(
                {
                    "host": server.host,
                    **summary,
                }
            )
    rows.sort(key=lambda item: (item["theme"], -item["max"], item["host"], item["section"]))
    return rows


def build_server_overview(servers: list[ServerReport]) -> list[dict[str, str]]:
    return [_server_overview(server) for server in servers]


def build_server_overview_payload(servers: list[ServerReport]) -> list[dict[str, Any]]:
    return [_server_overview_payload(server) for server in servers]


def _drop_empty_metric_infos(
    grouped: dict[str, list[MetricInfo]],
    sections: dict[str, pd.DataFrame],
) -> dict[str, list[MetricInfo]]:
    available = set(sections)
    result: dict[str, list[MetricInfo]] = {}
    for theme, infos in grouped.items():
        kept = [info for info in infos if info.section in available]
        if kept:
            result[theme] = kept
    return result


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in frame.columns:
        if column in {"timestamp", "timestamp_id", "source_line"}:
            continue
        if pd.api.types.is_numeric_dtype(frame[column]):
            columns.append(column)
    return columns


def _filter_time(
    frame: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    result = frame
    if start is not None:
        result = result[result["timestamp"] >= start]
    if end is not None:
        result = result[result["timestamp"] <= end]
    return result.reset_index(drop=True)


def _parse_optional_timestamp(value: str | None, label: str) -> pd.Timestamp | None:
    if not value:
        return None
    stamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(stamp):
        raise ValueError(f"Invalid {label} time: {value}")
    return pd.Timestamp(stamp).tz_localize(None)


def _server_overview(server: ServerReport) -> dict[str, str]:
    return {
        "file_name": server.path.name,
        "ip_address": _metadata_value(server, "ip", "ip_address", "host_ip", "hostip"),
        "cpu_usage": _format_percent(_cpu_usage(server)),
        "memory_usage": _format_percent(_memory_usage(server)),
        "swap_usage": _format_percent(_swap_usage(server)),
        "disk_read": _format_number(_max_section_value(server, ("DISKREAD",))),
        "disk_write": _format_number(_max_section_value(server, ("DISKWRITE",))),
        "network_read": _format_number(_network_value(server, ("read", "recv", "receive", "in"))),
        "network_write": _format_number(_network_value(server, ("write", "send", "transmit", "out"))),
        "system_type": _metadata_value(server, "os", "os_release", "system", "system_type", "machine_type"),
        "read_range": _read_range(server),
    }


def _server_overview_payload(server: ServerReport) -> dict[str, Any]:
    return {
        "file_name": server.path.name,
        "ip_address": _metadata_value(server, "ip", "ip_address", "host_ip", "hostip"),
        "system_type": _metadata_value(server, "os", "os_release", "system", "system_type", "machine_type"),
        "metrics": {
            "cpu_usage": _metric_points(server.sections.get("CPU_ALL"), _cpu_usage_series(server)),
            "memory_usage": _metric_points(_first_section(server, "MEM", "MEMNEW"), _memory_usage_series(server)),
            "swap_usage": _metric_points(_first_section(server, "MEM", "MEMNEW"), _swap_usage_series(server)),
            "disk_read": _metric_points(server.sections.get("DISKREAD"), _section_max_series(server, ("DISKREAD",))),
            "disk_write": _metric_points(server.sections.get("DISKWRITE"), _section_max_series(server, ("DISKWRITE",))),
            "network_read": _metric_points(
                server.sections.get("NET"),
                _network_series(server, ("read", "recv", "receive", "in")),
            ),
            "network_write": _metric_points(
                server.sections.get("NET"),
                _network_series(server, ("write", "send", "transmit", "out")),
            ),
        },
        "range_points": _range_points(server),
    }


def _metadata_value(server: ServerReport, *keys: str) -> str:
    metadata = getattr(server, "metadata", {})
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value)
    return "-"


def _cpu_usage(server: ServerReport) -> float | None:
    return _max_series(_cpu_usage_series(server))


def _cpu_usage_series(server: ServerReport) -> pd.Series:
    frame = server.sections.get("CPU_ALL")
    if frame is None or frame.empty:
        return pd.Series(dtype="float64")
    if "Busy" in frame:
        busy = _numeric(frame["Busy"]).clip(lower=0, upper=100)
        if _has_values(busy):
            return busy
    idle_column = _find_column(frame, "Idle%")
    if idle_column:
        return (100.0 - _numeric(frame[idle_column])).clip(lower=0, upper=100)
    columns = [column for column in ("User%", "Sys%", "Wait%") if column in frame]
    if columns:
        return frame[columns].apply(pd.to_numeric, errors="coerce").sum(axis=1).clip(lower=0, upper=100)
    return pd.Series(dtype="float64")


def _memory_usage(server: ServerReport) -> float | None:
    return _max_series(_memory_usage_series(server))


def _memory_usage_series(server: ServerReport) -> pd.Series:
    frame = _first_section(server, "MEM", "MEMNEW")
    if frame is None or frame.empty:
        return pd.Series(dtype="float64")
    total_column = _find_column(frame, "Real total MB", "memtotal")
    free_column = _find_column(frame, "Real free MB", "memfree")
    cached_column = _find_column(frame, "cached", "Cached")
    buffers_column = _find_column(frame, "buffers", "Buffers")
    if free_column and total_column:
        total = pd.to_numeric(frame[total_column], errors="coerce")
        free = pd.to_numeric(frame[free_column], errors="coerce")
        used = total - free
        if cached_column:
            used -= pd.to_numeric(frame[cached_column], errors="coerce").fillna(0)
        if buffers_column:
            used -= pd.to_numeric(frame[buffers_column], errors="coerce").fillna(0)
        return (used / total.replace(0, pd.NA) * 100).clip(lower=0, upper=100)
    return _matching_column_series(frame, ("used", "%")).clip(lower=0, upper=100)


def _swap_usage(server: ServerReport) -> float | None:
    return _max_series(_swap_usage_series(server))


def _swap_usage_series(server: ServerReport) -> pd.Series:
    frame = _first_section(server, "MEM", "MEMNEW")
    if frame is None or frame.empty:
        return pd.Series(dtype="float64")
    free_column = _find_column(frame, "Virtual free MB", "swapfree")
    total_column = _find_column(frame, "Virtual total MB", "swaptotal")
    if free_column and total_column:
        total = pd.to_numeric(frame[total_column], errors="coerce")
        free = pd.to_numeric(frame[free_column], errors="coerce")
        return ((total - free) / total.replace(0, pd.NA) * 100).fillna(0).clip(lower=0, upper=100)
    return _matching_column_series(frame, ("swap", "used")).clip(lower=0, upper=100)


def _max_section_value(server: ServerReport, section_names: tuple[str, ...]) -> float | None:
    return _max_series(_section_max_series(server, section_names))


def _section_max_series(server: ServerReport, section_names: tuple[str, ...]) -> pd.Series:
    values = []
    for section in section_names:
        frame = server.sections.get(section)
        if frame is not None:
            series = _frame_max_series(frame)
            if _has_values(series):
                values.append(series)
    if not values:
        return pd.Series(dtype="float64")
    return pd.concat(values, axis=1).max(axis=1)


def _network_value(server: ServerReport, keywords: tuple[str, ...]) -> float | None:
    return _max_series(_network_series(server, keywords))


def _network_series(server: ServerReport, keywords: tuple[str, ...]) -> pd.Series:
    frame = server.sections.get("NET")
    if frame is None or frame.empty:
        return pd.Series(dtype="float64")
    matching = [
        column
        for column in _numeric_columns(frame)
        if any(keyword in column.lower() for keyword in keywords)
    ]
    if matching:
        return _frame_max_series(frame[matching])
    return _frame_max_series(frame)


def _read_range(server: ServerReport) -> str:
    values = []
    for frame in server.sections.values():
        if "source_line" in frame:
            values.extend(pd.to_numeric(frame["source_line"], errors="coerce").dropna().tolist())
    if values:
        return f"{int(min(values))}-{int(max(values))}"
    timestamp_ids = []
    for frame in server.sections.values():
        if "timestamp_id" in frame:
            timestamp_ids.extend(frame["timestamp_id"].dropna().astype(str).tolist())
    return f"{min(timestamp_ids)}-{max(timestamp_ids)}" if timestamp_ids else "-"


def _find_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    lowered = {str(column).lower(): column for column in frame.columns}
    for candidate in candidates:
        key = candidate.lower()
        if key in lowered:
            return str(lowered[key])
    for column in frame.columns:
        column_lower = str(column).lower()
        if all(part in column_lower for part in candidates):
            return str(column)
    return None


def _max_matching_column(frame: pd.DataFrame, keywords: tuple[str, ...]) -> float | None:
    columns = [
        column
        for column in _numeric_columns(frame)
        if all(keyword.lower() in column.lower() for keyword in keywords)
    ]
    if not columns:
        return None
    return _max_frame_value(frame[columns])


def _max_frame_value(frame: pd.DataFrame) -> float | None:
    return _max_series(_frame_max_series(frame))


def _frame_max_series(frame: pd.DataFrame) -> pd.Series:
    columns = _numeric_columns(frame)
    if not columns:
        return pd.Series(dtype="float64")
    return frame[columns].apply(pd.to_numeric, errors="coerce").max(axis=1)


def _max_series(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.max()) if not values.empty else None


def _min_series(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.min()) if not values.empty else None


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _has_values(series: pd.Series | None) -> bool:
    return series is not None and not series.dropna().empty


def _format_percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _format_number(value: float | None) -> str:
    return "-" if value is None else f"{value:,.2f}"


def _first_section(server: ServerReport, *names: str) -> pd.DataFrame | None:
    for name in names:
        frame = server.sections.get(name)
        if frame is not None:
            return frame
    return None


def _matching_column_series(frame: pd.DataFrame, keywords: tuple[str, ...]) -> pd.Series:
    columns = [
        column
        for column in _numeric_columns(frame)
        if all(keyword.lower() in column.lower() for keyword in keywords)
    ]
    if not columns:
        return pd.Series(dtype="float64")
    return _frame_max_series(frame[columns])


def _metric_points(frame: pd.DataFrame | None, series: pd.Series) -> list[list[object]]:
    if frame is None or frame.empty or not _has_values(series):
        return []
    points = []
    aligned = series.reindex(frame.index)
    for index, value in aligned.items():
        clean_value = pd.to_numeric(value, errors="coerce")
        if pd.isna(clean_value):
            continue
        points.append(
            [
                pd.Timestamp(frame.loc[index, "timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                round(float(clean_value), 4),
            ]
        )
    return points


def _range_points(server: ServerReport) -> list[list[object]]:
    points = set()
    for frame in server.sections.values():
        if frame.empty or "timestamp" not in frame:
            continue
        for _, row in frame.iterrows():
            source_line = row.get("source_line")
            if pd.isna(source_line):
                continue
            points.add(
                (
                    pd.Timestamp(row["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                    int(source_line),
                )
            )
    return [[time, line] for time, line in sorted(points, key=lambda item: (item[0], item[1]))]
