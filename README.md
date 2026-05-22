# nmon-report

`nmon-report` reads one or more `.nmon` files from a directory, filters the data by an absolute time range, and generates:

- `report.html`: a multi-server resource summary report.
- `resource-report.docx`: a Word report with the overview table and chart sections.
- `images/*.png`: chart screenshots that can be copied into a performance test report.

The parser keeps every nmon section it can read. A metric registry maps common sections into friendly report themes such as CPU, memory, disk, network, filesystem, system, process, adapter, JFS, and LPAR. Unknown sections are preserved and shown as unclassified metrics.

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## CLI

```bash
nmon-report \
  --input-dir ./sample \
  --start "2026-05-21 10:00:00" \
  --end "2026-05-21 10:10:00" \
  --metrics cpu,memory,disk,network,filesystem,system \
  --output ./report-output
```

Use `--metrics all` to include every discovered metric theme and unclassified section.

## Web UI

```bash
nmon-report-web --host 127.0.0.1 --port 5000
```

Open `http://127.0.0.1:5000`, enter the nmon directory, time range, metric themes, and output directory, then generate the report.

## Supported nmon data

The first version focuses on standard nmon text files with `ZZZZ` timestamp records. Common sections are grouped by theme, while unrecognized sections are still parsed and can be added to the registry later without changing the parser.
