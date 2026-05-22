from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .analyzer import build_server_overview, build_server_overview_payload, load_servers
from .charts import build_interactive_chart_specs, generate_charts
from .models import ReportResult, ServerReport
from .word import generate_word_report


def generate_report(
    input_dir: str | Path,
    start: str | None,
    end: str | None,
    metrics: str | list[str] | None,
    output_dir: str | Path,
    top_n: int = 5,
    network_bandwidth_mbps: float | None = None,
) -> ReportResult:
    output = Path(output_dir)
    image_dir = output / "images"
    output.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    _clear_generated_images(image_dir)

    servers, failures, discovered, selected = load_servers(input_dir, start, end, metrics)
    summary_images = generate_charts(
        servers,
        image_dir,
        top_n=top_n,
        network_bandwidth_mbps=network_bandwidth_mbps,
    )
    docx_path = output / "resource-report.docx"
    generate_word_report(servers, docx_path, start, end)

    html_path = output / "report.html"
    html_path.write_text(
        render_html(
            input_dir=Path(input_dir),
            start=start,
            end=end,
            selected=selected,
            servers=servers,
            failures=failures,
            docx_path=docx_path.name,
            top_n=top_n,
            network_bandwidth_mbps=network_bandwidth_mbps,
        ),
        encoding="utf-8",
    )
    return ReportResult(
        output_dir=output,
        html_path=html_path,
        docx_path=docx_path,
        image_dir=image_dir,
        summary_images=summary_images,
        servers=servers,
        failures=failures,
        discovered_sections=discovered,
        selected_metrics=selected,
    )


def _clear_generated_images(image_dir: Path) -> None:
    for image in image_dir.rglob("*.png"):
        image.unlink()


def render_html(
    input_dir: Path,
    start: str | None,
    end: str | None,
    selected: list[str],
    servers: list[ServerReport],
    failures: list[dict[str, str]],
    docx_path: str,
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>nmon Resource Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #20242a; background: #f7f8fa; }}
    header {{ background: #243447; color: white; padding: 24px 32px; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 24px 32px 48px; }}
    section {{ background: white; border: 1px solid #dde2e8; border-radius: 8px; padding: 18px; margin-bottom: 18px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f6; }}
    .table-scroll {{ overflow-x: auto; }}
    .overview-table {{ min-width: 1120px; }}
    .overview-table th, .overview-table td {{ white-space: nowrap; }}
    .summary-controls {{ display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 8px 0 14px; }}
    .summary-controls label {{ display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #66717f; }}
    .summary-controls input {{ padding: 7px 9px; border: 1px solid #c8d0da; border-radius: 6px; color: #20242a; }}
    .summary-controls button {{ border: 1px solid #243447; background: #243447; color: white; border-radius: 6px; padding: 8px 12px; cursor: pointer; }}
    .summary-controls button#summary-reset {{ background: #fff; color: #243447; }}
    #summary-range-label {{ padding-bottom: 8px; }}
    code {{ background: #eef2f6; padding: 2px 5px; border-radius: 4px; }}
    img {{ max-width: 100%; border: 1px solid #d8dee6; border-radius: 6px; margin: 8px 0 16px; }}
    details {{ margin: 8px 0 18px; }}
    summary {{ cursor: pointer; color: #243447; font-weight: 600; }}
    .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 14px; align-items: start; }}
    .chart-card {{ border: 1px solid #d8dee6; border-radius: 6px; padding: 12px; background: #fff; }}
    .chart-card h3 {{ font-size: 15px; margin-bottom: 8px; }}
    .chart-card .echart {{ width: 100%; height: 430px; }}
    .chart-card.has-echart img.chart-image {{ display: none; }}
    .chart-card.has-echart.no-echarts img.chart-image {{ display: block; }}
    .chart-card.has-echart.no-echarts .echart {{ display: none; }}
    .resource-tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }}
    .resource-tabs button {{ border: 1px solid #c8d0da; background: #f7f8fa; color: #243447; border-radius: 6px; padding: 7px 12px; cursor: pointer; }}
    .resource-tabs button.active {{ background: #243447; color: white; border-color: #243447; }}
    .chart-card[hidden] {{ display: none; }}
    select {{ padding: 8px 10px; border: 1px solid #c8d0da; border-radius: 6px; min-width: 220px; }}
    .actions {{ margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; }}
    .button {{ display: inline-block; padding: 9px 14px; border-radius: 6px; background: #243447; color: white; text-decoration: none; }}
    .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    .warning {{ color: #8a5a00; }}
    .failure {{ color: #a52323; }}
    .muted {{ color: #66717f; }}
    .server-panel[hidden] {{ display: none; }}
    .copy-menu {{ position: fixed; display: none; z-index: 1000; background: white; border: 1px solid #c8d0da; border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,0.14); padding: 6px; }}
    .copy-menu button {{ border: 0; background: #243447; color: white; border-radius: 5px; padding: 8px 12px; cursor: pointer; }}
    .copy-status {{ position: fixed; right: 20px; bottom: 20px; display: none; background: #243447; color: white; padding: 10px 14px; border-radius: 6px; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head>
<body>
  <header>
    <h1>nmon Resource Report</h1>
    <div>Generated resource summary and chart screenshots</div>
  </header>
  <main>
    <section>
      <h2>运行信息</h2>
      <div class="meta">
        <div><strong>输入目录</strong><br><code>{escape(str(input_dir))}</code></div>
        <div><strong>时间范围</strong><br>{escape(start or "文件全部时间")} ~ {escape(end or "文件全部时间")}</div>
        <div><strong>选择指标</strong><br>{escape(", ".join(selected))}</div>
        <div><strong>成功/失败文件</strong><br>{len(servers)} / {len(failures)}</div>
      </div>
      <div class="actions"><a class="button" href="{escape(docx_path)}">一键生成Word文档</a></div>
    </section>
    {render_failures(failures)}
    {render_overall(servers)}
    {render_servers(servers, top_n, network_bandwidth_mbps)}
  </main>
  <div id="copy-menu" class="copy-menu"><button type="button" id="copy-image-button">复制图片</button></div>
  <div id="copy-status" class="copy-status"></div>
  <script>
    const serverSelect = document.getElementById("server-select");
    const overviewData = {json.dumps(build_server_overview_payload(servers), ensure_ascii=False)};
    let currentSummaryRange = getOverviewExtent();

    if (serverSelect) {{
      serverSelect.addEventListener("change", () => {{
        document.querySelectorAll(".server-panel").forEach((panel) => {{
          panel.hidden = panel.dataset.server !== serverSelect.value;
        }});
        resizeVisibleCharts();
      }});
    }}

    let selectedImage = null;
    let selectedChartUrl = null;
    const menu = document.getElementById("copy-menu");
    const statusBox = document.getElementById("copy-status");
    document.querySelectorAll("img.chart-image").forEach((image) => {{
      image.addEventListener("contextmenu", (event) => {{
        event.preventDefault();
        selectedImage = image;
        selectedChartUrl = null;
        menu.style.left = `${{event.clientX}}px`;
        menu.style.top = `${{event.clientY}}px`;
        menu.style.display = "block";
      }});
    }});
    document.addEventListener("click", () => {{
      menu.style.display = "none";
    }});
    document.getElementById("copy-image-button").addEventListener("click", async () => {{
      try {{
        if (!selectedImage && !selectedChartUrl) return;
        const response = await fetch(selectedChartUrl || selectedImage.src);
        const blob = await response.blob();
        await navigator.clipboard.write([new ClipboardItem({{ [blob.type]: blob }})]);
        showCopyStatus("图片已复制");
      }} catch (error) {{
        showCopyStatus("浏览器不允许直接复制，请使用默认图片菜单");
      }}
    }});
    function showCopyStatus(message) {{
      statusBox.textContent = message;
      statusBox.style.display = "block";
      setTimeout(() => {{ statusBox.style.display = "none"; }}, 1800);
    }}

    const summaryStartInput = document.getElementById("summary-start");
    const summaryEndInput = document.getElementById("summary-end");
    const summaryApplyButton = document.getElementById("summary-apply");
    const summaryResetButton = document.getElementById("summary-reset");
    if (summaryApplyButton) {{
      summaryApplyButton.addEventListener("click", () => {{
        const startMs = parseInputMillis(summaryStartInput.value);
        const endMs = parseInputMillis(summaryEndInput.value);
        updateOverviewTable(startMs, endMs, true);
      }});
    }}
    if (summaryResetButton) {{
      summaryResetButton.addEventListener("click", () => {{
        const extent = getOverviewExtent();
        updateOverviewTable(extent.start, extent.end, true);
      }});
    }}

    const chartInstances = [];
    function initEcharts() {{
      document.querySelectorAll(".resource-tabs").forEach((tabs) => {{
        tabs.addEventListener("click", (event) => {{
          const button = event.target.closest("button[data-theme]");
          if (!button) return;
          const panel = button.closest(".server-panel");
          panel.querySelectorAll(".resource-tabs button").forEach((item) => item.classList.toggle("active", item === button));
          panel.querySelectorAll(".chart-card[data-theme]").forEach((card) => {{
            card.hidden = card.dataset.theme !== button.dataset.theme;
          }});
          resizeVisibleCharts();
        }});
      }});
      document.querySelectorAll(".chart-card").forEach((card) => {{
        const container = card.querySelector(".echart");
        if (!container) return;
        if (!window.echarts) {{
          card.classList.add("no-echarts");
          return;
        }}
        const spec = JSON.parse(container.dataset.spec || "{{}}");
        const chart = echarts.init(container, null, {{ renderer: "canvas" }});
        chart.setOption(buildEchartOption(spec));
        chart.on("dataZoom", () => {{
          const range = getChartZoomRange(chart, spec);
          if (range) {{
            updateOverviewTable(range.start, range.end, true);
          }}
        }});
        container.addEventListener("contextmenu", (event) => {{
          event.preventDefault();
          selectedImage = null;
          selectedChartUrl = chart.getDataURL({{ type: "png", pixelRatio: 2, backgroundColor: "#fff" }});
          menu.style.left = `${{event.clientX}}px`;
          menu.style.top = `${{event.clientY}}px`;
          menu.style.display = "block";
        }});
        chartInstances.push(chart);
      }});
      window.addEventListener("resize", () => chartInstances.forEach((chart) => chart.resize()));
    }}
    function resizeVisibleCharts() {{
      setTimeout(() => {{
        chartInstances.forEach((chart) => {{
          const element = chart.getDom();
          if (element && element.offsetParent !== null) {{
            chart.resize();
          }}
        }});
      }}, 30);
    }}
    function buildEchartOption(spec) {{
      return {{
        animation: false,
        color: ["#2f7ed8", "#d94e5d", "#31a354", "#9467bd", "#ff7f0e", "#17becf", "#bcbd22", "#8c564b", "#e377c2", "#7f7f7f"],
        title: {{ text: spec.title || "", left: "center", top: 4, textStyle: {{ fontSize: 15, fontWeight: 600 }} }},
        tooltip: {{ trigger: "axis", axisPointer: {{ type: "cross" }}, valueFormatter: (value) => `${{(spec.signed_mirror ? Math.abs(Number(value)) : Number(value)).toFixed(2)}} ${{spec.unit || ""}}` }},
        legend: {{ type: "scroll", top: 36, left: 18, right: 18 }},
        grid: {{ top: 88, left: 72, right: 36, bottom: 82 }},
        toolbox: {{
          right: 18,
          feature: {{
            dataZoom: {{ yAxisIndex: "none" }},
            restore: {{}},
            saveAsImage: {{ title: "保存图片", pixelRatio: 2 }}
          }}
        }},
        dataZoom: [
          {{ type: "inside", xAxisIndex: 0, filterMode: "none" }},
          {{ type: "slider", xAxisIndex: 0, bottom: 28, height: 22 }}
        ],
        xAxis: {{ type: "time", name: "采样时间", axisLabel: {{ formatter: "{{yyyy}}-{{MM}}-{{dd}}\\n{{HH}}:{{mm}}:{{ss}}" }} }},
        yAxis: {{
          type: "value",
          name: spec.unit || "Value",
          min: spec.percent ? 0 : (spec.signed_mirror ? -Math.max(Number(spec.max_abs || 0), 1) : null),
          max: spec.percent ? 100 : (spec.signed_mirror ? Math.max(Number(spec.max_abs || 0), 1) : null),
          scale: !spec.percent && !spec.signed_mirror,
          axisLabel: {{ formatter: (value) => spec.signed_mirror ? Math.abs(Number(value)).toFixed(0) : value }}
        }},
        series: (spec.series || []).map((item) => ({{
          name: item.name,
          type: "line",
          showSymbol: false,
          sampling: "lttb",
          smooth: false,
          stack: spec.chart_type === "stacked-area" && item.name !== "CPU Busy%" ? "CPU使用组成" : null,
          areaStyle: spec.chart_type === "stacked-area" && item.name !== "CPU Busy%" ? {{ opacity: 0.72 }} : null,
          lineStyle: item.name === "CPU Busy%" ? {{ width: 2.2, type: "solid" }} : {{ width: 1.2 }},
          z: item.name === "CPU Busy%" ? 3 : 2,
          emphasis: {{ focus: "series" }},
          data: item.data || []
        }}))
      }};
    }}
    function getOverviewExtent() {{
      const times = [];
      overviewData.forEach((row) => {{
        Object.values(row.metrics || {{}}).forEach((points) => {{
          (points || []).forEach((point) => {{
            const time = parseMillis(point[0]);
            if (Number.isFinite(time)) times.push(time);
          }});
        }});
      }});
      if (!times.length) return {{ start: null, end: null }};
      return {{ start: Math.min(...times), end: Math.max(...times) }};
    }}
    function getChartZoomRange(chart, spec) {{
      const extent = getSpecExtent(spec);
      if (!extent) return null;
      const option = chart.getOption();
      const zoom = (option.dataZoom || []).find((item) => item.xAxisIndex === 0 || item.xAxisIndex?.[0] === 0) || (option.dataZoom || [])[0];
      if (!zoom) return extent;
      let start = parseZoomValue(zoom.startValue);
      let end = parseZoomValue(zoom.endValue);
      if (!Number.isFinite(start) || !Number.isFinite(end)) {{
        const startPercent = Number.isFinite(Number(zoom.start)) ? Number(zoom.start) : 0;
        const endPercent = Number.isFinite(Number(zoom.end)) ? Number(zoom.end) : 100;
        start = extent.start + (extent.end - extent.start) * startPercent / 100;
        end = extent.start + (extent.end - extent.start) * endPercent / 100;
      }}
      return {{ start: Math.min(start, end), end: Math.max(start, end) }};
    }}
    function getSpecExtent(spec) {{
      const times = [];
      (spec.series || []).forEach((item) => {{
        (item.data || []).forEach((point) => {{
          const time = parseMillis(point[0]);
          if (Number.isFinite(time)) times.push(time);
        }});
      }});
      if (!times.length) return null;
      return {{ start: Math.min(...times), end: Math.max(...times) }};
    }}
    function updateOverviewTable(startMs, endMs, updateInputs) {{
      const body = document.getElementById("overview-body");
      const rangeLabel = document.getElementById("summary-range-label");
      if (!body) return;
      const extent = getOverviewExtent();
      const cleanStart = Number.isFinite(Number(startMs)) ? Number(startMs) : extent.start;
      const cleanEnd = Number.isFinite(Number(endMs)) ? Number(endMs) : extent.end;
      currentSummaryRange = {{ start: cleanStart, end: cleanEnd }};
      if (updateInputs) {{
        if (summaryStartInput) summaryStartInput.value = formatDateTimeLocal(cleanStart);
        if (summaryEndInput) summaryEndInput.value = formatDateTimeLocal(cleanEnd);
      }}
      if (rangeLabel) {{
        rangeLabel.textContent = cleanStart && cleanEnd
          ? `${{formatDisplayTime(cleanStart)}} ~ ${{formatDisplayTime(cleanEnd)}}`
          : "全部时间";
      }}
      const rows = overviewData.map((row) => overviewRowHtml(row, cleanStart, cleanEnd)).join("");
      body.innerHTML = rows || '<tr><td colspan="11" class="muted">没有可展示的数据。</td></tr>';
    }}
    function overviewRowHtml(row, startMs, endMs) {{
      const metrics = row.metrics || {{}};
      return `<tr>
        <td>${{escapeHtml(row.file_name || "-")}}</td>
        <td>${{escapeHtml(row.ip_address || "-")}}</td>
        <td>${{formatPercent(maxPointValue(metrics.cpu_usage, startMs, endMs))}}</td>
        <td>${{formatPercent(maxPointValue(metrics.memory_usage, startMs, endMs))}}</td>
        <td>${{formatPercent(maxPointValue(metrics.swap_usage, startMs, endMs))}}</td>
        <td>${{formatNumber(maxPointValue(metrics.disk_read, startMs, endMs))}}</td>
        <td>${{formatNumber(maxPointValue(metrics.disk_write, startMs, endMs))}}</td>
        <td>${{formatNumber(maxPointValue(metrics.network_read, startMs, endMs))}}</td>
        <td>${{formatNumber(maxPointValue(metrics.network_write, startMs, endMs))}}</td>
        <td>${{escapeHtml(row.system_type || "-")}}</td>
        <td>${{escapeHtml(readRange(row.range_points || [], startMs, endMs))}}</td>
      </tr>`;
    }}
    function maxPointValue(points, startMs, endMs) {{
      const values = (points || [])
        .filter((point) => withinRange(parseMillis(point[0]), startMs, endMs))
        .map((point) => Number(point[1]))
        .filter((value) => Number.isFinite(value));
      if (!values.length) return null;
      return Math.max(...values);
    }}
    function readRange(points, startMs, endMs) {{
      const lines = (points || [])
        .filter((point) => withinRange(parseMillis(point[0]), startMs, endMs))
        .map((point) => Number(point[1]))
        .filter((value) => Number.isFinite(value));
      if (!lines.length) return "-";
      return `${{Math.min(...lines)}}-${{Math.max(...lines)}}`;
    }}
    function withinRange(value, startMs, endMs) {{
      if (!Number.isFinite(value)) return false;
      if (Number.isFinite(Number(startMs)) && value < Number(startMs)) return false;
      if (Number.isFinite(Number(endMs)) && value > Number(endMs)) return false;
      return true;
    }}
    function parseMillis(value) {{
      if (value === null || value === undefined || value === "") return NaN;
      if (typeof value === "number") return value;
      const text = String(value).includes("T") ? String(value) : String(value).replace(" ", "T");
      const parsed = Date.parse(text);
      return Number.isFinite(parsed) ? parsed : NaN;
    }}
    function parseZoomValue(value) {{
      if (value === null || value === undefined || value === "") return NaN;
      const asNumber = Number(value);
      if (Number.isFinite(asNumber)) return asNumber;
      return parseMillis(value);
    }}
    function parseInputMillis(value) {{
      return parseMillis(value);
    }}
    function formatDateTimeLocal(value) {{
      if (!Number.isFinite(Number(value))) return "";
      const date = new Date(Number(value));
      const pad = (item) => String(item).padStart(2, "0");
      return `${{date.getFullYear()}}-${{pad(date.getMonth() + 1)}}-${{pad(date.getDate())}}T${{pad(date.getHours())}}:${{pad(date.getMinutes())}}:${{pad(date.getSeconds())}}`;
    }}
    function formatDisplayTime(value) {{
      return formatDateTimeLocal(value).replace("T", " ");
    }}
    function formatPercent(value) {{
      return value === null || value === undefined ? "-" : `${{Number(value).toFixed(2)}}%`;
    }}
    function formatNumber(value) {{
      return value === null || value === undefined ? "-" : Number(value).toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }}
    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}
    initEcharts();
    updateOverviewTable(currentSummaryRange.start, currentSummaryRange.end, true);
  </script>
</body>
</html>
"""


def render_failures(failures: list[dict[str, str]]) -> str:
    if not failures:
        return ""
    rows = "".join(
        f"<tr><td><code>{escape(item['path'])}</code></td><td class=\"failure\">{escape(item['error'])}</td></tr>"
        for item in failures
    )
    return f"<section><h2>解析失败文件</h2><table><tr><th>文件</th><th>原因</th></tr>{rows}</table></section>"


def render_overall(servers: list[ServerReport]) -> str:
    return f"""
    <section>
      <h2>整体汇总</h2>
      <div class="summary-controls">
        <label>开始时间 <input id="summary-start" type="datetime-local" step="1"></label>
        <label>结束时间 <input id="summary-end" type="datetime-local" step="1"></label>
        <button type="button" id="summary-apply">按范围计算</button>
        <button type="button" id="summary-reset">全部时间</button>
        <span id="summary-range-label" class="muted"></span>
      </div>
      {render_server_overview_table(build_server_overview(servers))}
    </section>
    """


def render_server_overview_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return '<p class="muted">没有可展示的数据。</p>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{escape(row['file_name'])}</td>"
            f"<td>{escape(row['ip_address'])}</td>"
            f"<td>{escape(row['cpu_usage'])}</td>"
            f"<td>{escape(row['memory_usage'])}</td>"
            f"<td>{escape(row['swap_usage'])}</td>"
            f"<td>{escape(row['disk_read'])}</td>"
            f"<td>{escape(row['disk_write'])}</td>"
            f"<td>{escape(row['network_read'])}</td>"
            f"<td>{escape(row['network_write'])}</td>"
            f"<td>{escape(row['system_type'])}</td>"
            f"<td>{escape(row['read_range'])}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table id="overview-table" class="overview-table"><thead><tr>'
        "<th>文件名</th><th>IP地址</th><th>CPU使用率</th><th>内存使用率</th>"
        "<th>SWAP使用率</th><th>磁盘读速率<br>(KB/s)</th><th>磁盘写速率<br>(KB/s)</th>"
        "<th>网络读速率<br>(KB/s)</th><th>网络写速率<br>(KB/s)</th><th>系统类型</th><th>读取范围</th>"
        f'</tr></thead><tbody id="overview-body">{"".join(body)}</tbody></table></div>'
    )


def render_servers(
    servers: list[ServerReport],
    top_n: int,
    network_bandwidth_mbps: float | None,
) -> str:
    if not servers:
        return ""
    options = "".join(
        f'<option value="{escape(server.host)}">{escape(server.host)} - {escape(server.path.name)}</option>'
        for server in servers
    )
    panels = "".join(
        render_server(server, top_n, network_bandwidth_mbps, hidden=index != 0)
        for index, server in enumerate(servers)
    )
    return f"""
    <section>
      <h2>服务器明细</h2>
      <label for="server-select">选择服务器</label>
      <select id="server-select">{options}</select>
    </section>
    {panels}
    """


def render_server(
    server: ServerReport,
    top_n: int,
    network_bandwidth_mbps: float | None,
    hidden: bool = False,
) -> str:
    warnings = ""
    if server.warnings:
        warnings = "<ul>" + "".join(f"<li class=\"warning\">{escape(item)}</li>" for item in server.warnings) + "</ul>"
    charts = build_interactive_chart_specs(server, top_n=top_n, network_bandwidth_mbps=network_bandwidth_mbps)
    image_by_name = {image["name"]: image for image in server.images}
    tabs = render_resource_tabs(charts)
    first_theme = str(charts[0]["theme"]) if charts else ""
    cards = "".join(
        render_echart_card(chart, image_by_name.get(str(chart["name"])), hidden=str(chart["theme"]) != first_theme)
        for chart in charts
    )
    if not cards:
        cards = '<p class="muted">没有可展示的图表。</p>'
    hidden_attr = " hidden" if hidden else ""
    return f"""
    <section class="server-panel" data-server="{escape(server.host)}"{hidden_attr}>
      <h2>{escape(server.host)}</h2>
      <div class="muted"><code>{escape(str(server.path))}</code></div>
      {warnings}
      {tabs}
      <div class="chart-grid">{cards}</div>
    </section>
    """


def render_resource_tabs(charts: list[dict[str, object]]) -> str:
    themes = []
    for chart in charts:
        theme = str(chart["theme"])
        if theme not in themes:
            themes.append(theme)
    if len(themes) <= 1:
        return ""
    labels = {
        "cpu": "CPU",
        "memory": "内存",
        "disk": "磁盘",
        "network": "网络",
    }
    buttons = "".join(
        f'<button type="button" class="{"active" if index == 0 else ""}" data-theme="{escape(theme)}">{escape(labels.get(theme, theme))}</button>'
        for index, theme in enumerate(themes)
    )
    return f'<div class="resource-tabs">{buttons}</div>'


def render_echart_card(chart: dict[str, object], image: dict[str, str] | None, hidden: bool = False) -> str:
    spec = escape(json.dumps(chart, ensure_ascii=False), quote=True)
    theme = escape(str(chart["theme"]))
    title = escape(str(chart["title"]))
    png = ""
    if image:
        png = f'<img class="chart-image" src="{escape(image["relative_path"])}" alt="{title}">'
    hidden_attr = " hidden" if hidden else ""
    return (
        f'<div class="chart-card has-echart" data-theme="{theme}"{hidden_attr}>'
        f"<h3>{title}</h3>"
        f'<div class="echart" data-spec="{spec}"></div>'
        f"{png}"
        "</div>"
    )
