from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import numpy as np


@dataclass(frozen=True)
class ChartSeries:
    name: str
    frame: pd.DataFrame
    values: pd.Series
    unit: str = ""


def theme_chart_series(theme: str, sections: dict[str, pd.DataFrame]) -> list[ChartSeries]:
    if theme == "cpu":
        return _cpu_series(sections)
    if theme == "memory":
        return _memory_series(sections)
    if theme == "disk":
        return _disk_series(sections)
    if theme == "network":
        return _network_series(sections)
    return _raw_series(sections)


def _cpu_series(sections: dict[str, pd.DataFrame]) -> list[ChartSeries]:
    frame = sections.get("CPU_ALL")
    if frame is None:
        return []
    result = []
    for column, name in (("User%", "用户 (%)"), ("Sys%", "系统 (%)"), ("Wait%", "等待 (%)")):
        if column in frame:
            result.append(ChartSeries(name, frame, _numeric(frame[column]), "%"))
    return result


def _memory_series(sections: dict[str, pd.DataFrame]) -> list[ChartSeries]:
    frame = _first_section(sections, "MEM", "MEMNEW")
    if frame is None:
        return []
    result = []
    memory_usage = _usage_percent(frame, "memtotal", "memfree")
    if memory_usage is None:
        memory_usage = _usage_percent(frame, "Real total MB", "Real free MB")
    if memory_usage is not None:
        result.append(ChartSeries("内存 (%)", frame, memory_usage, "%"))
    swap_usage = _usage_percent(frame, "swaptotal", "swapfree")
    if swap_usage is None:
        swap_usage = _usage_percent(frame, "Virtual total MB", "Virtual free MB")
    if swap_usage is not None:
        result.append(ChartSeries("SWAP (%)", frame, swap_usage, "%"))

    vm = sections.get("VM")
    if vm is not None:
        if "pswpin" in vm:
            result.append(ChartSeries("SwapIn (/s)", vm, _numeric(vm["pswpin"]), "/s"))
        if "pswpout" in vm:
            result.append(ChartSeries("SwapOut (/s)", vm, _numeric(vm["pswpout"]), "/s"))
    return result


def _disk_series(sections: dict[str, pd.DataFrame]) -> list[ChartSeries]:
    result = []
    xfer = sections.get("DISKXFER")
    if xfer is not None:
        result.append(ChartSeries("IO (/s)", xfer, _sum_columns(xfer), "/s"))
    read = sections.get("DISKREAD")
    if read is not None:
        result.append(ChartSeries("读速率 (KB/s)", read, _sum_columns(read), "KB/s"))
    write = sections.get("DISKWRITE")
    if write is not None:
        result.append(ChartSeries("写速率 (KB/s)", write, -_sum_columns(write), "KB/s"))
    return result


def _network_series(sections: dict[str, pd.DataFrame]) -> list[ChartSeries]:
    result = []
    packets = sections.get("NETPACKET")
    if packets is not None:
        read_packets = _sum_matching_columns(packets, ("read/s",))
        write_packets = _sum_matching_columns(packets, ("write/s",))
        if read_packets is not None:
            result.append(ChartSeries("IO读 (/s)", packets, read_packets, "/s"))
        if write_packets is not None:
            result.append(ChartSeries("IO写 (/s)", packets, -write_packets, "/s"))

    net = sections.get("NET")
    if net is not None:
        read = _sum_matching_columns(net, ("read-kb/s",))
        write = _sum_matching_columns(net, ("write-kb/s",))
        if read is not None:
            result.append(ChartSeries("读速率 (KB/s)", net, read, "KB/s"))
        if write is not None:
            result.append(ChartSeries("写速率 (KB/s)", net, -write, "KB/s"))
    return result


def _raw_series(sections: dict[str, pd.DataFrame]) -> list[ChartSeries]:
    result = []
    for section, frame in sections.items():
        for column in _numeric_columns(frame):
            result.append(ChartSeries(f"{section}:{column}", frame, _numeric(frame[column])))
    return result


def _usage_percent(frame: pd.DataFrame, total_column: str, free_column: str) -> pd.Series | None:
    if total_column not in frame or free_column not in frame:
        return None
    total = _numeric(frame[total_column])
    free = _numeric(frame[free_column])
    used = np.where(total == 0, 0.0, (total - free) / total * 100)
    return pd.Series(used, index=frame.index)


def _sum_columns(frame: pd.DataFrame) -> pd.Series:
    columns = _numeric_columns(frame)
    if not columns:
        return pd.Series([0.0] * len(frame), index=frame.index)
    return frame[columns].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)


def _sum_matching_columns(frame: pd.DataFrame, keywords: tuple[str, ...]) -> pd.Series | None:
    columns = [
        column
        for column in _numeric_columns(frame)
        if all(keyword.lower() in column.lower() for keyword in keywords)
    ]
    if not columns:
        return None
    return frame[columns].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [
        str(column)
        for column in frame.columns
        if column not in {"timestamp", "timestamp_id", "source_line"}
        and pd.api.types.is_numeric_dtype(frame[column])
    ]


def _first_section(sections: dict[str, pd.DataFrame], *names: str) -> pd.DataFrame | None:
    for name in names:
        frame = sections.get(name)
        if frame is not None:
            return frame
    return None
