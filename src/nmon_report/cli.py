from __future__ import annotations

import argparse
from pathlib import Path

from .metrics import FRIENDLY_THEMES
from .report import generate_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate nmon HTML reports and PNG charts.")
    parser.add_argument("--input-dir", required=True, help="Directory containing .nmon files.")
    parser.add_argument("--start", help='Start time, for example "2026-05-21 10:00:00".')
    parser.add_argument("--end", help='End time, for example "2026-05-21 11:00:00".')
    parser.add_argument(
        "--metrics",
        default="cpu,memory,disk,network",
        help=f"Comma-separated themes, raw sections, or all. Themes: {', '.join(FRIENDLY_THEMES)}.",
    )
    parser.add_argument("--output", required=True, help="Output directory for report.html and images.")
    parser.add_argument("--top-n", default=5, type=int, help="Top N disks/interfaces to draw for disk and network charts.")
    parser.add_argument(
        "--network-bandwidth-mbps",
        type=float,
        help="Optional network bandwidth in Mbps. When set, generate network_bandwidth_usage.png.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = generate_report(
        input_dir=Path(args.input_dir),
        start=args.start,
        end=args.end,
        metrics=args.metrics,
        output_dir=Path(args.output),
        top_n=args.top_n,
        network_bandwidth_mbps=args.network_bandwidth_mbps,
    )
    print(f"Report: {result.html_path}")
    print(f"Word: {result.docx_path}")
    print(f"Images: {result.image_dir}")
    print(f"Servers: {len(result.servers)}")
    if result.failures:
        print(f"Failures: {len(result.failures)}")
        for failure in result.failures:
            print(f"- {failure['path']}: {failure['error']}")
    return 0 if result.servers else 1


if __name__ == "__main__":
    raise SystemExit(main())
