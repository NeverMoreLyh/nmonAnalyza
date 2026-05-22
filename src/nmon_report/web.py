from __future__ import annotations

import argparse
from html import escape

from flask import Flask, request

from .metrics import FRIENDLY_THEMES
from .report import generate_report


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return _page()

    @app.post("/generate")
    def generate() -> str:
        input_dir = request.form.get("input_dir", "").strip()
        output_dir = request.form.get("output_dir", "").strip()
        start = request.form.get("start", "").strip() or None
        end = request.form.get("end", "").strip() or None
        selected_metrics = request.form.getlist("metrics")
        metrics_text = request.form.get("metrics_text", "").strip()
        metrics = ",".join(selected_metrics + ([metrics_text] if metrics_text else []))
        top_n = int(request.form.get("top_n", "5").strip() or "5")
        bandwidth_text = request.form.get("network_bandwidth_mbps", "").strip()
        network_bandwidth_mbps = float(bandwidth_text) if bandwidth_text else None
        try:
            result = generate_report(
                input_dir,
                start,
                end,
                metrics,
                output_dir,
                top_n=top_n,
                network_bandwidth_mbps=network_bandwidth_mbps,
            )
            message = (
                f"<p>报告已生成：<code>{escape(str(result.html_path))}</code></p>"
                f"<p>Word文档：<code>{escape(str(result.docx_path))}</code></p>"
                f"<p>图片目录：<code>{escape(str(result.image_dir))}</code></p>"
                f"<p>成功服务器：{len(result.servers)}，失败文件：{len(result.failures)}</p>"
            )
            return _page(message)
        except Exception as exc:  # noqa: BLE001 - Web UI should show actionable local errors.
            return _page(f'<p class="error">生成失败：{escape(str(exc))}</p>'), 400

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the nmon report web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5000, type=int)
    args = parser.parse_args(argv)
    create_app().run(host=args.host, port=args.port, debug=False)
    return 0


def _page(message: str = "") -> str:
    checkboxes = "".join(
        f'<label><input type="checkbox" name="metrics" value="{theme}" {"checked" if theme in {"cpu", "memory", "disk", "network"} else ""}> {theme}</label>'
        for theme in FRIENDLY_THEMES
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>nmon Report Generator</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f7f8fa; color: #20242a; }}
    main {{ max-width: 880px; margin: 0 auto; padding: 32px; }}
    form {{ background: white; border: 1px solid #dde2e8; border-radius: 8px; padding: 20px; }}
    label {{ display: block; margin: 12px 0 6px; font-weight: 600; }}
    input[type="text"] {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #c8d0da; border-radius: 6px; }}
    .checks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 6px; margin: 8px 0; }}
    .checks label {{ font-weight: 400; margin: 0; }}
    button {{ margin-top: 16px; padding: 10px 16px; border: 0; border-radius: 6px; background: #243447; color: white; cursor: pointer; }}
    code {{ background: #eef2f6; padding: 2px 5px; border-radius: 4px; }}
    .message {{ margin-bottom: 16px; padding: 12px; background: white; border: 1px solid #dde2e8; border-radius: 8px; }}
    .error {{ color: #a52323; }}
  </style>
</head>
<body>
  <main>
    <h1>nmon Report Generator</h1>
    <div class="message">{message or "输入 nmon 目录、时间段和指标主题后生成 HTML 报告、Word 文档与 PNG 截图。"}</div>
    <form method="post" action="/generate">
      <label for="input_dir">nmon 文件目录</label>
      <input id="input_dir" name="input_dir" type="text" placeholder="/path/to/nmon-files" required>

      <label for="start">开始时间</label>
      <input id="start" name="start" type="text" placeholder="2026-05-21 10:00:00">

      <label for="end">结束时间</label>
      <input id="end" name="end" type="text" placeholder="2026-05-21 11:00:00">

      <label>指标主题</label>
      <div class="checks">{checkboxes}</div>

      <label for="metrics_text">额外原始 section 或 all</label>
      <input id="metrics_text" name="metrics_text" type="text" placeholder="例如 CPU_ALL,DISKBUSY 或 all">

      <label for="top_n">磁盘/网络 Top N</label>
      <input id="top_n" name="top_n" type="text" value="5">

      <label for="network_bandwidth_mbps">网络带宽 Mbps（可选）</label>
      <input id="network_bandwidth_mbps" name="network_bandwidth_mbps" type="text" placeholder="例如 1000">

      <label for="output_dir">输出目录</label>
      <input id="output_dir" name="output_dir" type="text" placeholder="/path/to/report-output" required>

      <button type="submit">生成报告</button>
    </form>
  </main>
</body>
</html>
"""
