const MONTHS = {
  jan: 0, january: 0,
  feb: 1, february: 1,
  mar: 2, march: 2,
  apr: 3, april: 3,
  may: 4,
  jun: 5, june: 5,
  jul: 6, july: 6,
  aug: 7, august: 7,
  sep: 8, sept: 8, september: 8,
  oct: 9, october: 9,
  nov: 10, november: 10,
  dec: 11, december: 11
};

const THEME_LABELS = {
  cpu: "CPU",
  memory: "内存",
  disk: "磁盘",
  network: "网络"
};

const DEFAULT_TOP_N = 5;

const state = {
  servers: [],
  charts: [],
  previewServers: [],
  summaryRange: { start: null, end: null },
  selectedImageUrl: null
};

const els = {
  files: document.getElementById("nmon-files"),
  bandwidth: document.getElementById("network-bandwidth"),
  analyze: document.getElementById("analyze-button"),
  status: document.getElementById("status"),
  previewPanel: document.getElementById("file-preview-panel"),
  previewSummary: document.getElementById("file-preview-summary"),
  previewBody: document.getElementById("file-preview-body"),
  overviewPanel: document.getElementById("overview-panel"),
  overviewBody: document.getElementById("overview-body"),
  summaryFilterMode: document.getElementById("summary-filter-mode"),
  summaryTimeControls: document.getElementById("summary-time-controls"),
  summaryLineControls: document.getElementById("summary-line-controls"),
  summaryStart: document.getElementById("summary-start"),
  summaryEnd: document.getElementById("summary-end"),
  summaryLineStart: document.getElementById("summary-line-start"),
  summaryLineEnd: document.getElementById("summary-line-end"),
  summaryApply: document.getElementById("summary-apply-button"),
  summaryLabel: document.getElementById("summary-range-label"),
  selectorPanel: document.getElementById("server-selector-panel"),
  serverSelect: document.getElementById("server-select"),
  serverPanels: document.getElementById("server-panels"),
  copyMenu: document.getElementById("copy-menu"),
  copyButton: document.getElementById("copy-image-button"),
  toast: document.getElementById("toast")
};

els.files.addEventListener("change", previewSelectedFiles);
els.analyze.addEventListener("click", analyzeFiles);
els.summaryFilterMode.addEventListener("change", syncSummaryFilterControls);
els.summaryApply.addEventListener("click", applySummaryFilter);
els.serverSelect.addEventListener("change", () => {
  document.querySelectorAll(".server-panel").forEach((panel) => {
    panel.hidden = panel.dataset.server !== els.serverSelect.value;
  });
  setTimeout(resizeVisibleCharts, 40);
});
els.copyButton.addEventListener("click", copySelectedImage);
document.addEventListener("click", () => {
  els.copyMenu.style.display = "none";
});

async function previewSelectedFiles() {
  const files = Array.from(els.files.files || []);
  state.previewServers = [];
  els.previewBody.innerHTML = "";
  els.previewPanel.hidden = !files.length;
  destroyCharts();
  state.servers = [];
  els.overviewPanel.hidden = true;
  els.selectorPanel.hidden = true;
  els.serverPanels.innerHTML = "";
  if (!files.length) {
    setStatus("选择一个或多个 .nmon 文件后生成报告。");
    return;
  }

  setStatus("正在读取文件时间范围...");
  const rows = [];
  const times = [];
  let success = 0;
  for (const file of files) {
    try {
      const parsed = parseNmonText(await file.text(), file.name);
      parsed.fileKey = fileKey(file);
      state.previewServers.push(parsed);
      success += 1;
      const extent = serverTimeExtent(parsed);
      if (Number.isFinite(extent.start)) times.push(extent.start);
      if (Number.isFinite(extent.end)) times.push(extent.end);
      rows.push(filePreviewRow({
        fileName: parsed.fileName,
        host: parsed.host,
        start: extent.start,
        end: extent.end,
        readRange: serverReadRange(parsed),
        sectionCount: Object.keys(parsed.sections).length,
        status: parsed.warnings?.length ? parsed.warnings.join("；") : "可解析",
        ok: true
      }));
    } catch (error) {
      rows.push(filePreviewRow({
        fileName: file.name,
        host: "-",
        start: null,
        end: null,
        readRange: "-",
        sectionCount: "-",
        status: error.message || String(error),
        ok: false
      }));
    }
  }

  els.previewBody.innerHTML = rows.join("");
  const start = times.length ? arrayMin(times) : null;
  const end = times.length ? arrayMax(times) : null;
  els.previewSummary.textContent = Number.isFinite(start) && Number.isFinite(end)
    ? `已识别 ${success}/${files.length} 个文件，整体时间范围：${formatDateTime(start)} ~ ${formatDateTime(end)}`
    : `已识别 ${success}/${files.length} 个文件。`;
  setStatus(success ? "文件时间范围已关联，可直接生成报告。" : "没有可解析的 nmon 文件。", success ? "muted" : "failure");
}

async function analyzeFiles() {
  const files = Array.from(els.files.files || []);
  if (!files.length) {
    setStatus("请选择至少一个 .nmon 文件。", "failure");
    return;
  }

  setStatus("正在解析 nmon 文件...");
  destroyCharts();
  const selectedThemes = selectedMetrics();
  const bandwidth = Number(els.bandwidth.value) > 0 ? Number(els.bandwidth.value) : null;
  const servers = [];
  const failures = [];
  const parsedByFile = new Map(state.previewServers.map((server) => [server.fileKey, server]));

  for (const file of files) {
    try {
      const parsed = parsedByFile.get(fileKey(file)) || parseNmonText(await file.text(), file.name);
      const filtered = filterServer(parsed, null, null, selectedThemes);
      if (Object.keys(filtered.sections).length) {
        filtered.charts = buildChartSpecs(filtered, DEFAULT_TOP_N, bandwidth, selectedThemes);
        filtered.overview = buildOverviewPayload(filtered);
        servers.push(filtered);
      } else {
        failures.push(`${file.name}: 指定时间范围内没有所选指标数据`);
      }
    } catch (error) {
      failures.push(`${file.name}: ${error.message || error}`);
    }
  }

  try {
    state.servers = servers;
    renderReport(servers, failures);
    const extent = overviewExtent();
    const lineExtent = overviewLineExtent();
    setSummaryFilterInputs({
      mode: "time",
      start: extent.start,
      end: extent.end,
      lineStart: lineExtent.start,
      lineEnd: lineExtent.end
    });
    updateOverview({ mode: "time", start: extent.start, end: extent.end, lineStart: lineExtent.start, lineEnd: lineExtent.end });
    setStatus(`解析完成：成功 ${servers.length} 个，失败 ${failures.length} 个。${failures.join("；")}`, failures.length ? "warning" : "muted");
  } catch (error) {
    console.error(error);
    setStatus(`生成报告失败：${error.message || error}`, "failure");
  }
}

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function parseNmonText(text, fileName) {
  const metadata = {};
  const headers = {};
  const rows = {};
  const timestamps = {};
  const warnings = [];
  const lines = text.split(/\r?\n/);

  lines.forEach((line, index) => {
    if (!line.trim()) return;
    const row = parseCsvLine(line).map((cell) => cell.trim());
    const section = row[0];
    if (!section) return;
    if (section === "AAA") {
      if (row.length >= 3) metadata[normalizeKey(row[1])] = row[2];
      return;
    }
    if (section === "ZZZZ") {
      const stamp = parseNmonTimestamp(row);
      if (stamp && row[1]) timestamps[row[1]] = stamp;
      else warnings.push(`无法解析时间行：${line}`);
      return;
    }
    if (row.length < 2) return;
    if (/^T\d+/i.test(row[1])) {
      rows[section] ||= [];
      rows[section].push({ line: index + 1, cells: row.slice(1) });
    } else {
      headers[section] = normalizeHeader(row);
    }
  });

  if (!Object.keys(timestamps).length) {
    throw new Error("没有找到 ZZZZ 时间采样记录");
  }

  const sections = {};
  Object.entries(rows).forEach(([section, sectionRows]) => {
    const frame = buildSectionFrame(sectionRows, headers[section], timestamps, section);
    if (frame.length) sections[section] = frame;
  });

  if (!Object.keys(sections).length) {
    throw new Error("没有可用的时序 section");
  }

  const host = metadata.host || metadata.hostname || metadata.node || metadata.server || stripExtension(fileName);
  return { fileName, host, metadata, sections, warnings };
}

function filePreviewRow(item) {
  return `<tr>
    <td>${escapeHtml(item.fileName)}</td>
    <td>${escapeHtml(item.host)}</td>
    <td>${Number.isFinite(item.start) ? escapeHtml(formatDateTime(item.start)) : "-"}</td>
    <td>${Number.isFinite(item.end) ? escapeHtml(formatDateTime(item.end)) : "-"}</td>
    <td>${escapeHtml(item.readRange)}</td>
    <td>${escapeHtml(item.sectionCount)}</td>
    <td class="${item.ok ? "" : "failure"}">${escapeHtml(item.status)}</td>
  </tr>`;
}

function serverTimeExtent(server) {
  const times = Object.values(server.sections)
    .flatMap((rows) => rows.map((row) => row.timestamp?.getTime()))
    .filter(Number.isFinite);
  return times.length ? { start: arrayMin(times), end: arrayMax(times) } : { start: null, end: null };
}

function serverReadRange(server) {
  const lines = Object.values(server.sections)
    .flatMap((rows) => rows.map((row) => Number(row.source_line)))
    .filter(Number.isFinite);
  return lines.length ? `${arrayMin(lines)}-${arrayMax(lines)}` : "-";
}

function parseCsvLine(line) {
  const result = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      result.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current);
  return result;
}

function parseNmonTimestamp(row) {
  if (row.length < 4) return null;
  return parseDateParts(row[3], row[2]) || parseDateParts(row[2], row[3]);
}

function parseDateParts(dateText, timeText) {
  const dateMatch = String(dateText || "").match(/^(\d{1,2})[-/ ]([A-Za-z]+|\d{1,2})[-/ ](\d{2,4})$/);
  const timeMatch = String(timeText || "").match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!dateMatch || !timeMatch) return null;
  const day = Number(dateMatch[1]);
  const rawMonth = dateMatch[2];
  const month = /^\d+$/.test(rawMonth) ? Number(rawMonth) - 1 : MONTHS[rawMonth.toLowerCase()];
  let year = Number(dateMatch[3]);
  if (year < 100) year += 2000;
  if (!Number.isFinite(month)) return null;
  const date = new Date(year, month, day, Number(timeMatch[1]), Number(timeMatch[2]), Number(timeMatch[3] || 0));
  return Number.isNaN(date.getTime()) ? null : date;
}

function normalizeHeader(row) {
  const columns = ["timestamp_id"];
  row.slice(1).forEach((raw, index) => {
    let name = raw || `value_${index + 1}`;
    if (index === 0 && /^T\d+/i.test(name)) name = "timestamp_id";
    columns.push(dedupeName(name, columns));
  });
  return columns;
}

function buildSectionFrame(sectionRows, header, timestamps, section) {
  const maxWidth = arrayMax(sectionRows.map((row) => row.cells.length));
  const columns = alignHeaderColumns(header, maxWidth);
  while (columns.length < maxWidth) columns.push(`value_${columns.length}`);

  return sectionRows
    .map((row) => {
      const cells = row.cells.concat(Array(Math.max(0, maxWidth - row.cells.length)).fill(""));
      const timestampId = cells[0];
      const timestamp = timestamps[timestampId];
      if (!timestamp) return null;
      const item = { timestamp, timestamp_id: timestampId, source_line: row.line, section };
      columns.forEach((column, index) => {
        if (column === "timestamp_id") return;
        item[column] = parseMaybeNumber(cells[index]);
      });
      return item;
    })
    .filter(Boolean)
    .sort((left, right) => left.timestamp - right.timestamp);
}

function alignHeaderColumns(header, width) {
  if (!header) return Array.from({ length: width }, (_, index) => index ? `value_${index}` : "timestamp_id");
  const columns = header.slice();
  if (columns.length === width + 1) columns.splice(1, 1);
  return columns.slice(0, width);
}

function filterServer(server, start, end, selectedThemes) {
  const sections = {};
  Object.entries(server.sections).forEach(([name, rows]) => {
    const theme = classifySection(name);
    if (!selectedThemes.includes(theme)) return;
    const filteredRows = rows.filter((row) => inRange(row.timestamp, start, end));
    if (filteredRows.length) sections[name] = filteredRows;
  });
  return { ...server, sections };
}

function classifySection(section) {
  const name = section.toUpperCase();
  if (name === "CPU_ALL" || /^CPU/.test(name)) return "cpu";
  if (["MEM", "MEMNEW", "VM", "PAGE", "LARGEPAGE"].includes(name)) return "memory";
  if (/^DISK/.test(name)) return "disk";
  if (/^NET/.test(name)) return "network";
  return "unclassified";
}

function selectedMetrics() {
  return Array.from(document.querySelectorAll('input[name="metric"]:checked')).map((input) => input.value);
}

function buildChartSpecs(server, topN, bandwidth, selectedThemes) {
  const builders = [
    ["cpu", "CPU 使用率趋势图", "cpu_usage", cpuUsageData],
    ["memory", "内存使用率趋势图", "memory_usage_percent", memoryUsageData],
    ["memory", "内存明细趋势图", "memory_detail", memoryDetailData],
    ["memory", "Swap 使用趋势图", "swap_usage", swapUsageData],
    ["disk", `磁盘 Busy Top${topN} 趋势图`, "disk_busy_top", (item) => diskBusyData(item, topN)],
    ["disk", `磁盘读写吞吐 Top${topN} 趋势图`, "disk_io_top", (item) => diskIoData(item, topN)],
    ["disk", `磁盘 IOPS Top${topN} 趋势图`, "disk_iops_top", (item) => diskIopsData(item, topN)],
    ["network", `网络吞吐 Top${topN} 趋势图`, "network_top", (item) => networkTopData(item, topN)]
  ];
  if (bandwidth) builders.push(["network", "网络带宽使用率趋势图", "network_bandwidth_usage", (item) => networkBandwidthData(item, bandwidth)]);

  return builders
    .filter(([theme]) => selectedThemes.includes(theme))
    .map(([theme, title, key, builder]) => {
      const data = builder(server);
      if (!data || !Object.keys(data.series).length) return null;
      return {
        theme,
        key,
        title: `${server.host} ${title}`,
        unit: data.unit,
        percent: data.percent,
        signedMirror: data.signedMirror || false,
        chartType: key === "cpu_usage" ? "stacked-area" : "line",
        maxAbs: maxAbs(data.series),
        series: Object.entries(data.series).map(([name, points]) => ({ name, data: points }))
      };
    })
    .filter(Boolean);
}

function cpuUsageData(server) {
  const frame = server.sections.CPU_ALL;
  if (!frame) return null;
  const series = {
    "CPU Busy%": chartPointsFromRows(frame, (row) => cpuBusy(row)),
    "User%": chartPointsFromRows(frame, (row) => numberOrNull(row["User%"])),
    "Sys%": chartPointsFromRows(frame, (row) => numberOrNull(row["Sys%"])),
    "Wait%": chartPointsFromRows(frame, (row) => numberOrNull(row["Wait%"]))
  };
  return { unit: "%", percent: true, series: cleanSeries(series) };
}

function memoryUsageData(server) {
  const frame = firstSection(server, "MEM", "MEMNEW");
  if (!frame) return null;
  const used = chartPointsFromRows(frame, (row) => memoryUsedPercent(row));
  return { unit: "%", percent: true, series: cleanSeries({ "Memory Used%": used }) };
}

function memoryDetailData(server) {
  const frame = firstSection(server, "MEM", "MEMNEW");
  if (!frame) return null;
  const columns = {
    "Memory Available/Free": findColumn(frame, ["Memory Available", "available", "Real free MB", "memfree"]),
    Cached: findColumn(frame, ["Cached", "cached"]),
    Buffers: findColumn(frame, ["Buffers", "buffers"])
  };
  const series = {};
  Object.entries(columns).forEach(([label, column]) => {
    if (column) series[label] = chartPointsFromRows(frame, (row) => numberOrNull(row[column]));
  });
  return { unit: "MB", percent: false, series: cleanSeries(series) };
}

function swapUsageData(server) {
  const memFrame = firstSection(server, "MEM", "MEMNEW");
  const vmFrame = firstSection(server, "VM", "PAGE");
  const series = {};
  if (memFrame) series["Swap Used%"] = chartPointsFromRows(memFrame, (row) => swapUsedPercent(row));
  if (vmFrame) {
    const inColumn = findColumn(vmFrame, ["pswpin", "SwapIn", "swapin"]);
    const outColumn = findColumn(vmFrame, ["pswpout", "SwapOut", "swapout"]);
    if (inColumn) series["Swap In"] = chartPointsFromRows(vmFrame, (row) => numberOrNull(row[inColumn]));
    if (outColumn) series["Swap Out"] = chartPointsFromRows(vmFrame, (row) => numberOrNull(row[outColumn]));
  }
  return { unit: "%, pages/s", percent: false, series: cleanSeries(series) };
}

function diskBusyData(server, topN) {
  const frame = server.sections.DISKBUSY;
  if (!frame) return null;
  const columns = topColumns(frame, topN, arrayMax);
  const series = Object.fromEntries(columns.map((column) => [column, chartPointsFromRows(frame, (row) => numberOrNull(row[column]))]));
  return { unit: "%", percent: true, series: cleanSeries(series) };
}

function diskIoData(server, topN) {
  const readFrame = server.sections.DISKREAD;
  const writeFrame = server.sections.DISKWRITE;
  if (!readFrame || !writeFrame) return null;
  const disks = Array.from(new Set(numericColumns(readFrame).concat(numericColumns(writeFrame))));
  const ranked = disks.map((disk) => {
    const maxTotal = arrayMax(readFrame.map((row, index) => Math.max(0, valueAt(readFrame, index, disk)) + Math.max(0, valueAt(writeFrame, index, disk))));
    return [disk, maxTotal];
  }).sort((a, b) => b[1] - a[1]).slice(0, topN);
  const series = {};
  ranked.forEach(([disk]) => {
    if (numericColumns(readFrame).includes(disk)) series[`${disk} Read MB/s`] = chartPointsFromRows(readFrame, (row) => numberOrNull(row[disk]) / 1024);
    if (numericColumns(writeFrame).includes(disk)) series[`${disk} Write MB/s`] = chartPointsFromRows(writeFrame, (row) => -numberOrNull(row[disk]) / 1024);
  });
  return { unit: "MB/s", percent: false, signedMirror: true, series: cleanSeries(series) };
}

function diskIopsData(server, topN) {
  const frame = server.sections.DISKXFER;
  if (!frame) return null;
  const columns = topColumns(frame, topN, arrayMax);
  const series = Object.fromEntries(columns.map((column) => [`${column} Xfer/s`, chartPointsFromRows(frame, (row) => numberOrNull(row[column]))]));
  return { unit: "Xfer/s", percent: false, series: cleanSeries(series) };
}

function networkTopData(server, topN) {
  const frame = server.sections.NET;
  const pairs = networkPairs(frame);
  if (!frame || !Object.keys(pairs).length) return null;
  const ranked = Object.entries(pairs).map(([iface, pair]) => {
    const maxTotal = arrayMax(frame.map((row) => Math.max(0, numberOrNull(row[pair.read]) || 0) + Math.max(0, numberOrNull(row[pair.write]) || 0)));
    return [iface, maxTotal];
  }).sort((a, b) => b[1] - a[1]).slice(0, topN);
  const series = {};
  ranked.forEach(([iface]) => {
    const pair = pairs[iface];
    if (pair.read) series[`${iface} Receive MB/s`] = chartPointsFromRows(frame, (row) => numberOrNull(row[pair.read]) / 1024);
    if (pair.write) series[`${iface} Transmit MB/s`] = chartPointsFromRows(frame, (row) => -numberOrNull(row[pair.write]) / 1024);
  });
  return { unit: "MB/s", percent: false, signedMirror: true, series: cleanSeries(series) };
}

function networkBandwidthData(server, bandwidth) {
  const frame = server.sections.NET;
  const pairs = networkPairs(frame);
  if (!frame || !Object.keys(pairs).length) return null;
  const total = chartPointsFromRows(frame, (row) => {
    const kb = Object.values(pairs).reduce((sum, pair) => sum + (numberOrNull(row[pair.read]) || 0) + (numberOrNull(row[pair.write]) || 0), 0);
    return (kb / 1024) * 8 / bandwidth * 100;
  });
  return { unit: "%", percent: true, series: cleanSeries({ "Bandwidth Usage%": total }) };
}

function buildOverviewPayload(server) {
  const cpuFrame = server.sections.CPU_ALL;
  const memFrame = firstSection(server, "MEM", "MEMNEW");
  const netFrame = server.sections.NET;
  return {
    fileName: server.fileName,
    host: server.host,
    ip: metadataValue(server, ["ip", "ip_address", "host_ip", "hostip"]),
    system: metadataValue(server, ["os", "os_release", "system", "system_type", "machine_type"]),
    metrics: {
      cpu: cpuFrame ? overviewPointsFromRows(cpuFrame, (row) => cpuBusy(row)) : [],
      memory: memFrame ? overviewPointsFromRows(memFrame, (row) => memoryUsedPercent(row)) : [],
      swap: memFrame ? overviewPointsFromRows(memFrame, (row) => swapUsedPercent(row)) : [],
      diskRead: maxSectionPoints(server.sections.DISKREAD),
      diskWrite: maxSectionPoints(server.sections.DISKWRITE),
      networkRead: networkDirectionPoints(netFrame, ["read", "recv", "receive", "in"]),
      networkWrite: networkDirectionPoints(netFrame, ["write", "send", "transmit", "out"])
    },
    rangePoints: Object.values(server.sections).flatMap((rows) => rows.map((row) => [formatDate(row.timestamp), row.source_line]))
  };
}

function renderReport(servers, failures) {
  els.overviewPanel.hidden = !servers.length;
  els.selectorPanel.hidden = !servers.length;
  els.serverPanels.innerHTML = "";
  els.serverSelect.innerHTML = "";

  failures.forEach((failure) => console.warn(failure));

  servers.forEach((server, index) => {
    const option = document.createElement("option");
    option.value = server.host;
    option.textContent = `${server.host} - ${server.fileName}`;
    els.serverSelect.appendChild(option);

    const panel = document.createElement("section");
    panel.className = "panel server-panel";
    panel.dataset.server = server.host;
    panel.hidden = index !== 0;
    panel.innerHTML = `<h2>${escapeHtml(server.host)}</h2><div class="muted">${escapeHtml(server.fileName)}</div>${renderTabs(server.charts)}<div class="chart-grid"></div>`;
    const grid = panel.querySelector(".chart-grid");
    const pendingCharts = [];
    server.charts.forEach((spec, chartIndex) => {
      const card = document.createElement("div");
      card.className = "chart-card";
      card.dataset.theme = spec.theme;
      card.hidden = chartIndex > 0 && spec.theme !== server.charts[0].theme;
      card.innerHTML = `<h3>${escapeHtml(spec.title)}</h3><div class="echart"></div>`;
      grid.appendChild(card);
      pendingCharts.push([card.querySelector(".echart"), spec]);
    });
    if (!server.charts.length) {
      grid.innerHTML = `<div class="empty">没有可展示的图表</div>`;
    }
    els.serverPanels.appendChild(panel);
    pendingCharts.forEach(([container, spec]) => renderChart(container, spec));
  });

  document.querySelectorAll(".resource-tabs").forEach((tabs) => {
    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-theme]");
      if (!button) return;
      const panel = button.closest(".server-panel");
      panel.querySelectorAll(".resource-tabs button").forEach((item) => item.classList.toggle("active", item === button));
      panel.querySelectorAll(".chart-card").forEach((card) => {
        card.hidden = card.dataset.theme !== button.dataset.theme;
      });
      setTimeout(resizeVisibleCharts, 40);
    });
  });
  scheduleInitialChartResize();
}

function renderTabs(charts) {
  const themes = Array.from(new Set(charts.map((chart) => chart.theme)));
  if (themes.length <= 1) return "";
  return `<div class="resource-tabs">${themes.map((theme, index) => `<button type="button" class="${index === 0 ? "active" : ""}" data-theme="${theme}">${THEME_LABELS[theme] || theme}</button>`).join("")}</div>`;
}

function renderChart(container, spec) {
  if (!window.echarts) {
    container.outerHTML = `<div class="empty">ECharts 加载失败</div>`;
    return;
  }
  const chart = echarts.init(container, null, { renderer: "canvas" });
  chart.setOption(echartOption(spec));
  chart.on("dataZoom", () => {
    const range = chartZoomRange(chart, spec);
    if (range) {
      updateOverview({ mode: "time", start: range.start, end: range.end }, true);
    }
  });
  container.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    state.selectedImageUrl = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#fff" });
    els.copyMenu.style.left = `${event.clientX}px`;
    els.copyMenu.style.top = `${event.clientY}px`;
    els.copyMenu.style.display = "block";
  });
  state.charts.push({ chart, container });
}

function echartOption(spec) {
  return {
    animation: false,
    color: ["#2f7ed8", "#d94e5d", "#31a354", "#9467bd", "#ff7f0e", "#17becf", "#bcbd22", "#8c564b", "#e377c2", "#7f7f7f"],
    title: { text: spec.title, left: "center", top: 4, textStyle: { fontSize: 15, fontWeight: 600 } },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      valueFormatter: (value) => `${(spec.signedMirror ? Math.abs(Number(value)) : Number(value)).toFixed(2)} ${spec.unit}`
    },
    legend: { type: "scroll", top: 36, left: 18, right: 18 },
    grid: { top: 88, left: 72, right: 36, bottom: 82 },
    toolbox: {
      right: 18,
      feature: {
        dataZoom: { yAxisIndex: "none" },
        restore: {},
        saveAsImage: { title: "保存图片", pixelRatio: 2 }
      }
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, filterMode: "none" },
      { type: "slider", xAxisIndex: 0, bottom: 28, height: 22 }
    ],
    xAxis: { type: "time", name: "采样时间", axisLabel: { formatter: "{yyyy}-{MM}-{dd}\n{HH}:{mm}:{ss}" } },
    yAxis: {
      type: "value",
      name: spec.unit,
      min: spec.percent ? 0 : (spec.signedMirror ? -Math.max(spec.maxAbs, 1) : null),
      max: spec.percent ? 100 : (spec.signedMirror ? Math.max(spec.maxAbs, 1) : null),
      scale: !spec.percent && !spec.signedMirror,
      axisLabel: { formatter: (value) => spec.signedMirror ? Math.abs(Number(value)).toFixed(0) : value }
    },
    series: spec.series.map((item) => ({
      name: item.name,
      type: "line",
      showSymbol: false,
      sampling: "lttb",
      stack: spec.chartType === "stacked-area" && item.name !== "CPU Busy%" ? "CPU使用组成" : null,
      areaStyle: spec.chartType === "stacked-area" && item.name !== "CPU Busy%" ? { opacity: 0.72 } : null,
      lineStyle: item.name === "CPU Busy%" ? { width: 2.2 } : { width: 1.2 },
      data: item.data
    }))
  };
}

function applySummaryFilter() {
  const mode = els.summaryFilterMode.value;
  updateOverview({
    mode,
    start: parseDateInput(els.summaryStart.value),
    end: parseDateInput(els.summaryEnd.value),
    lineStart: parseNumberInput(els.summaryLineStart.value),
    lineEnd: parseNumberInput(els.summaryLineEnd.value)
  }, true);
}

function syncSummaryFilterControls() {
  const mode = els.summaryFilterMode.value;
  els.summaryTimeControls.hidden = mode !== "time";
  els.summaryLineControls.hidden = mode !== "line";
}

function setSummaryFilterInputs(filter) {
  if (filter.mode) els.summaryFilterMode.value = filter.mode;
  if (Number.isFinite(filter.start)) els.summaryStart.value = formatInputDate(filter.start);
  if (Number.isFinite(filter.end)) els.summaryEnd.value = formatInputDate(filter.end);
  if (Number.isFinite(filter.lineStart)) els.summaryLineStart.value = String(filter.lineStart);
  if (Number.isFinite(filter.lineEnd)) els.summaryLineEnd.value = String(filter.lineEnd);
  syncSummaryFilterControls();
}

function updateOverview(filter, updateInputs = false) {
  const mode = filter?.mode || "time";
  const extent = overviewExtent();
  const lineExtent = overviewLineExtent();
  const cleanFilter = {
    mode,
    start: Number.isFinite(filter?.start) ? filter.start : extent.start,
    end: Number.isFinite(filter?.end) ? filter.end : extent.end,
    lineStart: Number.isFinite(filter?.lineStart) ? filter.lineStart : lineExtent.start,
    lineEnd: Number.isFinite(filter?.lineEnd) ? filter.lineEnd : lineExtent.end
  };
  state.summaryRange = cleanFilter;
  if (updateInputs) setSummaryFilterInputs(cleanFilter);
  els.summaryLabel.textContent = summaryFilterLabel(cleanFilter);
  els.overviewBody.innerHTML = state.servers.map((server) => overviewRow(server.overview, cleanFilter)).join("");
}

function overviewRow(row, filter) {
  const metrics = row.metrics;
  return `<tr>
    <td>${escapeHtml(row.fileName)}</td>
    <td>${escapeHtml(row.host)}</td>
    <td>${escapeHtml(row.ip || "-")}</td>
    <td>${formatPercent(maxValue(metrics.cpu, filter))}</td>
    <td>${formatPercent(maxValue(metrics.memory, filter))}</td>
    <td>${formatPercent(maxValue(metrics.swap, filter))}</td>
    <td>${formatNumber(maxValue(metrics.diskRead, filter))}</td>
    <td>${formatNumber(maxValue(metrics.diskWrite, filter))}</td>
    <td>${formatNumber(maxValue(metrics.networkRead, filter))}</td>
    <td>${formatNumber(maxValue(metrics.networkWrite, filter))}</td>
    <td>${escapeHtml(row.system || "-")}</td>
    <td>${escapeHtml(readRange(row.rangePoints, filter))}</td>
  </tr>`;
}

function overviewExtent() {
  const times = state.servers.flatMap((server) => Object.values(server.overview?.metrics || {}).flatMap((points) => points.map((point) => Date.parse(point[0]))));
  const clean = times.filter(Number.isFinite);
  return clean.length ? { start: arrayMin(clean), end: arrayMax(clean) } : { start: null, end: null };
}

function overviewLineExtent() {
  const lines = state.servers.flatMap((server) => (server.overview?.rangePoints || []).map((point) => Number(point[1])));
  const clean = lines.filter(Number.isFinite);
  return clean.length ? { start: arrayMin(clean), end: arrayMax(clean) } : { start: null, end: null };
}

function summaryFilterLabel(filter) {
  if (filter.mode === "line") {
    return Number.isFinite(filter.lineStart) && Number.isFinite(filter.lineEnd)
      ? `读取范围：${filter.lineStart}-${filter.lineEnd}`
      : "读取范围：全部";
  }
  return Number.isFinite(filter.start) && Number.isFinite(filter.end)
    ? `时间范围：${formatDateTime(filter.start)} ~ ${formatDateTime(filter.end)}`
    : "时间范围：全部";
}

function chartZoomRange(chart, spec) {
  const times = spec.series.flatMap((series) => series.data.map((point) => Date.parse(point[0]))).filter(Number.isFinite);
  if (!times.length) return null;
  const extent = { start: arrayMin(times), end: arrayMax(times) };
  const zoom = (chart.getOption().dataZoom || [])[0];
  if (!zoom) return extent;
  const start = extent.start + (extent.end - extent.start) * (Number(zoom.start || 0) / 100);
  const end = extent.start + (extent.end - extent.start) * (Number(zoom.end ?? 100) / 100);
  return { start: Math.min(start, end), end: Math.max(start, end) };
}

function destroyCharts() {
  state.charts.forEach(({ chart }) => chart.dispose());
  state.charts = [];
}

function resizeVisibleCharts() {
  state.charts.forEach(({ chart }) => {
    if (chart.getDom().offsetParent !== null) chart.resize();
  });
}

function scheduleInitialChartResize() {
  requestAnimationFrame(() => {
    resizeVisibleCharts();
    setTimeout(resizeVisibleCharts, 80);
  });
}

window.addEventListener("resize", resizeVisibleCharts);

async function copySelectedImage() {
  try {
    if (!state.selectedImageUrl) return;
    const blob = await (await fetch(state.selectedImageUrl)).blob();
    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    toast("图片已复制");
  } catch {
    toast("浏览器不允许复制图片，请使用图表工具栏保存");
  }
}

function chartPointsFromRows(rows, getter) {
  return rows.map((row) => [formatDate(row.timestamp), getter(row)]).filter((point) => Number.isFinite(point[1]));
}

function overviewPointsFromRows(rows, getter) {
  return rows.map((row) => [formatDate(row.timestamp), getter(row), row.source_line]).filter((point) => Number.isFinite(point[1]));
}

function maxSectionPoints(rows) {
  if (!rows) return [];
  const columns = numericColumns(rows);
  return overviewPointsFromRows(rows, (row) => arrayMax(columns.map((column) => numberOrNull(row[column])).filter(Number.isFinite)));
}

function networkDirectionPoints(rows, keywords) {
  if (!rows) return [];
  const columns = numericColumns(rows).filter((column) => keywords.some((keyword) => column.toLowerCase().includes(keyword)));
  return overviewPointsFromRows(rows, (row) => arrayMax(columns.map((column) => numberOrNull(row[column])).filter(Number.isFinite)));
}

function cpuBusy(row) {
  const busyColumn = findColumn([row], ["Busy", "Busy%"], { exactOnly: true });
  if (busyColumn && Number.isFinite(numberOrNull(row[busyColumn]))) return clampNumber(numberOrNull(row[busyColumn]), 0, 100, 0);
  const idleColumn = findColumn([row], ["Idle%", "Idle"], { exactOnly: true });
  if (idleColumn && Number.isFinite(numberOrNull(row[idleColumn]))) return clampNumber(100 - numberOrNull(row[idleColumn]), 0, 100, 0);
  const usageColumns = ["User%", "Sys%", "Wait%"].map((name) => findColumn([row], [name], { exactOnly: true })).filter(Boolean);
  const namedUsage = sumValues(row, usageColumns);
  if (Number.isFinite(namedUsage)) return clampNumber(namedUsage, 0, 100, 0);
  const values = orderedNumericValues(row);
  if (values.length >= 5) return clampNumber(values[4], 0, 100, 0);
  if (values.length >= 4) return clampNumber(100 - values[3], 0, 100, 0);
  if (values.length >= 3) return clampNumber(values[0] + values[1] + values[2], 0, 100, 0);
  return null;
}

function memoryUsedPercent(row) {
  const totalColumn = findColumn([row], ["Real total MB", "memtotal", "Memory total", "memtotal-mb"]);
  const freeColumn = findColumn([row], ["Real free MB", "memfree", "Memory free", "memfree-mb"]);
  const availableColumn = findColumn([row], ["available", "memavailable", "Memory available"]);
  if (totalColumn && freeColumn) {
    const total = numberOrNull(row[totalColumn]);
    const free = numberOrNull(row[freeColumn]);
    const cached = availableColumn ? 0 : numberOrNull(row[findColumn([row], ["cached", "Cached"])]) || 0;
    const buffers = availableColumn ? 0 : numberOrNull(row[findColumn([row], ["buffers", "Buffers"])]) || 0;
    if (total > 0) return clampNumber((total - free - cached - buffers) / total * 100, 0, 100, 0);
  }
  if (totalColumn && availableColumn) {
    const total = numberOrNull(row[totalColumn]);
    const available = numberOrNull(row[availableColumn]);
    if (total > 0) return clampNumber((total - available) / total * 100, 0, 100, 0);
  }
  const usedColumn = findColumn([row], ["Memory Used%", "used%"]);
  return usedColumn ? clampNumber(numberOrNull(row[usedColumn]), 0, 100, 0) : null;
}

function swapUsedPercent(row) {
  const totalColumn = findColumn([row], ["Virtual total MB", "swaptotal", "Swap total", "swaptotal-mb"], { exactOnly: true });
  const freeColumn = findColumn([row], ["Virtual free MB", "swapfree", "Swap free", "swapfree-mb"], { exactOnly: true });
  if (totalColumn && freeColumn) {
    const total = numberOrNull(row[totalColumn]);
    const free = numberOrNull(row[freeColumn]);
    if (total === 0 && free === 0) return 0;
    if (total > 0) return clampNumber((total - free) / total * 100, 0, 100, 0);
  }
  const usedColumn = findColumn([row], ["Swap Used%", "swap used"], { exactOnly: true });
  return usedColumn ? clampNumber(numberOrNull(row[usedColumn]), 0, 100, 0) : null;
}

function topColumns(rows, topN, score) {
  return numericColumns(rows)
    .map((column) => [column, score(rows.map((row) => numberOrNull(row[column])).filter(Number.isFinite))])
    .filter((item) => Number.isFinite(item[1]))
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map((item) => item[0]);
}

function networkPairs(rows) {
  if (!rows) return {};
  const pairs = {};
  numericColumns(rows).forEach((column) => {
    const lower = column.toLowerCase();
    if (lower.includes("read") || lower.includes("recv") || lower.includes("receive")) {
      const iface = ifaceName(column, ["-read-kb/s", "_read-kb/s", "read", "recv", "receive"]);
      pairs[iface] ||= {};
      pairs[iface].read = column;
    } else if (lower.includes("write") || lower.includes("send") || lower.includes("transmit")) {
      const iface = ifaceName(column, ["-write-kb/s", "_write-kb/s", "write", "send", "transmit"]);
      pairs[iface] ||= {};
      pairs[iface].write = column;
    }
  });
  return pairs;
}

function firstSection(server, ...names) {
  for (const name of names) {
    if (server.sections[name]) return server.sections[name];
  }
  return null;
}

function numericColumns(rows) {
  if (!rows || !rows.length) return [];
  return Object.keys(rows[0]).filter((column) => !["timestamp", "timestamp_id", "source_line", "section"].includes(column) && rows.some((row) => Number.isFinite(numberOrNull(row[column]))));
}

function orderedNumericValues(row) {
  return Object.keys(row)
    .filter((column) => !["timestamp", "timestamp_id", "source_line", "section"].includes(column))
    .map((column) => numberOrNull(row[column]))
    .filter(Number.isFinite);
}

function findColumn(rows, candidates, options = {}) {
  if (!rows || !rows.length) return null;
  const columns = Object.keys(rows[0]);
  for (const candidate of candidates) {
    const exact = columns.find((column) => column.toLowerCase() === candidate.toLowerCase());
    if (exact) return exact;
  }
  if (options.exactOnly) return null;
  for (const candidate of candidates) {
    const found = columns.find((column) => column.toLowerCase().includes(candidate.toLowerCase()));
    if (found) return found;
  }
  return null;
}

function valueAt(rows, index, column) {
  if (!rows || !rows[index] || !column) return 0;
  return numberOrNull(rows[index][column]) || 0;
}

function cleanSeries(series) {
  return Object.fromEntries(Object.entries(series).filter(([, points]) => points && points.length));
}

function maxAbs(series) {
  const values = Object.values(series).flatMap((points) => points.map((point) => Math.abs(Number(point[1]))).filter(Number.isFinite));
  return values.length ? arrayMax(values) * 1.08 : 0;
}

function maxValue(points, filter) {
  const values = (points || []).filter((point) => pointMatchesFilter(point, filter)).map((point) => Number(point[1])).filter(Number.isFinite);
  return values.length ? arrayMax(values) : null;
}

function readRange(points, filter) {
  const lines = (points || []).filter((point) => pointMatchesFilter([point[0], 0, point[1]], filter)).map((point) => Number(point[1])).filter(Number.isFinite);
  return lines.length ? `${arrayMin(lines)}-${arrayMax(lines)}` : "-";
}

function pointMatchesFilter(point, filter) {
  if (filter?.mode === "line") {
    return numberInRange(Number(point[2]), filter.lineStart, filter.lineEnd);
  }
  return inRange(Date.parse(point[0]), filter?.start, filter?.end);
}

function metadataValue(server, keys) {
  for (const key of keys) {
    if (server.metadata[key]) return server.metadata[key];
  }
  return "-";
}

function sumValues(row, columns) {
  const values = columns.map((column) => numberOrNull(row[column])).filter(Number.isFinite);
  return values.length ? values.reduce((sum, value) => sum + value, 0) : null;
}

function numberOrNull(value) {
  if (value === "" || value === null || value === undefined) return null;
  if (typeof value === "string" && !value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function parseMaybeNumber(value) {
  if (value === "") return "";
  const number = Number(value);
  return Number.isFinite(number) ? number : value;
}

function inRange(value, start, end) {
  const time = value instanceof Date ? value.getTime() : Number(value);
  if (!Number.isFinite(time)) return false;
  if (Number.isFinite(start) && time < start) return false;
  if (Number.isFinite(end) && time > end) return false;
  return true;
}

function numberInRange(value, start, end) {
  if (!Number.isFinite(value)) return false;
  if (Number.isFinite(start) && value < start) return false;
  if (Number.isFinite(end) && value > end) return false;
  return true;
}

function parseDateInput(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseNumberInput(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDate(date) {
  const value = date instanceof Date ? date : new Date(date);
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`;
}

function formatDateTime(value) {
  return Number.isFinite(value) ? formatDate(new Date(value)) : "";
}

function formatInputDate(value) {
  return Number.isFinite(value) ? formatDate(new Date(value)).replace(" ", "T") : "";
}

function formatPercent(value) {
  return value === null || value === undefined ? "-" : `${Number(value).toFixed(2)}%`;
}

function formatNumber(value) {
  return value === null || value === undefined ? "-" : Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function clampNumber(value, min, max, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

function arrayMax(values) {
  let result = -Infinity;
  for (const value of values || []) {
    const number = Number(value);
    if (Number.isFinite(number) && number > result) result = number;
  }
  return result === -Infinity ? null : result;
}

function arrayMin(values) {
  let result = Infinity;
  for (const value of values || []) {
    const number = Number(value);
    if (Number.isFinite(number) && number < result) result = number;
  }
  return result === Infinity ? null : result;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function normalizeKey(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
}

function dedupeName(name, existing) {
  let candidate = name;
  let index = 2;
  while (existing.includes(candidate)) {
    candidate = `${name}_${index}`;
    index += 1;
  }
  return candidate;
}

function ifaceName(column, tokens) {
  let name = column;
  tokens.forEach((token) => {
    if (name.toLowerCase().endsWith(token)) name = name.slice(0, -token.length);
  });
  tokens.forEach((token) => {
    name = name.replace(new RegExp(token, "ig"), "");
  });
  return name.replace(/[-_ ]+$/g, "") || column;
}

function stripExtension(name) {
  return name.replace(/\.[^.]+$/, "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message, level = "muted") {
  els.status.textContent = message;
  els.status.className = `status ${level}`;
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.style.display = "block";
  setTimeout(() => {
    els.toast.style.display = "none";
  }, 1800);
}

window.nmonAnalyzer = {
  parseNmonText,
  filterServer,
  buildChartSpecs,
  buildOverviewPayload,
  renderReport,
  updateOverview,
  overviewExtent,
  state
};
