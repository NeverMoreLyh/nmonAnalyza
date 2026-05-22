from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "nmon-report-matplotlib"))

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = [
    "PingFang SC",
    "Hiragino Sans GB",
    "Arial Unicode MS",
    "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .models import ServerReport

ChartImage = dict[str, str]

PNG_DPI = 100
FIGURE_SIZE = (16, 9)
DEFAULT_TOP_N = 5


def generate_charts(
    servers: list[ServerReport],
    image_dir: str | Path,
    top_n: int = DEFAULT_TOP_N,
    network_bandwidth_mbps: float | None = None,
) -> list[ChartImage]:
    output = Path(image_dir)
    output.mkdir(parents=True, exist_ok=True)
    clean_top_n = max(1, int(top_n or DEFAULT_TOP_N))

    for server in servers:
        server.images = []
        server_dir = output / _slug(server.host)
        server_dir.mkdir(parents=True, exist_ok=True)
        _generate_server_charts(server, server_dir, clean_top_n, network_bandwidth_mbps)

    if len(servers) > 1:
        return _generate_summary_charts(servers, output)
    return []


def build_interactive_chart_specs(
    server: ServerReport,
    top_n: int = DEFAULT_TOP_N,
    network_bandwidth_mbps: float | None = None,
) -> list[dict[str, object]]:
    clean_top_n = max(1, int(top_n or DEFAULT_TOP_N))
    specs: list[dict[str, object]] = []
    for theme, title, filename, builder in _interactive_builders(network_bandwidth_mbps):
        if theme not in server.metrics:
            continue
        frame, series, unit, percent = builder(server, clean_top_n, network_bandwidth_mbps)
        clean_series = {name: values for name, values in series.items() if _has_values(values)}
        if frame is None or frame.empty or not clean_series:
            continue
        display_title = title.replace("TopN", f"Top{clean_top_n}")
        specs.append(
            {
                "theme": theme,
                "title": f"{server.host} {display_title}",
                "name": filename,
                "unit": unit,
                "percent": percent,
                "chart_type": "stacked-area" if theme == "cpu" and filename == "cpu_usage.png" else "line",
                "signed_mirror": filename in {"disk_io_top5.png", "network_top5.png"},
                "max_abs": _max_abs(clean_series),
                "series": [_series_payload(name, frame, values) for name, values in clean_series.items()],
            }
        )
    return specs


def _interactive_builders(
    network_bandwidth_mbps: float | None,
) -> list[tuple[str, str, str, Callable[[ServerReport, int, float | None], tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]]]]:
    builders: list[tuple[str, str, str, Callable[[ServerReport, int, float | None], tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]]]] = [
        ("cpu", "CPU 使用率趋势图", "cpu_usage.png", _cpu_usage_data),
        ("memory", "内存使用率趋势图", "memory_usage_percent.png", _memory_usage_percent_data),
        ("memory", "内存明细趋势图", "memory_detail.png", _memory_detail_data),
        ("memory", "Swap 使用趋势图", "swap_usage.png", _swap_usage_data),
        ("disk", "磁盘 Busy TopN 趋势图", "disk_busy_top5.png", _disk_busy_data),
        ("disk", "磁盘读写吞吐 TopN 趋势图", "disk_io_top5.png", _disk_io_data),
        ("disk", "磁盘 IOPS TopN 趋势图", "disk_iops_top5.png", _disk_iops_data),
        ("network", "网络吞吐 TopN 趋势图", "network_top5.png", _network_top_data),
    ]
    if network_bandwidth_mbps:
        builders.append(("network", "网络带宽使用率趋势图", "network_bandwidth_usage.png", _network_bandwidth_data))
    return builders


def _generate_server_charts(
    server: ServerReport,
    server_dir: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> None:
    specs: list[tuple[str, str, str, Callable[[ServerReport, Path, int, float | None], bool]]] = [
        ("cpu", "CPU 使用率趋势图", "cpu_usage.png", _plot_cpu_usage),
        ("memory", "内存使用率趋势图", "memory_usage_percent.png", _plot_memory_usage_percent),
        ("memory", "内存明细趋势图", "memory_detail.png", _plot_memory_detail),
        ("memory", "Swap 使用趋势图", "swap_usage.png", _plot_swap_usage),
        ("disk", "磁盘 Busy Top5 趋势图", "disk_busy_top5.png", _plot_disk_busy),
        ("disk", "磁盘读写吞吐 Top5 趋势图", "disk_io_top5.png", _plot_disk_io),
        ("disk", "磁盘 IOPS Top5 趋势图", "disk_iops_top5.png", _plot_disk_iops),
        ("network", "网络吞吐 Top5 趋势图", "network_top5.png", _plot_network_top),
    ]
    if network_bandwidth_mbps:
        specs.append(("network", "网络带宽使用率趋势图", "network_bandwidth_usage.png", _plot_network_bandwidth))

    selected_themes = set(server.metrics)
    for theme, title, filename, plotter in specs:
        if theme not in selected_themes:
            continue
        path = server_dir / filename
        if plotter(server, path, top_n, network_bandwidth_mbps):
            server.images.append(
                {
                    "theme": theme,
                    "title": f"{server.host} {title}",
                    "path": str(path),
                    "relative_path": f"images/{server_dir.name}/{filename}",
                    "name": filename,
                }
            )
        else:
            server.warnings.append(f"{filename} 数据缺失")


def _plot_cpu_usage(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _cpu_usage_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, "CPU 使用率趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _plot_memory_usage_percent(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _memory_usage_percent_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, "内存使用率趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _plot_memory_detail(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _memory_detail_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, "内存明细趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _plot_swap_usage(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _swap_usage_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, "Swap 使用趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _plot_disk_busy(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _disk_busy_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, f"磁盘 Busy Top{top_n} 趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _plot_disk_io(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _disk_io_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, f"磁盘读写吞吐 Top{top_n} 趋势图"),
        ylabel=unit,
        percent=percent,
        signed_mirror=True,
    )


def _plot_disk_iops(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _disk_iops_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, f"磁盘 IOPS Top{top_n} 趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _plot_network_top(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _network_top_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, f"网络吞吐 Top{top_n} 趋势图"),
        ylabel=unit,
        percent=percent,
        signed_mirror=True,
    )


def _plot_network_bandwidth(
    server: ServerReport,
    path: Path,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> bool:
    frame, series, unit, percent = _network_bandwidth_data(server, top_n, network_bandwidth_mbps)
    if frame is None or not series:
        return False
    return _line_chart(
        frame,
        series,
        path,
        title=_title(server, "网络带宽使用率趋势图"),
        ylabel=unit,
        percent=percent,
    )


def _generate_summary_charts(servers: list[ServerReport], output: Path) -> list[ChartImage]:
    summary_specs = [
        ("summary_cpu_bar.png", "跨服务器 CPU Busy 汇总图", _summary_cpu_values, "%", True),
        ("summary_memory_bar.png", "跨服务器内存使用率汇总图", _summary_memory_values, "%", True),
        ("summary_disk_busy_bar.png", "跨服务器磁盘 Busy 汇总图", _summary_disk_busy_values, "%", True),
        ("summary_network_bar.png", "跨服务器网络总流量汇总图", _summary_network_values, "MB/s", False),
    ]
    images: list[ChartImage] = []
    for filename, title, value_getter, ylabel, percent in summary_specs:
        rows = []
        for server in servers:
            avg_value, max_value = value_getter(server)
            if avg_value is not None:
                rows.append((server.host, avg_value, max_value))
        if not rows:
            continue
        path = output / filename
        _bar_chart(rows, path, title=title, ylabel=ylabel, percent=percent)
        images.append(
            {
                "theme": "summary",
                "title": title,
                "path": str(path),
                "relative_path": f"images/{filename}",
                "name": filename,
            }
        )
    return images


def _cpu_usage_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    frame = server.sections.get("CPU_ALL")
    if frame is None or frame.empty:
        return None, {}, "%", True
    return (
        frame,
        {
            "CPU Busy%": _cpu_busy_series(frame),
            "User%": _column_series(frame, "User%"),
            "Sys%": _column_series(frame, "Sys%"),
            "Wait%": _column_series(frame, "Wait%"),
        },
        "%",
        True,
    )


def _memory_usage_percent_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    frame = _first_section(server, "MEM", "MEMNEW")
    used = _memory_used_percent(frame)
    return frame, {"Memory Used%": used} if _has_values(used) else {}, "%", True


def _memory_detail_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    frame = _first_section(server, "MEM", "MEMNEW")
    if frame is None or frame.empty:
        return None, {}, "MB", False
    series: dict[str, pd.Series] = {}
    free_column = _find_column(frame, "Memory Available", "available", "Real free MB", "memfree")
    cached_column = _find_column(frame, "Cached", "cached")
    buffers_column = _find_column(frame, "Buffers", "buffers")
    if free_column:
        series["Memory Available/Free"] = _numeric(frame[free_column])
    if cached_column:
        series["Cached"] = _numeric(frame[cached_column])
    if buffers_column:
        series["Buffers"] = _numeric(frame[buffers_column])
    return frame, series, "MB", False


def _swap_usage_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    mem_frame = _first_section(server, "MEM", "MEMNEW")
    vm_frame = _first_section(server, "VM", "PAGE")
    base_frame = mem_frame if mem_frame is not None and not mem_frame.empty else vm_frame
    if base_frame is None or base_frame.empty:
        return None, {}, "%, pages/s", False
    series: dict[str, pd.Series] = {}
    used = _swap_used_percent(mem_frame)
    if _has_values(used):
        series["Swap Used%"] = used
    if vm_frame is not None and not vm_frame.empty:
        swap_in_column = _find_column(vm_frame, "pswpin", "SwapIn", "swapin")
        swap_out_column = _find_column(vm_frame, "pswpout", "SwapOut", "swapout")
        if swap_in_column:
            series["Swap In"] = _numeric(vm_frame[swap_in_column])
        if swap_out_column:
            series["Swap Out"] = _numeric(vm_frame[swap_out_column])
    return base_frame, series, "%, pages/s", False


def _disk_busy_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    frame = server.sections.get("DISKBUSY")
    if frame is None or frame.empty:
        return None, {}, "%", True
    columns = _top_numeric_columns(frame, top_n, lambda values: values.max())
    return frame, {column: _numeric(frame[column]) for column in columns}, "%", True


def _disk_io_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    read_frame = server.sections.get("DISKREAD")
    write_frame = server.sections.get("DISKWRITE")
    if read_frame is None or read_frame.empty or write_frame is None or write_frame.empty:
        return None, {}, "MB/s", False
    disks = sorted(set(_numeric_columns(read_frame)) | set(_numeric_columns(write_frame)))
    ranked = []
    for disk in disks:
        read = _numeric(read_frame[disk]) if disk in read_frame else pd.Series(dtype="float64")
        write = _numeric(write_frame[disk]) if disk in write_frame else pd.Series(dtype="float64")
        total = read.reindex(read_frame.index, fill_value=0) + write.reindex(read_frame.index, fill_value=0)
        if _has_values(total):
            ranked.append((disk, float(total.max())))
    top_disks = [disk for disk, _ in sorted(ranked, key=lambda item: item[1], reverse=True)[:top_n]]
    series: dict[str, pd.Series] = {}
    for disk in top_disks:
        if disk in read_frame:
            series[f"{disk} Read MB/s"] = _numeric(read_frame[disk]) / 1024.0
        if disk in write_frame:
            series[f"{disk} Write MB/s"] = -(_numeric(write_frame[disk]) / 1024.0)
    return read_frame, series, "MB/s", False


def _disk_iops_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    frame = server.sections.get("DISKXFER")
    if frame is None or frame.empty:
        return None, {}, "Xfer/s", False
    columns = _top_numeric_columns(frame, top_n, lambda values: values.max())
    return frame, {f"{column} Xfer/s": _numeric(frame[column]) for column in columns}, "Xfer/s", False


def _network_top_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    frame = server.sections.get("NET")
    pairs = _network_pairs(frame)
    if frame is None or frame.empty or not pairs:
        return None, {}, "MB/s", False
    top_ifaces = _top_network_interfaces(frame, pairs, top_n)
    series: dict[str, pd.Series] = {}
    for iface in top_ifaces:
        read_column, write_column = pairs[iface]
        if read_column:
            series[f"{iface} Receive MB/s"] = _numeric(frame[read_column]) / 1024.0
        if write_column:
            series[f"{iface} Transmit MB/s"] = -(_numeric(frame[write_column]) / 1024.0)
    return frame, series, "MB/s", False


def _network_bandwidth_data(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> tuple[pd.DataFrame | None, dict[str, pd.Series], str, bool]:
    if not network_bandwidth_mbps:
        return None, {}, "%", True
    frame = server.sections.get("NET")
    pairs = _network_pairs(frame)
    if frame is None or frame.empty or not pairs:
        return None, {}, "%", True
    total = _network_total_mbps(frame, pairs)
    usage = total * 8.0 / network_bandwidth_mbps * 100.0
    return frame, {"Bandwidth Usage%": usage}, "%", True


def _line_chart(
    frame: pd.DataFrame,
    series: dict[str, pd.Series],
    path: Path,
    title: str,
    ylabel: str,
    percent: bool = False,
    signed_mirror: bool = False,
) -> bool:
    clean_series = {name: values for name, values in series.items() if _has_values(values)}
    if frame.empty or not clean_series:
        return False
    figure, axis = plt.subplots(figsize=FIGURE_SIZE, dpi=PNG_DPI)
    for name, values in clean_series.items():
        aligned = values.reindex(frame.index)
        axis.plot(frame["timestamp"], aligned, linewidth=1.4, label=name)
    axis.set_title(title, fontsize=16)
    axis.set_xlabel("采样时间")
    axis.set_ylabel(ylabel)
    if percent:
        axis.set_ylim(0, 100)
    elif signed_mirror:
        limit = _max_abs(clean_series)
        if limit > 0:
            axis.set_ylim(-limit, limit)
            axis.yaxis.set_major_formatter(lambda value, position: f"{abs(value):g}")
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best", fontsize=9, ncol=2)
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(path, dpi=PNG_DPI)
    plt.close(figure)
    return True


def _bar_chart(
    rows: list[tuple[str, float | None, float | None]],
    path: Path,
    title: str,
    ylabel: str,
    percent: bool,
) -> None:
    hosts = [row[0] for row in rows]
    avg_values = [0 if row[1] is None else row[1] for row in rows]
    max_values = [0 if row[2] is None else row[2] for row in rows]
    x_values = range(len(hosts))
    figure, axis = plt.subplots(figsize=FIGURE_SIZE, dpi=PNG_DPI)
    axis.bar([x - 0.18 for x in x_values], avg_values, width=0.36, label="平均值")
    axis.bar([x + 0.18 for x in x_values], max_values, width=0.36, label="最大值")
    axis.set_xticks(list(x_values), hosts, rotation=30, ha="right")
    axis.set_title(title, fontsize=16)
    axis.set_ylabel(ylabel)
    if percent:
        axis.set_ylim(0, 100)
    axis.grid(True, axis="y", alpha=0.25)
    axis.legend(loc="best")
    figure.tight_layout()
    figure.savefig(path, dpi=PNG_DPI)
    plt.close(figure)


def _series_payload(name: str, frame: pd.DataFrame, values: pd.Series) -> dict[str, object]:
    points = []
    aligned = values.reindex(frame.index)
    for index, value in aligned.items():
        clean_value = pd.to_numeric(value, errors="coerce")
        if pd.isna(clean_value):
            continue
        points.append([
            pd.Timestamp(frame.loc[index, "timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
            round(float(clean_value), 4),
        ])
    return {"name": name, "data": points}


def _summary_cpu_values(server: ServerReport) -> tuple[float | None, float | None]:
    frame = server.sections.get("CPU_ALL")
    if frame is None:
        return None, None
    busy = _cpu_busy_series(frame)
    return _mean_max(busy)


def _summary_memory_values(server: ServerReport) -> tuple[float | None, float | None]:
    return _mean_max(_memory_used_percent(_first_section(server, "MEM", "MEMNEW")))


def _summary_disk_busy_values(server: ServerReport) -> tuple[float | None, float | None]:
    frame = server.sections.get("DISKBUSY")
    if frame is None or frame.empty:
        return None, None
    columns = _numeric_columns(frame)
    if not columns:
        return None, None
    highest = frame[columns].apply(pd.to_numeric, errors="coerce").max(axis=1)
    return _mean_max(highest)


def _summary_network_values(server: ServerReport) -> tuple[float | None, float | None]:
    frame = server.sections.get("NET")
    pairs = _network_pairs(frame)
    if frame is None or frame.empty or not pairs:
        return None, None
    total = _network_total_mbps(frame, pairs)
    max_value = _series_max(total)
    return max_value, max_value


def _mean_max(values: pd.Series | None) -> tuple[float | None, float | None]:
    if not _has_values(values):
        return None, None
    clean = values.dropna()
    return float(clean.mean()), float(clean.max())


def _max_abs(series: dict[str, pd.Series]) -> float:
    values = []
    for item in series.values():
        clean = pd.to_numeric(item, errors="coerce").dropna()
        if not clean.empty:
            values.append(float(clean.abs().max()))
    if not values:
        return 0.0
    return max(values) * 1.08


def _cpu_busy_series(frame: pd.DataFrame) -> pd.Series:
    busy_column = _find_column(frame, "Busy", "CPU Busy%", "Busy%")
    if busy_column:
        busy = _numeric(frame[busy_column])
        if _has_values(busy):
            return busy.clip(lower=0, upper=100)
    idle_column = _find_column(frame, "Idle%", "Idle")
    if idle_column:
        idle = _numeric(frame[idle_column])
        return (100.0 - idle).clip(lower=0, upper=100)
    columns = [column for column in ("User%", "Sys%", "Wait%") if column in frame]
    if columns:
        return frame[columns].apply(pd.to_numeric, errors="coerce").sum(axis=1).clip(lower=0, upper=100)
    return pd.Series(dtype="float64")


def _memory_used_percent(frame: pd.DataFrame | None) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    total_column = _find_column(frame, "memtotal", "Real total MB", "Memory total")
    free_column = _find_column(frame, "memfree", "Real free MB", "Memory free", "available")
    cached_column = _find_column(frame, "cached", "Cached")
    buffers_column = _find_column(frame, "buffers", "Buffers")
    if total_column and free_column:
        total = _numeric(frame[total_column])
        free = _numeric(frame[free_column])
        used = total - free
        if cached_column:
            used -= _numeric(frame[cached_column]).fillna(0)
        if buffers_column:
            used -= _numeric(frame[buffers_column]).fillna(0)
        return (used / total.replace(0, pd.NA) * 100.0).clip(lower=0, upper=100)
    used_column = _find_column(frame, "Memory Used%", "used%")
    if used_column:
        return _numeric(frame[used_column]).clip(lower=0, upper=100)
    return None


def _swap_used_percent(frame: pd.DataFrame | None) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    total_column = _find_column(frame, "swaptotal", "Virtual total MB", "Swap total")
    free_column = _find_column(frame, "swapfree", "Virtual free MB", "Swap free")
    if total_column and free_column:
        total = _numeric(frame[total_column])
        free = _numeric(frame[free_column])
        used = (total - free) / total.replace(0, pd.NA) * 100.0
        return used.fillna(0).clip(lower=0, upper=100)
    used_column = _find_column(frame, "Swap Used%", "swap used")
    if used_column:
        return _numeric(frame[used_column]).clip(lower=0, upper=100)
    return None


def _network_pairs(frame: pd.DataFrame | None) -> dict[str, tuple[str | None, str | None]]:
    if frame is None or frame.empty:
        return {}
    pairs: dict[str, tuple[str | None, str | None]] = {}
    for column in _numeric_columns(frame):
        lower = column.lower()
        if lower.endswith("-read-kb/s") or lower.endswith("_read-kb/s") or "read" in lower or "recv" in lower:
            iface = _iface_name(column, ("-read-kb/s", "_read-kb/s", "read", "recv", "receive", "in"))
            read, write = pairs.get(iface, (None, None))
            pairs[iface] = (column, write)
        elif lower.endswith("-write-kb/s") or lower.endswith("_write-kb/s") or "write" in lower or "send" in lower or "transmit" in lower:
            iface = _iface_name(column, ("-write-kb/s", "_write-kb/s", "write", "send", "transmit", "out"))
            read, write = pairs.get(iface, (None, None))
            pairs[iface] = (read, column)
    return pairs


def _top_network_interfaces(
    frame: pd.DataFrame,
    pairs: dict[str, tuple[str | None, str | None]],
    top_n: int,
) -> list[str]:
    ranked = []
    for iface, (read_column, write_column) in pairs.items():
        read = _numeric(frame[read_column]) if read_column else pd.Series(0, index=frame.index)
        write = _numeric(frame[write_column]) if write_column else pd.Series(0, index=frame.index)
        total = read.fillna(0) + write.fillna(0)
        if _has_values(total):
            ranked.append((iface, float(total.max())))
    return [iface for iface, _ in sorted(ranked, key=lambda item: item[1], reverse=True)[:top_n]]


def _network_total_mbps(frame: pd.DataFrame, pairs: dict[str, tuple[str | None, str | None]]) -> pd.Series:
    total = pd.Series(0.0, index=frame.index)
    for read_column, write_column in pairs.values():
        if read_column:
            total += _numeric(frame[read_column]).fillna(0)
        if write_column:
            total += _numeric(frame[write_column]).fillna(0)
    return total / 1024.0


def _top_numeric_columns(
    frame: pd.DataFrame,
    top_n: int,
    score: Callable[[pd.Series], float],
) -> list[str]:
    ranked = []
    for column in _numeric_columns(frame):
        values = _numeric(frame[column]).dropna()
        if values.empty:
            continue
        ranked.append((column, float(score(values))))
    return [column for column, _ in sorted(ranked, key=lambda item: item[1], reverse=True)[:top_n]]


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [
        column
        for column in frame.columns
        if column not in {"timestamp", "timestamp_id", "source_line"}
        and pd.api.types.is_numeric_dtype(frame[column])
    ]


def _numeric(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce")


def _column_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(dtype="float64")
    return _numeric(frame[column]).clip(lower=0, upper=100)


def _has_values(values: pd.Series | None) -> bool:
    return values is not None and not values.dropna().empty


def _series_max(values: pd.Series | None) -> float | None:
    if not _has_values(values):
        return None
    return float(values.dropna().max())


def _first_section(server: ServerReport, *names: str) -> pd.DataFrame | None:
    for name in names:
        frame = server.sections.get(name)
        if frame is not None and not frame.empty:
            return frame
    return None


def _find_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    by_lower = {str(column).lower(): column for column in frame.columns}
    for candidate in candidates:
        found = by_lower.get(candidate.lower())
        if found is not None:
            return str(found)
    for candidate in candidates:
        needle = candidate.lower()
        for column in frame.columns:
            if needle in str(column).lower():
                return str(column)
    return None


def _iface_name(column: str, tokens: tuple[str, ...]) -> str:
    name = column
    lower = column.lower()
    for token in tokens:
        if lower.endswith(token):
            return name[: -len(token)].strip("-_ ")
    for token in tokens:
        pattern = re.compile(re.escape(token), re.IGNORECASE)
        name = pattern.sub("", name)
    return name.strip("-_ ") or column


def _title(server: ServerReport, metric_type: str) -> str:
    return f"【{server.host}】{metric_type}（{_time_range(server)}）"


def _time_range(server: ServerReport) -> str:
    stamps = []
    for frame in server.sections.values():
        if "timestamp" not in frame or frame.empty:
            continue
        stamps.append(pd.to_datetime(frame["timestamp"], errors="coerce").dropna())
    if not stamps:
        return "-"
    merged = pd.concat(stamps)
    return f"{merged.min():%Y-%m-%d %H:%M:%S} ~ {merged.max():%Y-%m-%d %H:%M:%S}"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower() or "server"
