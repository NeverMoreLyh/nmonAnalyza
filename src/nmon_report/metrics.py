from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch

from .models import MetricInfo


@dataclass(frozen=True)
class MetricRule:
    pattern: str
    theme: str
    title: str
    unit: str = ""


METRIC_RULES: tuple[MetricRule, ...] = (
    MetricRule("CPU_ALL", "cpu", "CPU overall", "%"),
    MetricRule("CPU*", "cpu", "CPU cores", "%"),
    MetricRule("TPS*", "tps", "TPS", "tps"),
    MetricRule("TPM*", "tps", "Transactions", ""),
    MetricRule("MEM", "memory", "Memory", "MB"),
    MetricRule("MEMNEW", "memory", "Memory", "MB"),
    MetricRule("VM", "memory", "Virtual memory", ""),
    MetricRule("PAGE", "memory", "Paging", ""),
    MetricRule("DISKBUSY", "disk", "Disk busy", "%"),
    MetricRule("DISKREAD", "disk", "Disk read", "KB/s"),
    MetricRule("DISKWRITE", "disk", "Disk write", "KB/s"),
    MetricRule("DISKXFER", "disk", "Disk transfers", "ops/s"),
    MetricRule("DISKBSIZE", "disk", "Disk block size", "KB"),
    MetricRule("DISKSERV", "disk", "Disk service time", "ms"),
    MetricRule("DISKWAIT", "disk", "Disk wait time", "ms"),
    MetricRule("NET", "network", "Network throughput", "KB/s"),
    MetricRule("NETPACKET", "network", "Network packets", "packets/s"),
    MetricRule("NETERROR", "network", "Network errors", ""),
    MetricRule("NETSIZE", "network", "Network packet size", "bytes"),
    MetricRule("JFSFILE", "filesystem", "Filesystem files", ""),
    MetricRule("JFSINODE", "filesystem", "Filesystem inodes", ""),
    MetricRule("JFS*", "jfs", "JFS", ""),
    MetricRule("FILE", "filesystem", "File table", ""),
    MetricRule("PROC", "process", "Processes", ""),
    MetricRule("TOP", "process", "Top processes", ""),
    MetricRule("UARG", "process", "Process arguments", ""),
    MetricRule("SYS", "system", "System", ""),
    MetricRule("RUNQUEUE", "system", "Run queue", ""),
    MetricRule("LARGEPAGE", "memory", "Large pages", ""),
    MetricRule("LPAR", "lpar", "LPAR", ""),
    MetricRule("WLM*", "lpar", "Workload manager", ""),
    MetricRule("SEA*", "adapter", "Shared ethernet adapter", ""),
    MetricRule("ENT*", "adapter", "Ethernet adapter", ""),
    MetricRule("FC*", "adapter", "Fibre channel adapter", ""),
)

FRIENDLY_THEMES: tuple[str, ...] = (
    "cpu",
    "tps",
    "memory",
    "disk",
    "network",
    "filesystem",
    "system",
    "process",
    "adapter",
    "jfs",
    "lpar",
    "unclassified",
)


def classify_section(section: str) -> MetricInfo:
    upper_section = section.upper()
    for rule in METRIC_RULES:
        if fnmatch(upper_section, rule.pattern):
            return MetricInfo(
                section=section,
                theme=rule.theme,
                title=rule.title,
                unit=rule.unit,
            )
    return MetricInfo(
        section=section,
        theme="unclassified",
        title=f"Unclassified {section}",
        unit="",
    )


def group_sections(sections: list[str]) -> dict[str, list[MetricInfo]]:
    grouped: dict[str, list[MetricInfo]] = {}
    for section in sorted(sections):
        info = classify_section(section)
        grouped.setdefault(info.theme, []).append(info)
    return grouped


def normalize_metric_selection(metrics: str | list[str] | None) -> list[str]:
    if metrics is None:
        return ["cpu", "memory", "disk", "network"]
    if isinstance(metrics, str):
        values = [part.strip().lower() for part in metrics.split(",") if part.strip()]
    else:
        values = [part.strip().lower() for part in metrics if part.strip()]
    return values or ["cpu", "memory", "disk", "network"]


def select_metrics(
    grouped: dict[str, list[MetricInfo]],
    selected: list[str],
) -> dict[str, list[MetricInfo]]:
    if "all" in selected:
        return grouped

    selected_set = set(selected)
    result: dict[str, list[MetricInfo]] = {}
    for theme, infos in grouped.items():
        direct_sections = [info for info in infos if info.section.lower() in selected_set]
        if theme in selected_set or direct_sections:
            result[theme] = infos if theme in selected_set else direct_sections
    return result
