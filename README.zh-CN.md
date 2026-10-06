# 小白开发搭子 · Newbie Dev Buddy

[English](README.md)

**每次改动 清楚记录**

你说想法，搭子陪你一步步做。**小白开发搭子**让 AI 把技术方案解释清楚，你决定要做什么、哪些先不做；通过搭子流程进行的修改，会留下方案、决定和实施记录，方便下次继续。

![小白开发搭子：每次改动，清楚记录。你说想法，一起定方案，改动留记录。](assets/promo.png)

- **想法有人帮你拆：**让 AI 用日常语言解释各部分负责什么、怎样配合。
- **能提意见：**不合适就改方案，确认你想要的那一版再实施。
- **修改有迹可循：**模块结构、方案版本、决定和实施记录保存在本地 Markdown 中；新方案不会抹掉旧记录。

这是给你现有 AI 编程助手使用的本地 Skill，安装名和调用名为 `newbie-dev-buddy`，配套 Python CLI 保存记录。

[观看 / 下载短视频](assets/demo.mp4) · [自己复现这个例子](examples/bookmark-demo/README.md) · [新手使用指引](references/beginner-guide.md)

<details>
<summary>看看演示画面</summary>

[![书签演示：三个模块、方案修订、实施结果与下次继续。](assets/demo-poster.png)](assets/demo.mp4)

</details>

视频用**预设对话＋真实 CLI 记录与程序结果**演示工作流。演示播放器是展示材料，不是工具自带的界面，也不是真实模型会话录屏。

## 先试一张模块地图

先装**基础版**即可，CodeGraph 和 Acceptance Kit 以后需要时再选。准备能发现本地 Skill、操作项目文件的编程助手，以及 macOS/Linux 上的 Python 3.9+；Windows 完整流程使用 WSL，助手与工具放在同一个 Linux 环境。

已有搭子安装时先检查来源，由管理器管理的安装通过原管理器更新。首次安装到 Codex，下载源码后运行：

```sh
git clone https://github.com/Lywooye/newbie-dev-buddy.git
cd newbie-dev-buddy
python3 scripts/install.py --agent codex --dry-run
python3 scripts/install.py --agent codex
```

随后在 Codex 中打开你要开发的项目，说：

```text
$newbie-dev-buddy
先用我能理解的语言说明这个项目各部分负责什么、怎样配合。
给我候选模块地图，列出待核实的地方，等我确认后再保存。
如果是新项目，先帮我明确第一版要做什么。
```

安装后按输出完成宿主操作，并确认助手确实发现了 Skill。[其他助手与调用方式](references/agent-support.md) · [详细安装说明](#要求与安装)

**v0.4.0 仍是实验版本。** 验证来自合成项目和外部 Kit 小样例，尚未在用户生产项目中评估，也没有优于其他工具的比较证据。流程正文目前为中文；你输入的名称、契约、方案和说明保留原语言。

## 它解决什么

- **新项目先设计模块。** AI 根据需求提出各模块的职责、输入输出和关系，用易懂的说明供你确认；确认后通过 `init` 保存初始结构。代码路径可以尚未存在，计划与已实现状态分开记录；CLI 本身不设计架构。
- **从现有代码开始。** `scan` 保存结构清单和来源指纹；AI 或贡献者核对源码、按职责分组；`map-propose` 展示候选地图、差异、未分配文件和路径重叠。内置扫描提取 Python 语法观察，其他语言生成文件清单；可选 CodeGraph 为 AI 补充多语言结构依据。两者都不能自动确认业务模块，也不自动重构。
- **结构也有历史。** 确认具体地图版本，保留旧图；改名、移动保留模块 ID，拆分、合并、退休记录对应关系，旧 ID 不重复使用。
- **确认的是具体方案。** 接受前检查完整 Markdown SHA、最新修订和项目基线。新版本替换旧方案时，旧记录仍然保留。
- **按模块选择验收。** 项目默认策略可由模块覆盖，并可配置跨模块检查。方案冻结配置 SHA 和 JSON 内容、步骤及声明输入；有配置时，配置与声明源码、测试须先存在且未被排除，新测试先准备再提案；整项目报告通过不会自动把所有模块标成已检查。
- **状态分开记录。** 接受、实施和验收互不替代，未配置、未检查、部分、失败、历史通过和需重验都应如实显示。
- **复用已有 Kit。** `run-checks` 实际运行选中的 Acceptance Kit 配置；`verify` 复核已有报告。不新建测试引擎、后台服务、账号或数据库。

这些材料便于复核和交接，但不认证人类同意、不阻止直接改文件，也不证明架构合理、影响分析完整或测试覆盖充分。`delivery_ready` 要求必需检查及必需模块相关的已配置接口检查通过；任何已运行检查失败或过期都会阻止门槛满足。没有必需规则时为 `null`，不代表整个项目质量已获证明。

## 要求与安装

- Python 3.9 及以上。安装器只用标准库；核心项目流程当前仍需要 macOS/Linux 的安全目录相对读取接口。
- 能发现本地 Skill、操作项目文件的 AI 编程助手。安装器提供 Codex、Claude Code、Cursor、Windsurf/Cascade、Copilot CLI、WorkBuddy、CodeBuddy、OpenCode、pi、ZCode、DeepSeek Harness 和 Trae 的适配。目录、调用方式与限制见[宿主支持](references/agent-support.md)。
- `run-checks` 与 `verify` 可选，需要可信兼容的 Acceptance Kit；独立 Kit 0.1.2 要求 Node.js 22 及以上，本工具不自动安装 Kit。

下载源码，进入目录，先预览你选定的宿主：

```sh
git clone https://github.com/Lywooye/newbie-dev-buddy.git
cd newbie-dev-buddy
python3 scripts/install.py --agent codex --dry-run
python3 scripts/install.py --agent codex
```

**默认基础安装**，只安装搭子。**增强安装**会复用兼容的 CodeGraph；未找到时，下载固定的官方 v1.6.2 发布包并核对 SHA-256，再准备所选宿主的 MCP 配置。不自动升级已有工具，也不自动给项目建索引。

想把增强版装进一个项目，替换示例路径并先预览：

```sh
python3 scripts/install.py --agent opencode --mode enhanced \
  --scope project --project /path/to/project --dry-run
python3 scripts/install.py --agent opencode --mode enhanced \
  --scope project --project /path/to/project
```

在交互终端中不带参数运行，可进入简短安装向导；`--list-agents` 查看可选宿主。`install.sh` 和 `install.ps1` 把同样的参数交给 Python。重复 `--agent` 可选多个宿主，不修改未选宿主。不同的已有部署不会被覆盖；由 Skills 管理器管理的安装，通过原管理器更新。

严格 JSON 的 MCP 文件可以合并，并保留其他设置；TOML、JSONC、DeepSeek overlay 或未确认的全局路径，会生成独立候选文件供手动应用。文件安装、配置应用、MCP 连接、模型实际调用是不同结果；看清安装输出，再按[宿主说明](references/agent-support.md)继续。

**Windows：**提供 PowerShell 包装和 CodeGraph 发布包选择，尚未在真实 Windows 主机验证，也不等于核心流程已原生兼容 Windows。建议在 WSL 内完成整套工作流：助手、Python、搭子和 CodeGraph 都装在同一个 Linux 环境，避免混用 Windows 与 WSL 的程序和项目路径。详见 [CodeGraph 接入](references/codegraph.md)。

## 如何使用

先读 [新手使用指引](references/beginner-guide.md)：包含准备步骤、新建项目、修改项目和换对话继续的提示词。

Codex 中对目标项目调用 `$newbie-dev-buddy`；其他助手使用[对应调用方式](references/agent-support.md#host-paths-and-invocation)：

新项目可以这样开始：

> 我想开发一个工具，实现……。请先帮我明确第一版要做什么，再划分模块、说明它们怎么配合。用我能理解的语言给出方案，确认后再保存结构并开始开发。

已有项目可以这样开始：

> 整理这个项目现在有哪些模块、它们怎么联系。区分代码核实、推断和待核实，列出现有测试及覆盖缺口。先给我候选地图和可选检查，确认后再保存正式结构。

流程为：

```text
明确新项目需求或梳理现有代码 → 提出模块地图 → 接受或修订
→ 提出修改与检查方案 → 接受具体版本
→ 实施 → 运行选中检查 → 复核并保存证据
```

梳理默认记录当前实现；建议的架构调整另提修改方案。扫描不安装插件、不执行项目脚本、不转向其他工作区，也不上传源码。增强安装是另一个明确动作，CodeGraph 的建索引和网络行为有自己的边界。

输入文件、命令和技术字段由 AI 编程助手准备；你主要确认要做什么、会影响什么、怎样判断完成。下面的 CLI 部分供直接调用或排查流程时参考。

## 直接调用 CLI

下面以已有项目为例；新项目确认初始模块后使用 [`init`](references/cli.md#扫描地图候选与接受)。

以下命令从源码目录调用。路径、名称和 SHA 是合成示例，实际扫描路径、修订号与 digest 从 JSON 返回取得。

```sh
python3 scripts/newbie_dev_buddy.py scan --project ./sample-project --exclude private
python3 scripts/newbie_dev_buddy.py map-propose --project ./sample-project \
  --scan .handoff/newbie-dev-buddy/discovery/S-SCAN.md --map-json ./map.json
```

生成的 map/spec JSON 建议放在项目 `.handoff/newbie-dev-buddy/inputs/` 或项目外临时目录，避免写进受检源码使扫描过期；权威内容仍为模块总览和版本 Markdown。

读取完整候选。用户接受该版本后，把实际确认写入 `map-note.md`，使用返回的修订号和 SHA：

```sh
python3 scripts/newbie_dev_buddy.py map-decide --project ./sample-project \
  --revision MAP_REVISION --expect-digest MAP_CANDIDATE_SHA \
  --decision accept --note-file ./map-note.md
```

首次接受建立 `docs/newbie-dev-buddy/MODULES.md`；后续接受保留旧图并更新当前图。说明文件记录已发生的确认，本身不能产生授权。

准备完整 `spec.json`，包含变更 ID、主模块、关联模块、位置、方案和可观察验收条件。依次 `propose`、展示并 `decide`、记录 `started`、实施、记录 `implemented`。字段与合成示例见 [CLI](references/cli.md)。

选中检查已获得授权且有可信 Kit 后：

```sh
python3 scripts/newbie_dev_buddy.py run-checks --project ./sample-project \
  --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA \
  --kit ./acceptance-kit --check-id module:M-EXPORT
```

也可通过项目已有流程先运行 Kit，再复核真实报告：

```sh
python3 scripts/newbie_dev_buddy.py verify --project ./sample-project \
  --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA \
  --kit ./acceptance-kit --receipt .acceptance/example-run/report.json \
  --check-id module:M-EXPORT
```

`run-checks` 先核对冻结配置，再以调用者权限执行选中配置的全部步骤，不是沙箱；开始实施后更换检查命令须修订并确认；`verify` 调用所选 Kit 检查器，但不运行项目测试。先核对 Kit 和配置，从验收输入排除生成的 `.handoff/newbie-dev-buddy/`，同时保留相关文档。没有 Kit 时记录待验项，不制造通过报告。

`status` 只读状态，不重跑 Kit，沿用历史结果前应再次复核。`refresh` 只重建索引，不重新梳理代码。参数错误退出码为 1；已完成但失败或过期的验收退出码为 2，同时检查 JSON 和退出码。

## 记录与交接

当前结构在 `docs/newbie-dev-buddy/MODULES.md`；已接受修改在 `docs/newbie-dev-buddy/changes/`。扫描、地图历史、候选、决定和事件保存在 `.handoff/newbie-dev-buddy/`。两部分一起备份；只有 `CURRENT.md`、`HISTORY.md` 导航索引可以重建。

地图更新不改写已接受方案，也不悄悄扩大旧方案路径范围。未指定检查的整体验证报告作为历史证据保留，不自动分配给各模块。

记录默认留在本地。相对链接便于移动，但输入、文件线索和 Kit 输出仍可能带私密信息；工具不自动匿名化，分享前应检查。

接入的价值在于：把代码结构依据连接到人工决策、Markdown 历史和可选验收。搭子调用外部 CodeGraph，不复制它的引擎，也不替代它的图谱。详细说明见 [CodeGraph 接入](references/codegraph.md)、[宿主支持](references/agent-support.md)、[梳理现有项目](references/discovery.md)、[流程](references/workflow.md)、[模块验收](references/verification.md)、[CLI](references/cli.md) 与 [安全边界](SECURITY.md)。

## 开发验证

```sh
python3 -m unittest discover -s tests -v
```

测试使用临时合成项目和模拟决定；Linux CI 使用 Python 3.9 和 3.12。仓库夹具验证 Kit 协议；外部 Kit 小样例不包含在 CI 中，也不证明生产适用性或比较优势。

采用 [MIT 许可证](LICENSE)。
