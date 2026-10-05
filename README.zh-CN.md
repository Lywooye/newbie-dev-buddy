# Module Change Workflow（模块变更流程）

[English](README.md)

一个本地 Skill 与 Python CLI，把模块结构、经过确认的变更方案、实施事件和 Acceptance Kit 证据保存在项目 Markdown 中。适合跨会话继续工作，或需要逐版确认方案的项目。

**0.1.1 为实验版本。** 目前只展示了合成场景的行为测试，没有比较实验能证明它提高了交付速度、正确性或安全性。工具生成的流程文档正文目前使用中文；用户输入的名称、契约、方案和说明保留原有语言。

## 能带来什么

- **用稳定 ID 定位模块：** 把职责、路径、依赖和契约连起来；名称或文件位置变化后，仍可按 ID 追溯。模块关系图由用户与代理提出并核对，不会从代码自动发现。
- **确认具体版本：** `decide` 校验候选完整 Markdown 的 SHA-256、最新修订号和跟踪范围内的项目基线。实施记录使用接受后返回的独立摘要。
- **修订不丢历史：** 新方案生成新修订；旧的已接受版本继续保留。`supersedes` 指明替换哪个旧版本、哪些约束。
- **分开记录进度：** 方案接受、实施完成和验收结果各自记录，避免把“同意方案”写成“已经完成”，或把“已经实现”写成“验收通过”。
- **衔接已有证据：** `verify` 调用另行提供的 Acceptance Kit 的 `check`，核对项目中的真实报告并保存结果，不另建一套测试运行器。

这些记录让下一位执行者有具体材料可核对。它不能认证人类同意的真实性、阻止直接改文件、证明模块设计正确，或证明影响与测试已完整覆盖。依赖关系给出的候选模块只是检查线索。

## 环境与安装

- Python 3.9 及以上；CLI 只用标准库。
- 只有可选的 `verify` 需要 Node.js。该集成已用 Acceptance Kit 0.1.2 验证，Kit 需要 Node.js 22 或更新版本。本仓库不附带或安装 Kit，须另行提供兼容且可信的本地副本；其他命令不依赖它。
- 把 `SKILL.md` 用作代理指令时，需要支持本地 Skill 的宿主；也可以直接使用 Python CLI。

下载或复制源码，保存在名为 `module-change-workflow` 的目录中。在它的上级目录执行以下命令，只复制 Skill 文件到根 Skills 目录：

```sh
(
  set -eu
  skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
  skill_target="$skill_root/module-change-workflow"
  if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
    printf '%s\n' '目标已存在；请先检查，再决定如何更新。' >&2
    exit 1
  fi
  mkdir -p "$skill_root"
  mkdir "$skill_target"
  cp ./module-change-workflow/SKILL.md "$skill_target/"
  cp -R ./module-change-workflow/agents ./module-change-workflow/references \
    ./module-change-workflow/scripts "$skill_target/"
)
```

目标目录已存在时不会覆盖。按宿主说明重新加载 Skill，再对相关项目调用 `module-change-workflow`。下文 CLI 命令在源码目录执行。

## 合成示例

这个示例演示如何留存记录，不代表真实用户确认或真实实施。实际工作中，应先核对实现，再向用户展示模块结构和具体方案版本，记录已经发生的决定。写一份说明文件不会自行产生授权。

准备一个已有的 `sample-project` 目录。在源码目录的 `SKILL.md` 旁保存 `map.json`；计划中的模块路径可以尚未存在：

```json
{
  "title": "合成导出项目",
  "modules": [
    {
      "id": "M-EXPORT",
      "name": "导出",
      "purpose": "把记录写入 CSV",
      "paths": ["src/export.py"],
      "depends_on": [],
      "contract": "export.write_table 使用 UTF-8，默认列顺序为 item_id,score。"
    }
  ]
}
```

查看结构后，在 `structure-note.md` 中明确标注本练习的**模拟接受**，再初始化：

```sh
mkdir -p ./sample-project
python3 scripts/module_change.py init --project ./sample-project \
  --map-json ./map.json --decision-note-file ./structure-note.md
```

把下面的完整方案保存为 `spec.json`：

```json
{
  "id": "C-001",
  "title": "允许指定导出列顺序",
  "primary": "M-EXPORT",
  "affected": [],
  "location": "export.write_table",
  "plan": "增加可选 columns 参数，只接受 item_id 与 score 各一次。未指定时保留默认列顺序。",
  "acceptance": "两种合法顺序的表头与每行数据一致；遗漏、重复或未知列返回错误。"
}
```

保存候选，读取命令实际返回的变更 ID、修订号和候选摘要，不假定修订号固定：

```sh
python3 scripts/module_change.py propose --project ./sample-project \
  --spec-json ./spec.json > ./proposal-result.json
python3 -m json.tool ./proposal-result.json
change_id="$(python3 -c 'import json; print(json.load(open("proposal-result.json"))["change"])')"
revision="$(python3 -c 'import json; print(json.load(open("proposal-result.json"))["revision"])')"
candidate_digest="$(python3 -c 'import json; print(json.load(open("proposal-result.json"))["digest"])')"
```

按返回的 `path` 读取完整 Markdown；这个路径相对 `sample-project`。核对完整方案后，在 `accept-note.md` 中写明**模拟接受该具体修订**，再保存决定并读取接受后的新摘要：

```sh
python3 scripts/module_change.py decide --project ./sample-project \
  --change "$change_id" --revision "$revision" --decision accept \
  --expect-digest "$candidate_digest" --note-file ./accept-note.md > ./accepted-result.json
python3 -m json.tool ./accepted-result.json
accepted_digest="$(python3 -c 'import json; print(json.load(open("accepted-result.json"))["accepted_digest"])')"
```

改项目文件前，把实施范围写入 `start-note.md`，保存开始事件。代码及相关模块契约完成后，把实际变化和未验证范围写入 `implementation-note.md`，再保存实施完成事件：

```sh
python3 scripts/module_change.py record --project ./sample-project \
  --change "$change_id" --revision "$revision" --expect-digest "$accepted_digest" \
  --event started --note-file ./start-note.md

# 在这里实施已确认的方案，并更新相关模块文档。

python3 scripts/module_change.py record --project ./sample-project \
  --change "$change_id" --revision "$revision" --expect-digest "$accepted_digest" \
  --event implemented --note-file ./implementation-note.md
python3 scripts/module_change.py status --project ./sample-project
```

工作中断时用 `interrupted`，说明实际文件、未完成内容和恢复步骤。修订方案时，再次用 `propose` 提交完整的 `spec.json`，查看返回的新修订并重新确认。不要改写已接受文档，也不要把旧版授权扩展到新版。被替换的已接受版本保留为历史，但不能再登记实施或验收事件。

## 可选的 Acceptance Kit 核对

先按可信 Kit 的文档和项目已有流程实际运行验收。运行前完成源代码及模块文档；从 Kit 输入中排除生成的 `.handoff/module-change/`，避免登记结果后立即使报告过期，不要排除全部 `docs/`。CLI 不会修改 Kit 配置。

假设真实报告位于 `sample-project/.acceptance/example-run/report.json`，可信 Kit 位于 `./acceptance-kit`：

```sh
python3 scripts/module_change.py verify --project ./sample-project \
  --change "$change_id" --revision "$revision" --expect-digest "$accepted_digest" \
  --kit ./acceptance-kit --receipt .acceptance/example-run/report.json
```

报告路径相对项目根。`verify` 用 `node` 执行用户指定的 `bin/acceptance.mjs`，这个可执行文件属于信任边界；它不会执行项目测试。通过要求报告的 `status` 为 `passed`，且 Kit 核对返回 `current: true`、`issues: []`。没有 Kit 时保存实施说明与待验项，不构造虚假的通过报告。

`status` 只显示历史验收结果和内容指纹，不重跑 Kit；继续使用旧结果前应再次 `verify`。参数或前置条件错误的退出码为 1；`verify` 完成核对并登记失败或过期结果时，退出码为 2。判断结果时同时查看 JSON 和退出码。

## 文件与命令

| 项目内相对路径 | 用途 |
| --- | --- |
| `docs/module-change/MODULES.md` | 当前模块结构与契约 |
| `docs/module-change/changes/` | 已接受方案版本 |
| `.handoff/module-change/drafts/` | 候选修订，也保留被拒绝的版本 |
| `.handoff/module-change/decisions/` | 拒绝决定 |
| `.handoff/module-change/records/` | 实施、中断与验收事件 |
| `.handoff/module-change/CURRENT.md`、`HISTORY.md` | 派生导航索引 |

备份时同时保留文档与记录目录。只有索引能用 `refresh` 重建；记录目录不是可丢弃的缓存。生成的索引使用相对链接，移动项目后仍可使用。用户输入及 Kit 结果仍可能包含敏感信息或机器路径。工具不保证自动匿名化，分享前应检查内容。

命令包括 `init`、`propose`、`decide`、`record`、`verify`、`status` 和 `refresh`。完整说明见 [CLI 输入与行为](references/cli.md)、[流程规则](references/workflow.md)和[安全边界](SECURITY.md)。

## 开发与测试

```sh
python3 -m unittest discover -s tests -v
```

测试使用临时合成项目和模拟决定。Linux CI 在 Python 3.9 和 3.12 上运行该测试集。这是行为验证，不能证明真实用户授权、生产使用效果或比较性能。

仓库测试用合成 Kit 核对集成协议；另外已在本地用真实 Acceptance Kit 0.1.2 检查合成项目的通过、失败报告及输入变化情况。CI 不提供这个外部 Kit。

采用 [MIT 许可证](LICENSE)。
