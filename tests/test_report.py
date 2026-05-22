from pathlib import Path

from nmon_report.analyzer import build_server_overview, build_server_overview_payload, load_servers
from nmon_report.report import generate_report


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample"


def test_load_servers_filters_time_and_summarizes() -> None:
    servers, failures, discovered, selected = load_servers(
        SAMPLE,
        "2026-05-21 10:05:00",
        "2026-05-21 10:10:00",
        "cpu,memory,disk,network,filesystem,system",
    )

    assert not failures
    assert len(servers) == 2
    assert selected == ["cpu", "memory", "disk", "network", "filesystem", "system"]
    assert "CUSTOMX" in discovered["server-a"]
    assert all(summary["samples"] == 2 for summary in servers[0].summaries)

    overview = build_server_overview(servers)
    assert overview[0]["file_name"] == "server-a.nmon"
    assert overview[0]["ip_address"] == "172.21.186.37"
    assert overview[0]["cpu_usage"] == "60.00%"
    assert overview[0]["memory_usage"] == "75.00%"
    assert overview[0]["swap_usage"] == "60.94%"
    assert overview[0]["system_type"] == "Linux"
    assert overview[0]["read_range"] == "10-47"

    overview_payload = build_server_overview_payload(servers)
    server_a_payload = next(item for item in overview_payload if item["file_name"] == "server-a.nmon")
    assert server_a_payload["metrics"]["cpu_usage"] == [
        ["2026-05-21 10:05:00", 60.0],
        ["2026-05-21 10:10:00", 51.0],
    ]
    assert server_a_payload["metrics"]["memory_usage"] == [
        ["2026-05-21 10:05:00", 62.5],
        ["2026-05-21 10:10:00", 75.0],
    ]
    assert server_a_payload["range_points"]


def test_generate_report_creates_html_and_png(tmp_path: Path) -> None:
    result = generate_report(
        input_dir=SAMPLE,
        start="2026-05-21 10:00:00",
        end="2026-05-21 10:10:00",
        metrics="all",
        output_dir=tmp_path,
    )

    assert result.html_path.exists()
    assert result.docx_path.exists()
    assert (result.image_dir / "server-a" / "cpu_usage.png").exists()
    assert (result.image_dir / "server-a" / "cpu_usage.png").stat().st_size > 0
    assert (result.image_dir / "server-a" / "memory_usage_percent.png").exists()
    assert (result.image_dir / "server-a" / "disk_busy_top5.png").exists()
    assert (result.image_dir / "server-a" / "network_top5.png").exists()
    assert (result.image_dir / "summary_cpu_bar.png").exists()
    assert result.summary_images
    assert not (result.image_dir / "overall-top-peaks.png").exists()
    assert "CUSTOMX" in result.discovered_sections["server-a"]
    html = result.html_path.read_text(encoding="utf-8")
    assert "<th>CPU使用率</th>" in html
    assert "<td>server-a.nmon</td>" in html
    assert "<td>172.21.186.37</td>" in html
    assert 'href="resource-report.docx"' in html
    assert 'id="server-select"' in html
    assert 'id="copy-image-button"' in html
    assert "echarts.min.js" in html
    assert 'class="resource-tabs"' in html
    assert 'class="echart"' in html
    assert "dataZoom" in html
    assert "saveAsImage" in html
    assert 'id="summary-start"' in html
    assert 'id="summary-end"' in html
    assert 'id="overview-body"' in html
    assert "overviewData" in html
    assert "getChartZoomRange" in html
    assert "updateOverviewTable" in html
    assert "CPU Busy%" in html
    assert 'cpu_usage.png' in html
    assert 'memory_usage_percent.png' in html
    assert "2026-05-21 10:00:00" in html
    assert "CPU001:Busy" not in html
    assert "自动发现的 nmon section" not in html
    assert "跨服务器汇总图" not in html
    assert "summary_cpu_bar.png" not in html
    assert "指标明细" not in html


def test_generate_report_without_time_range_uses_all_data(tmp_path: Path) -> None:
    result = generate_report(
        input_dir=SAMPLE,
        start=None,
        end=None,
        metrics="cpu",
        output_dir=tmp_path,
    )

    html = result.html_path.read_text(encoding="utf-8")
    assert "文件全部时间 ~ 文件全部时间" in html
    server = next(item for item in result.servers if item.host == "server-a")
    cpu_busy = next(item for item in server.summaries if item["section"] == "CPU_ALL" and item["metric"] == "Busy")
    assert cpu_busy["samples"] == 3
