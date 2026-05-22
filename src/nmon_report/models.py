from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MetricInfo:
    section: str
    theme: str
    title: str
    unit: str = ""


@dataclass
class NmonFile:
    path: Path
    host: str
    metadata: dict[str, str]
    timestamps: dict[str, pd.Timestamp]
    sections: dict[str, pd.DataFrame]
    section_headers: dict[str, list[str]]
    warnings: list[str] = field(default_factory=list)

    @property
    def discovered_sections(self) -> list[str]:
        return sorted(self.sections)


@dataclass
class ServerReport:
    host: str
    path: Path
    metadata: dict[str, str]
    sections: dict[str, pd.DataFrame]
    metrics: dict[str, list[MetricInfo]]
    summaries: list[dict[str, Any]]
    images: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReportResult:
    output_dir: Path
    html_path: Path
    docx_path: Path
    image_dir: Path
    summary_images: list[dict[str, str]]
    servers: list[ServerReport]
    failures: list[dict[str, str]]
    discovered_sections: dict[str, list[str]]
    selected_metrics: list[str]
