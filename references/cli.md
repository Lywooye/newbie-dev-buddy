# CLI 契约与合成示例

工具为 `scripts/module_change.py`，仅依赖 Python 3.9 及以上版本的标准库。下列示例从 Skill 目录调用，项目、输入文件和变更内容均为合成材料。真实工作中替换成当前项目及已核对的内容。

成功命令在 stdout 返回 JSON，参数或前置条件错误在 stderr 返回 JSON 并以退出码 1 结束。`verify` 核对失败或凭据过期时仍保存真实结果，在 stdout 返回 `ok: false` 并以退出码 2 结束。按返回内容及退出码判断，不以出现某个关键词代替成功检查。不假设所有命令具有相同的返回字段。

## 命令

| 命令 | 必需参数 | 用途 |
|---|---|---|
| `init` | `--project P --map-json FILE --decision-note-file FILE` | 保存用户已接受的初始模块结构及决策说明 |
| `propose` | `--project P --spec-json FILE` | 保存候选方案；自动分配该变更的新修订号 |
| `decide` | `--project P --change C --revision N --decision accept\|reject --expect-digest SHA --note-file FILE` | 校验候选并记录接受或拒绝 |
| `record` | `--project P --change C --revision N --expect-digest SHA --event started\|implemented\|interrupted --note-file FILE` | 对已接受版本记录实施事件 |
| `verify` | `--project P --change C --revision N --expect-digest SHA --kit KIT_DIR --receipt REPORT_PATH` | 调用 Acceptance Kit `check`，登记真实报告的核对结果 |
| `status` | `--project P` | 只读当前状态；比较内容指纹 |
| `refresh` | `--project P` | 重建派生的 `CURRENT.md` 索引 |

`decide` 的 SHA 对应待决策候选的完整 Markdown。接受后返回 `accepted_digest`；`status.accepted[*].digest` 返回已接受变更的 digest。`record` 与 `verify` 使用这个已接受版本的完整 Markdown SHA，不假定接受前后 digest 相同。手工改写已接受版本后，原 digest 不再代表当前内容，须核查并按修订流程处理。

`decide` 接受前校验方案 digest、最新修订号及项目基线。失败时核对差异和用户接受范围；不能仅替换 digest 绕过旧版本或基线变化。

`verify --receipt` 指向项目内实际的 Kit JSON 报告；相对路径按 `--project` 项目根解析，也支持项目内绝对路径。`--kit` 指向真实的 Acceptance Kit 目录。执行它之前，先使用该 Kit 的文档和项目已有流程运行实际验收。`verify` 不替代那一步。

通过需要真实报告的 `status` 为 `passed`，且 Kit `check` 返回 `current: true`、`issues: []`。`status` 不调用 Kit 重验；它显示历史结果、输入与报告文件的指纹，并提示 `receipt_recheck_required: true`。沿用验收结论前再次执行 `verify`。

更高修订被接受或旧版被其他已接受方案通过 `supersedes` 替换后，旧版保留为历史，不能继续对其执行 `record` 或 `verify`。

## 模块输入 `map-json`

根对象字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `title` | 字符串 | 项目模块总览标题 |
| `context` | 可选字符串数组 | 项目上下文文件的相对路径 |
| `modules` | 模块对象数组 | 已接受的模块结构 |

每个模块的字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 字符串 | 稳定模块 ID，如 `M-EXPORT` |
| `name` | 字符串 | 可读模块名称 |
| `purpose` | 字符串 | 模块职责 |
| `paths` | 字符串数组 | 相对项目根的文件或目录路径；新项目允许路径尚未存在 |
| `depends_on` | 字符串数组 | 此模块依赖的其他模块 ID；无依赖用空数组 |
| `contract` | Markdown 字符串 | 接口、行为与数据约定 |

路径应保持项目内相对路径，不把个人目录、凭据或机器信息放进可分享材料。依赖项应引用当前模块总览中的稳定 ID。

项目内不支持软链接、硬链接或特殊文件（如 FIFO）。生成的交接索引使用相对链接，移动项目后仍可使用；用户输入的方案、说明及 Kit 结果仍可能含私密内容，工具不会自动匿名化这些材料。

合成 `map.json`：

```json
{
  "title": "合成表格导出项目",
  "context": ["docs/product.md"],
  "modules": [
    {
      "id": "M-INGEST",
      "name": "输入读取",
      "purpose": "读取 item_id 与 score 字段",
      "paths": ["src/ingest.py"],
      "depends_on": [],
      "contract": "返回包含 item_id 和 score 的记录；保留输入记录顺序。"
    },
    {
      "id": "M-EXPORT",
      "name": "表格导出",
      "purpose": "把输入记录写入 CSV 文件",
      "paths": ["src/export.py"],
      "depends_on": ["M-INGEST"],
      "contract": "提供 export.write_table；使用 UTF-8；默认列顺序为 item_id、score。"
    },
    {
      "id": "M-CLI",
      "name": "命令行入口",
      "purpose": "接收文件路径并调用导出",
      "paths": ["src/cli.py"],
      "depends_on": ["M-EXPORT"],
      "contract": "成功退出码为 0；--output 指定目标文件。"
    }
  ]
}
```

结构已经向用户展示并获得接受后，把明确的决策说明写入 `decision.md`，再运行：

```sh
python3 scripts/module_change.py init --project ./sample-project --map-json ./map.json --decision-note-file ./decision.md
```

这里的决策说明是执行者对已发生确认的记录；把文件命名为 `decision.md` 不能自行产生用户授权。

## 方案输入 `spec-json`

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | 字符串 | 稳定变更 ID，如 `C-001`；相同 ID 再次提出会生成新修订 |
| `title` | 字符串 | 本次变更标题 |
| `primary` | 字符串 | 主模块 ID |
| `affected` | 字符串数组 | 其他受影响模块 ID；无关联变化用空数组 |
| `location` | 字符串 | 稳定功能或接口名称 |
| `plan` | Markdown 字符串 | 本次完整方案正文 |
| `acceptance` | Markdown 字符串 | 可观察的验收条件 |
| `supersedes` | 可选对象数组 | 被替换的旧方案及范围 |

`supersedes` 的每项包含 `change`（旧变更 ID）、`revision`（旧修订号）和 `scope`（被替换约束的具体范围）。它记录方案中的替换声明，不自动证明关联范围完整或代码已经按新方案实现。

合成 `spec.json`：

```json
{
  "id": "C-001",
  "title": "允许指定导出列顺序",
  "primary": "M-EXPORT",
  "affected": ["M-CLI"],
  "location": "export.write_table",
  "plan": "为 write_table 增加可选 columns 参数，只接受 item_id 和 score 各一次。未指定时保留默认顺序。命令行新增 --columns，以逗号分隔两列。不改变输入读取或 UTF-8 编码。更新 M-EXPORT 与 M-CLI 的契约。",
  "acceptance": "未指定 columns 时输出表头为 item_id,score；指定 score,item_id 时表头和每行数据都按该顺序写出；重复、遗漏或未知列返回明确错误，且不生成成功结果。"
}
```

```sh
python3 scripts/module_change.py propose --project ./sample-project --spec-json ./spec.json
```

`propose` 返回完整候选 Markdown 的 digest 和关系图给出的候选关联模块。读取返回文件，核对方案内容，再向用户展示该变更及修订号。修订输入应是完整的新方案，不是只包含一句修订意见的补丁。

## 接受、实施与验收

下列 SHA 字符串只是说明参数角色，不能直接复制为有效 digest。实际 SHA 从对应命令结果或状态取得。

用户接受 `C-001` 修订 1 后，把确认范围写入 `accept-note.md`：

```sh
python3 scripts/module_change.py decide --project ./sample-project --change C-001 --revision 1 --decision accept --expect-digest CANDIDATE_MD_SHA --note-file ./accept-note.md
```

若用户拒绝，使用 `--decision reject` 并在 note 中保存拒绝理由。若用户修订，更新 `spec.json`，再次运行 `propose`，检查实际新修订号后重新展示。

接受成功后读取已接受 Markdown 的 digest。修改代码前保存开始说明：

```sh
python3 scripts/module_change.py record --project ./sample-project --change C-001 --revision 1 --expect-digest ACCEPTED_MD_SHA --event started --note-file ./start-note.md
```

源代码和模块契约都完成后保存实施说明：

```sh
python3 scripts/module_change.py record --project ./sample-project --change C-001 --revision 1 --expect-digest ACCEPTED_MD_SHA --event implemented --note-file ./implementation-note.md
```

若中断，使用 `--event interrupted`，note 中记录已改文件、当前实际行为、未完成部分及恢复步骤。中断记录不表示实现已经撤回，也不表示变更已被拒绝。

先按真实 Kit 的文档运行项目验收，取得项目内报告，再核对：

```sh
python3 scripts/module_change.py verify --project ./sample-project --change C-001 --revision 1 --expect-digest ACCEPTED_MD_SHA --kit ./acceptance-kit --receipt .acceptance/example-run/report.json
```

以上 receipt 路径相对 `sample-project` 项目根。不要自行构造一份具有 `passed` 状态的文件代替真实 Kit 报告。失败按实际结果保存，不改写为通过。

## 状态与交接

```sh
python3 scripts/module_change.py status --project ./sample-project
```

`status` 只读比较内容指纹；它不会自行刷新索引、接受漂移或重新运行 Kit `check`。指纹变化需要查看具体修改、执行记录与方案的对应关系；历史验收结论需要 `verify` 重新核对。

```sh
python3 scripts/module_change.py refresh --project ./sample-project
```

`refresh` 只用于派生状态索引。它不接受新方案，不核实用户同意，不代替实际实施或验收。对话中交接至少应给出当前模块、适用方案版本、实施状态、当前验收证据及下一步。

## 验收输入与工具限制

生成的 `.handoff/module-change/` 需要从 Acceptance Kit 输入中排除；不要排除全部 `docs/`。更新源代码及模块文档后重新运行 Kit；在报告生成后再改这些输入，会使报告不再代表当前内容。CLI 不自动修改项目的验收配置。

候选关联模块是关系图提供的检查线索。工具不执行 Markdown 中的任意命令，不自动证明 AI 理解，也不能核实人类同意或阻止绕过 CLI 直接改文件。保存的阶段与事件用于可核对的工作记录，不能据此声称全部需求、影响或安全问题已获证明。
