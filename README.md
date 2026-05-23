# nmon Analyzer

纯前端 nmon 分析工具。把整个目录拷贝到任意机器后，打开 `index.html` 就能使用；不需要 Python、Flask、pip、虚拟环境或命令行安装。

## 使用方式

1. 双击打开 `index.html`。
2. 选择一个或多个 `.nmon` 文件。
3. 页面会自动识别文件时间范围和读取行号范围。
4. 可选填写网络带宽。
5. 选择 CPU、内存、磁盘、网络指标后点击“生成报告”。

项目已内置 ECharts，clone 或拷贝整个目录后可离线使用，不需要访问 CDN。

推荐直接用浏览器打开 `index.html`。如果某些企业浏览器策略限制本地文件访问，可以把整个目录放到已有的静态文件服务中访问；该服务只负责提供 HTML、JS、CSS 文件，不参与解析和报表生成。

## 功能

- 多服务器 `.nmon` 文件本地解析。
- 支持 `ZZZZ` 采样时间映射真实时间。
- 选择文件后自动展示每个文件的采样时间范围、读取范围和 section 数。
- 生成报告默认使用文件全部采样数据。
- 整体汇总一台机器一行，展示 CPU、内存、Swap、磁盘、网络等关键值。
- 汇总表支持按时间范围或读取范围重新计算。
- 汇总表会随图表区域缩放按时间范围动态重新计算。
- 图表支持区域缩放，缩放后会联动刷新整体汇总。
- CPU 使用率使用堆叠面积图展示 User、Sys、Wait，并保留 Busy 趋势线。
- 磁盘和网络默认展示 Top 5。
- 图表右键支持复制图片；工具栏支持保存图片。

## 目录

```text
index.html          Web 入口
assets/app.js       nmon 解析、统计、图表逻辑
assets/styles.css   页面样式
assets/echarts.min.js
                    本地 ECharts 运行依赖
docs/               需求与设计说明
sample/             小型 nmon 示例文件
```

## 需求与设计

当前需求、指标口径、图表设计、运行边界和后续演进约束已固化在：

[docs/requirements-and-design.md](docs/requirements-and-design.md)

## 离线依赖

图表依赖已随项目放在 `assets/echarts.min.js`。入口页只加载本地文件，因此其他用户 clone 仓库后直接打开 `index.html` 即可离线使用。

第三方依赖：

- Apache ECharts 5，Apache-2.0 License。
