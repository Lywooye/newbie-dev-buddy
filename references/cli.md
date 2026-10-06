# CLI 契约与合成示例

工具为 `scripts/newbie_dev_buddy.py`，核心仅依赖 Python 3.9 及以上标准库。`run-checks` 和 `verify` 另需 Node.js 22+，默认使用随搭子安装的内置 Acceptance Kit；基础规划和记录不需要 Node、npm 或联网。命令从 Skill 源目录调用；示例项目和内容均为合成材料。SHA、扫描文件名和版本号是参数角色示例，实际值从命令返回取得。

`map-json`、`spec-json` 是传输材料，建议放在项目 `.handoff/newbie-dev-buddy/inputs/` 或项目外临时目录，再用正确的调用路径读取。不要把这些生成文件写进正在扫描或验收的源码目录，以免使扫描自己过期。权威内容仍为 `MODULES.md` 和已保存的版本 Markdown。

成功命令在 stdout 返回 JSON；参数或前置条件错误在 stderr 返回 JSON，退出码为 1。已完成但失败或过期的验收记录返回 `ok: false`，退出码为 2。按 JSON 和退出码判断，不只看关键词，不假定所有命令返回相同字段。

## 命令

| 命令 | 必需参数 | 用途 |
|---|---|---|
| `scan` | `--project P` | 保存结构清单；可重复 `--exclude PATH_OR_GLOB`，可设 `--max-bytes N` |
| `map-propose` | `--project P --scan SCAN_REL_PATH --map-json FILE` | 保存绑定扫描与旧图的地图候选；可附 `--lineage-json FILE` |
| `map-decide` | `--project P --revision N --expect-digest SHA --decision accept\|reject --note-file FILE` | 接受或拒绝地图候选，保留结构历史 |
| `init` | `--project P --map-json FILE --decision-note-file FILE` | 保存已接受的初始模块结构 |
| `propose` | `--project P --spec-json FILE` | 保存修改候选及冻结验证计划，分配新修订号 |
| `decide` | `--project P --change C --revision N --decision accept\|reject --expect-digest SHA --note-file FILE` | 校验修改候选并保存决定 |
| `record` | `--project P --change C --revision N --expect-digest SHA --event started\|implemented\|interrupted --note-file FILE` | 对已接受版本记录实施事件 |
| `run-checks` | `--project P --change C --revision N --expect-digest SHA --check-id ID` | 默认运行内置 Kit 的选中配置并核对结果；可重复 `--check-id`，可加 `--kit KIT_DIR` |
| `verify` | `--project P --change C --revision N --expect-digest SHA --receipt REPORT_PATH` | 默认用内置 Kit 核对既有报告；可加 `--check-id ID` 绑定冻结检查，或加 `--kit KIT_DIR` |
| `status` | `--project P` | 只读状态与本地内容指纹，不运行 Kit |
| `refresh` | `--project P` | 重建派生导航索引，不重新梳理代码 |

`scan` 默认单文件上限为 262144 字节（256 KiB），当前需要 macOS/Linux 安全目录相对读取。Python 可提取 AST 符号与导入，其他语言只有清单；动态导入、运行时调用和排除项内容不在覆盖内。它不运行代码，不自动生成业务模块。`map-propose` 使用该清单和经源码核对的人工或 AI 分组结果；详细方法见 [discovery.md](discovery.md)。扫描文件及报告路径相对项目根解析。`--kit` 是可选的可信兼容外部 Kit 目录；未指定时使用内置版本，显式目录错误时失败，不回退。

`map-decide` 与 `decide` 的 SHA 对应待决策候选的完整 Markdown。接受修改后返回 `accepted_digest`，`record`、`run-checks` 和 `verify` 使用已接受版本的 digest，不能假定接受前后相同。手工改写后不能只换 digest 当作原来已接受。

地图接受会校验扫描来源、旧图和最新候选；修改接受会校验方案 digest、最新修订和项目基线。遇到漂移先核对变化，必要时重新扫描、提出候选并确认。

## 模块输入 `map-json`

| 根字段 | 类型 | 含义 |
|---|---|---|
| `title` | 字符串 | 总览标题 |
| `context` | 可选字符串数组 | 项目内上下文相对路径 |
| `modules` | 非空对象数组 | 模块结构 |
| `verification_defaults` | 可选对象 | 默认检查策略，如 `{"policy":"manual"}` |
| `integration_checks` | 可选对象数组 | 跨模块检查 |

| 模块字段 | 类型 | 含义 |
|---|---|---|
| `id` | 字符串 | 稳定 ID，如 `M-EXPORT` |
| `name`、`purpose` | 字符串 | 名称与职责 |
| `paths` | 非空字符串数组 | 项目内文件或目录相对路径；新项目允许尚未存在 |
| `depends_on` | 字符串数组 | 当前模块依赖的其他 ID；无依赖用空数组 |
| `contract` | Markdown 字符串 | 接口、行为及数据约定 |
| `verification` | 可选对象 | 本模块策略及 Kit 配置引用 |

`verification.policy` 为 `manual`、`on-change` 或 `required`。集成项至少引用两个已知模块，策略只能为 `on-change` 或 `required`；检查项和步骤 ID 使用小写字母、数字及连字符。未设时继承项目默认策略；无默认时使用手动策略。有 `config` 时还需非空 `steps` 和 `inputs`。有配置时，配置、声明输入和相关模块源码必须先存在且未被排除；新测试先准备，再运行 `propose`。这些路径必须在项目内；配置使用 Kit 自己的格式，需排除 `.handoff/newbie-dev-buddy/` 或整个 `.handoff`，工具不自动修改配置。

合成地图：

```json
{
  "title": "合成导出项目",
  "context": ["docs/product.md"],
  "verification_defaults": {"policy": "manual"},
  "modules": [
    {
      "id": "M-INGEST",
      "name": "输入读取",
      "purpose": "读取 item_id 与 score 字段",
      "paths": ["src/ingest.py"],
      "depends_on": [],
      "contract": "保留输入记录顺序。"
    },
    {
      "id": "M-EXPORT",
      "name": "表格导出",
      "purpose": "把输入记录写入 CSV",
      "paths": ["src/export.py"],
      "depends_on": ["M-INGEST"],
      "contract": "export.write_table 使用 UTF-8，默认列为 item_id、score。",
      "verification": {
        "policy": "required",
        "config": "checks/export.json",
        "steps": ["export"],
        "inputs": ["src/export.py", "tests/test_export.py"]
      }
    }
  ],
  "integration_checks": [
    {
      "id": "ingest-export",
      "modules": ["M-INGEST", "M-EXPORT"],
      "policy": "on-change",
      "config": "checks/integration.json",
      "steps": ["ingest-export"],
      "inputs": ["src", "tests/test_integration.py"]
    }
  ]
}
```

这是本工具的地图格式，不能直接当作 Kit 配置。先按[Kit 配置格式](../vendor/acceptance-kit/docs/configuration.md)准备真实配置和测试；尚未配置检查时省略 `config`、`steps`、`inputs`，并如实保留未配置状态。内置运行时和策略不产生测试，也不证明覆盖。

项目内不支持软链接、硬链接或特殊文件，如 FIFO。相对路径避免记录机器根目录，但输入与 Kit 结果仍可能包含私密信息；工具不自动匿名化。

## 扫描、地图候选与接受

```sh
python3 scripts/newbie_dev_buddy.py scan --project ./sample-project --exclude private --max-bytes 1048576
```

读取返回的扫描 Markdown 和覆盖记录，结合源码准备 `map.json`。下列 `S-SCAN.md` 是占位名，替换为实际返回路径：

```sh
python3 scripts/newbie_dev_buddy.py map-propose --project ./sample-project --scan .handoff/newbie-dev-buddy/discovery/S-SCAN.md --map-json ./map.json
```

读取完整候选，再展示并确认。用户接受该版本后，保存确认范围到 `map-note.md`：

```sh
python3 scripts/newbie_dev_buddy.py map-decide --project ./sample-project --revision MAP_REVISION --expect-digest MAP_CANDIDATE_SHA --decision accept --note-file ./map-note.md
```

首次接受建立总览；后续接受保留旧地图并更新当前图。拒绝用 `--decision reject` 并保存理由。移除旧 ID 时，`--lineage-json` 文件使用数组：

```json
[
  {"from": ["M-OLD"], "to": ["M-NEW"], "reason": "职责迁移到新的边界"}
]
```

拆分可有多个 `to`，合并可有多个 `from`；退休用空 `to`。改名或移动路径保留原 ID，不要重新编号。

已有已确认结构仍可首次初始化：

```sh
python3 scripts/newbie_dev_buddy.py init --project ./sample-project --map-json ./map.json --decision-note-file ./map-note.md
```

这不替代实际确认；已初始化项目使用地图修订，不重跑 `init` 覆盖历史。

## 修改输入 `spec-json`

| 字段 | 类型 | 含义 |
|---|---|---|
| `id`、`title` | 字符串 | 稳定变更 ID 与标题 |
| `primary` | 字符串 | 主模块 ID |
| `affected` | 字符串数组 | 其他受影响模块；无关联变化用空数组 |
| `location` | 字符串 | 稳定功能或接口名 |
| `plan` | Markdown 字符串 | 完整方案 |
| `acceptance` | Markdown 字符串 | 可观察验收条件 |
| `supersedes` | 可选对象数组 | 替换的旧方案，每项含 `change`、`revision`、`scope` |

```json
{
  "id": "C-001",
  "title": "允许指定导出列顺序",
  "primary": "M-EXPORT",
  "affected": [],
  "location": "export.write_table",
  "plan": "增加可选 columns 参数，仅允许 item_id 和 score 各一次。省略时保留原列顺序，并更新模块契约。",
  "acceptance": "两种合法顺序的表头和数据一致；重复、遗漏、未知列返回明确错误。"
}
```

```sh
python3 scripts/newbie_dev_buddy.py propose --project ./sample-project --spec-json ./spec.json
```

候选关联模块是核查线索。候选保存本次验证计划；检查 ID 包括 `module:M-EXPORT` 与 `integration:ingest-export`。来源、策略、配置与输入需在接受前核对。配置 SHA 和完整 JSON 内容已冻结，开始实施后更换命令须修订再确认，不在运行时偷偷改变。

## 接受与实施

实际变更 ID、修订号和 digest 从命令结果取得。下列大写参数不能直接复制为有效值。

```sh
python3 scripts/newbie_dev_buddy.py decide --project ./sample-project --change C-001 --revision REVISION --decision accept --expect-digest CANDIDATE_MD_SHA --note-file ./accept-note.md
python3 scripts/newbie_dev_buddy.py record --project ./sample-project --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA --event started --note-file ./start-note.md
```

完成实际代码与相关模块文档后：

```sh
python3 scripts/newbie_dev_buddy.py record --project ./sample-project --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA --event implemented --note-file ./implementation-note.md
```

中断使用 `--event interrupted`，记录已改文件、当前行为、未完成部分及恢复步骤。更高修订被接受或旧版被 `supersedes` 替换后，旧版只供历史核对，不能继续实施或验收。

## 实际检查与既有报告复核

用户已选定检查或已确认策略授权运行后：

```sh
python3 scripts/newbie_dev_buddy.py run-checks --project ./sample-project --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA --check-id module:M-EXPORT --check-id integration:ingest-export
```

默认使用内置 Kit，需要 Node.js 22+。这会执行每份选中配置的全部 Kit 步骤，不是沙箱；地图 `steps` 字段指定必须通过的证明步骤，不筛选执行命令。命令拥有调用者权限并继承环境，共享依赖或绝对路径可能影响副本外的文件。先核对 Kit、配置和命令，完整流程见 [verification.md](verification.md)。

项目已有流程生成报告后，只复核相应检查：

```sh
python3 scripts/newbie_dev_buddy.py verify --project ./sample-project --change C-001 --revision REVISION --expect-digest ACCEPTED_MD_SHA --receipt .acceptance/example-run/report.json --check-id module:M-EXPORT
```

报告路径相对项目根，也支持项目内绝对路径。必须是真实 Kit 报告。通过要求报告 `status` 为 `passed`，Kit `check` 返回 `current: true`、`issues: []`，且指定检查的配置、步骤与输入符合冻结计划。模块验收需至少一个 `tap` 或 `checks` 行为步骤提供非空证明，仅 `exit` 步骤不够；命令与输入匹配仍不是语义覆盖证明。

以上两条命令可加 `--kit /path/to/acceptance-kit` 选择可信兼容外部版本。内置 Kit 基于上游 0.1.2 并附本地安全补丁，自报版本仍为 `0.1.2`；来源见 [BUNDLE.json](../vendor/acceptance-kit/BUNDLE.json)。补丁改变 `toolHash`，旧外置收据须指定原 `--kit` 复核，或用内置 Kit 重跑，不能直接登记为新内置版本通过。

省略 `--check-id` 时只核对整体报告；整体报告通过不自动标记各模块通过。`verify` 不运行测试。`status` 不调用 Kit，显示历史结果、内容指纹及需复核提示；继续使用历史结论前再次 `verify`。

```sh
python3 scripts/newbie_dev_buddy.py status --project ./sample-project
python3 scripts/newbie_dev_buddy.py refresh --project ./sample-project
```

状态以本次变更为单位显示各模块或集成检查。`delivery_ready` 只表示已配置必需检查的当前证据门槛；无必需规则也不等于整项目通过。`refresh` 只重建索引，不接受漂移、不运行扫描或 Kit。

地图更新不改写已接受版本的路径范围和历史记录，也不把整体报告升级成模块证据。
