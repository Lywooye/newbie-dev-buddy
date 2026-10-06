# 小白开发搭子 · Newbie Dev Buddy

[English](README.md)

面向非程序员的 AI 开发工作流：你描述想做什么，AI 提出模块划分和开发方案，你确认后再实施。新项目先设计模块，已有项目先梳理代码；模块结构、已确认方案、实施过程和可选验收证据保存在 Markdown 中，方便下次继续。

这是供 AI 编程助手使用的本地 Skill，安装名和调用名为 `newbie-dev-buddy`，配套 Python CLI 保存记录。

**v0.3.0 为实验版本。** 当前验证来自合成项目和外部 Kit 小样例，尚未在用户生产项目中评估，也没有优于其他工具的比较证据。生成的流程正文目前为中文；用户输入的名称、契约、方案和说明保留原语言。

## 它解决什么

- **新项目先设计模块。** AI 根据需求提出各模块的职责、输入输出和关系，用易懂的说明供你确认；确认后通过 `init` 保存初始结构。代码路径可以尚未存在，计划与已实现状态分开记录；CLI 本身不设计架构。
- **从现有代码开始。** `scan` 保存结构清单和来源指纹；AI 或贡献者核对源码、按职责分组；`map-propose` 展示候选地图、差异、未分配文件和路径重叠。Python 可提取符号和导入语法事实，其他语言目前只生成文件清单。CLI 不自动推断业务模块，也不自动重构。
- **结构也有历史。** 确认具体地图版本，保留旧图；改名、移动保留模块 ID，拆分、合并、退休记录对应关系，旧 ID 不重复使用。
- **确认的是具体方案。** 接受前检查完整 Markdown SHA、最新修订和项目基线。新版本替换旧方案时，旧记录仍然保留。
- **按模块选择验收。** 项目默认策略可由模块覆盖，并可配置跨模块检查。方案冻结配置 SHA 和 JSON 内容、步骤及声明输入；有配置时，配置与声明源码、测试须先存在且未被排除，新测试先准备再提案；整项目报告通过不会自动把所有模块标成已检查。
- **状态分开记录。** 接受、实施和验收互不替代，未配置、未检查、部分、失败、历史通过和需重验都应如实显示。
- **复用已有 Kit。** `run-checks` 实际运行选中的 Acceptance Kit 配置；`verify` 复核已有报告。不新建测试引擎、后台服务、账号或数据库。

这些材料便于复核和交接，但不认证人类同意、不阻止直接改文件，也不证明架构合理、影响分析完整或测试覆盖充分。`delivery_ready` 要求必需检查及必需模块相关的已配置接口检查通过；任何已运行检查失败或过期都会阻止门槛满足。没有必需规则时为 `null`，不代表整个项目质量已获证明。

## 要求与安装

- Python 3.9 及以上；核心 CLI 只用标准库。扫描当前需要 macOS 或 Linux 的目录相对读取接口。
- `run-checks` 与 `verify` 可选，需要 Node.js 和可信兼容的 Acceptance Kit。集成使用 Kit 0.1.2，要求 Node.js 22 及以上；仓库不附带或自动安装 Kit。
- 使用代理指令需要支持本地 Skill 的宿主；CLI 也可直接使用。CodeGraph、Understand Anything 是可选分析来源，不是依赖。

把源码放入名为 `newbie-dev-buddy` 的目录，从其父目录安装；脚本拒绝覆盖已有部署：

```sh
(
  set -eu
  skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
  skill_target="$skill_root/newbie-dev-buddy"
  if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
    printf '%s\n' '目标已存在，更新前请检查。' >&2
    exit 1
  fi
  mkdir -p "$skill_root"
  mkdir "$skill_target"
  cp ./newbie-dev-buddy/SKILL.md "$skill_target/"
  cp -R ./newbie-dev-buddy/agents ./newbie-dev-buddy/references \
    ./newbie-dev-buddy/scripts "$skill_target/"
)
```

按宿主说明重新加载 Skill。已由 Skills 管理器部署时，通过管理器更新，不直接覆盖其文件。

## 如何使用

先读 [新手使用指引](references/beginner-guide.md)：包含准备步骤、新建项目、修改项目和换对话继续的提示词。

对目标项目调用 `$newbie-dev-buddy`：

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

梳理默认记录当前实现；建议的架构调整另提修改方案。扫描不安装插件、不执行项目脚本、不转向其他工作区，也不上传源码。

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

详细说明见 [梳理现有项目](references/discovery.md)、[流程](references/workflow.md)、[模块验收](references/verification.md)、[CLI](references/cli.md) 与 [安全边界](SECURITY.md)。

## 开发验证

```sh
python3 -m unittest discover -s tests -v
```

测试使用临时合成项目和模拟决定；Linux CI 使用 Python 3.9 和 3.12。仓库夹具验证 Kit 协议；外部 Kit 小样例不包含在 CI 中，也不证明生产适用性或比较优势。

采用 [MIT 许可证](LICENSE)。
