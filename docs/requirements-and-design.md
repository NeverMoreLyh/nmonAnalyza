# nmon Analyzer Requirements And Design

## 目标

nmon Analyzer 是一个纯前端、本地运行的 nmon 资源分析工具。目标用户是在性能测试后需要快速整理多台服务器资源使用情况，并把图表截图放入测试报告的测试人员或性能分析人员。

工具必须方便拷贝到不同机器使用：不依赖 Python、Flask、pip、虚拟环境、数据库或后端服务，也不依赖 CDN。浏览器负责完成 nmon 文件读取、解析、统计、图表渲染和报告展示。

## 非目标

- 不直接生成 Word 或 PDF。
- 不上传 nmon 文件到服务器。
- 不保存历史报告到后端。
- 不覆盖 nmon 全部平台特有 section 的深度解释。
- 不追求和 pyNmonAnalyzer 完全相同的 UI，只参考它的图表交互体验。

## 运行方式

首选方式是直接打开仓库根目录的 `index.html`。

如果某些企业浏览器策略限制本地文件访问，可以使用已有静态文件服务托管当前目录。静态文件服务只负责提供 HTML、JS、CSS 文件，不参与解析、汇总和绘图。所有数据处理都在浏览器内完成。

## 输入

用户在页面中选择一个或多个标准 `.nmon` 文本文件。

页面配置项：

- 文件选择：选择文件后立即预解析，展示每个文件的时间范围、读取范围、section 数和状态。
- 指标主题：CPU、内存、磁盘、网络。
- Top N：磁盘和网络图表默认展示 Top 5；当前页面未暴露配置入口。
- 网络带宽 Mbps：可选；填写后可计算网络带宽使用率。

## 输出

页面直接生成一个可交互 HTML 报告。

报告内容：

- 运行状态提示。
- 文件时间与读取范围预览。
- 整体汇总表：一台机器一行。
- 服务器下拉选择。
- 每台服务器按资源主题分组的趋势图。
- 图表右键可复制图片，图表工具栏可保存图片。

## nmon 解析设计

解析逻辑位于 `assets/app.js`。

核心规则：

- 读取 `ZZZZ` 行，将采样编号如 `T0001` 映射为真实时间。
- 读取 section 表头行，例如 `CPU_ALL,User%,Sys%,Wait%,Idle%,Busy,CPUs`。
- 读取 section 数据行，例如 `CPU_ALL,T0001,...`。
- 将每个 section 解析为按真实时间排序的行数组。
- 保留每行原始文件行号，用于汇总表“读取范围”。
- 对数值字段自动转换为 number，无法转换的字段保留为文本。

异常处理：

- 文件没有 `ZZZZ` 行时标记解析失败。
- 文件没有可用时序 section 时标记解析失败。
- 某类指标缺失时不阻断其他指标展示。

## 文件选择预解析

用户选择 `.nmon` 文件后，页面立即执行轻量预解析，不生成图表。

预解析输出：

- 文件名
- 服务器名
- 文件开始采样时间
- 文件结束采样时间
- 读取行号范围
- 可解析 section 数
- 解析状态或错误信息

预解析成功后，页面展示所有文件的整体时间范围。生成报告默认使用文件全部采样数据。

生成报告时优先复用预解析结果，避免同一批文件被重复读取和解析。

## 指标主题映射

当前纯前端版本聚焦四类报告常用指标：

- `cpu`：`CPU_ALL` 和 `CPU*`
- `memory`：`MEM`、`MEMNEW`、`VM`、`PAGE`、`LARGEPAGE`
- `disk`：`DISK*`
- `network`：`NET*`

未归类 section 目前不展示在图表中。后续如需恢复“原始 section 全量探索”，应在不影响当前四类报告体验的前提下单独增加“高级/原始数据”视图。

## 汇总表口径

整体汇总表一台服务器一行，列包括：

- 文件名
- 服务器名
- IP 地址
- CPU 使用率
- 内存使用率
- Swap 使用率
- 磁盘读速率
- 磁盘写速率
- 网络读速率
- 网络写速率
- 系统类型
- 读取范围

汇总值按当前筛选范围内的最大值计算。页面初始化时使用当前报告的全部数据。

动态汇总：

- 整体汇总支持两种筛选模式：按时间范围、按读取范围。
- 按时间范围时，根据采样时间过滤指标点。
- 按读取范围时，根据 nmon 原始文件行号过滤指标点。
- 用户在任意 ECharts 图表中区域缩放或拖动底部缩放条时，汇总表按图表当前可见时间范围重新计算。

## 图表设计

图表使用 ECharts 渲染。为保证离线可用，`assets/echarts.min.js` 已随项目提交，入口页只加载本地依赖。

通用要求：

- X 轴使用真实采样时间。
- 百分比类 Y 轴固定为 0 到 100。
- 图例可滚动，避免线条较多时挤压图表。
- 启用 tooltip、区域缩放、保存图片。
- 图表标题包含服务器名和指标类型。

### CPU 图表

图表：`CPU 使用率趋势图`

展示：

- CPU Busy%
- User%
- Sys%
- Wait%

规则：

- 优先使用 nmon 的 `Busy` 或 `Busy%` 字段。
- 如果没有 Busy，则使用 `100 - Idle%` 或 `100 - Idle`。
- 如果没有 Idle，则使用 `User% + Sys% + Wait%`。
- 使用堆叠面积图展示 User、Sys、Wait。
- Busy 作为独立趋势线叠加显示。
- Y 轴固定为 0% 到 100%。

### 内存图表

图表：

- `内存使用率趋势图`
- `内存明细趋势图`
- `Swap 使用趋势图`

内存使用率优先计算：

```text
Memory Used% = (memtotal - memfree - cached - buffers) / memtotal * 100
```

字段缺失时退化为：

```text
Memory Used% = (memtotal - memfree) / memtotal * 100
```

明细图展示可用/空闲内存、Cached、Buffers，单位 MB。

Swap 图优先展示 Swap Used%，如存在分页相关字段则展示 Swap In、Swap Out。

### 磁盘图表

图表：

- `磁盘 Busy TopN 趋势图`
- `磁盘读写吞吐 TopN 趋势图`
- `磁盘 IOPS TopN 趋势图`

规则：

- Busy TopN 按指定时间段内每块盘 Busy 最大值排序。
- 读写吞吐 TopN 按 read + write 最大值排序。
- IOPS TopN 按 `DISKXFER` 最大值排序。
- DISKREAD、DISKWRITE 原始单位按 KB/s 处理，图中换算为 MB/s。
- 读写吞吐图采用上下镜像展示：Read 在上方，Write 在下方；tooltip 和 Y 轴标签显示正数。

### 网络图表

图表：

- `网络吞吐 TopN 趋势图`
- 可选 `网络带宽使用率趋势图`

规则：

- 网卡 TopN 按 receive + transmit 最大值排序。
- NET 原始单位按 KB/s 处理，图中换算为 MB/s。
- 收发吞吐图采用上下镜像展示：Receive 在上方，Transmit 在下方；tooltip 和 Y 轴标签显示正数。
- 如果配置了 `network_bandwidth_mbps`，计算：

```text
Bandwidth Usage% = Total_MBps * 8 / network_bandwidth_mbps * 100
```

## 前端结构

```text
index.html
assets/app.js
assets/styles.css
sample/
```

`index.html`：

- 页面结构。
- 文件选择、配置表单、汇总表、服务器明细容器。
- 加载 ECharts 和本地应用脚本。

`assets/app.js`：

- nmon CSV 行解析。
- ZZZZ 时间解析。
- section 数据建模。
- 指标计算。
- 汇总表渲染。
- ECharts 配置与事件绑定。
- 图表右键复制。

`assets/styles.css`：

- 页面布局。
- 控件、表格、图表卡片、移动端适配。

## 离线依赖与数据安全

所有 nmon 文件都通过浏览器 File API 在用户本机读取。当前设计不会把文件上传到任何服务器。

需要注意：

- ECharts 已放在 `assets/echarts.min.js`，页面不访问 CDN。
- 第三方依赖为 Apache ECharts 5，License 为 Apache-2.0。

## 验证方式

基础验证：

```bash
node --check assets/app.js
```

浏览器验证：

1. 打开 `index.html`。
2. 选择 `sample/server-a.nmon` 和 `sample/server-b.nmon`。
3. 确认“文件时间与读取范围”表出现两行，并展示整体时间范围。
4. 点击“生成报告”。
5. 确认整体汇总出现两行。
6. 在整体汇总中切换“按读取范围”，输入样例行号范围后确认表格按行号重新计算。
7. 确认 CPU、内存、磁盘、网络图表可见。
8. 缩放图表，确认整体汇总时间范围和数值随之变化。

当前样例的预期冒烟结果：

- `server-a.nmon` 可解析 8 个目标 section。
- `server-a.nmon` 可生成 7 个图表规格。
- `server-a.nmon` 最后一个采样点 CPU Busy 为 `51%`。
- `server-a.nmon` 最后一个采样点 Memory Used 为 `75%`。

## 后续演进约束

- 优先保持纯前端运行，不重新引入后端运行时。
- 不增加构建步骤，除非明确需要组件化或离线打包。
- 新增指标时优先在 `assets/app.js` 中增加独立计算函数，并保持汇总口径可追踪。
- 图表交互应继续保留 dataZoom 联动整体汇总。
- 大型 nmon 样例和生成报告不进入仓库，继续使用 `.gitignore` 排除。
