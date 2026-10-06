# Agent support / 宿主支持

安装器为选定的助手复制 Skill，并在增强模式下准备 CodeGraph 的 MCP 配置。下表依据官方文档与隔离配置夹具；除另行注明的验证外，不代表已在每个助手中运行模型、发现 Skill 或调用工具。

The installer supports selected-host file installation and optional MCP setup. Documented paths and configuration tests are not live host or model verification.

## 选择安装方式

从本项目源码目录调用，选择实际使用的助手：

```sh
python3 scripts/install.py --list-agents
python3 scripts/install.py --agent codebuddy --dry-run
python3 scripts/install.py --agent codebuddy
```

- `--mode basic` 是默认值，只安装 Skill；`--mode enhanced` 还准备外部 CodeGraph。
- `--scope user` 默认跨项目使用；`--scope project --project /path/to/project` 只安装到指定项目。
- 重复 `--agent` 可明确选择多个助手；不探测后自动配置所有助手。
- `--codegraph /path/to/codegraph` 指定可信的已有程序，不替它升级。
- `--mcp-config /path/to/config.json` 指定要处理的宿主配置；先预览，确认这是该宿主实际加载的文件。
- `--dry-run` 展示操作而不安装、下载或写配置。在交互终端中不带参数启动简短向导；非交互调用须指定助手。

macOS/Linux 可以用 `sh install.sh`；PowerShell 可以用 `.\install.ps1`，参数与 Python 入口相同。例如：

```powershell
.\install.ps1 --agent codebuddy --mode enhanced --dry-run
```

包装脚本不安装 Python 或助手本身。核心项目流程仍要求 macOS/Linux；CI 包含 Windows 安装夹具与 PowerShell 预览，用户 Windows 主机的完整助手会话尚未验证；Windows 的完整工作流请放在同一个 WSL 环境，详见 [CodeGraph 接入](codegraph.md#windows)。

## Host paths and invocation

表中目录后都包含 `newbie-dev-buddy/SKILL.md` 及配套资源；`~` 表示当前用户主目录。存在环境变量或旧版配置时，以安装预览的实际路径为准。

| `--agent` | 用户级 Skill 目录 | 项目级 Skill 目录 | 调用方式与来源 |
|---|---|---|---|
| `codex` | `$CODEX_HOME/skills`，未设置时 `~/.codex/skills` | `.agents/skills` | `$newbie-dev-buddy`；用户级沿用 Codex 兼容目录。[官方说明](https://developers.openai.com/codex/skills) |
| `claude-code` | `~/.claude/skills` | `.claude/skills` | `/newbie-dev-buddy`。[Skills](https://code.claude.com/docs/en/skills) |
| `cursor` | `~/.cursor/skills` | `.cursor/skills` | 在助手中明确要求使用 `newbie-dev-buddy`，或从 Skill 菜单选择。[Skills](https://cursor.com/docs/skills) |
| `windsurf` | 优先已有 `~/.codeium/windsurf/skills`，否则 `~/.config/devin/skills` | 优先已有 `.windsurf/skills`，否则 `.devin/skills` | Cascade 中 `@newbie-dev-buddy`；此适配针对 Cascade。[现官方说明](https://docs.devin.ai/desktop/cascade/skills) |
| `copilot` | `~/.copilot/skills` | `.github/skills` | 此适配针对 **Copilot CLI**，在对话中明确要求使用该 Skill。[Skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) |
| `workbuddy` | `~/.codebuddy/skills` | `.codebuddy/skills` | `/` 列表中选择，或明确要求使用该 Skill；使用官方记录的 CodeBuddy 兼容目录。[项目目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project) |
| `codebuddy` | `~/.codebuddy/skills` | `.codebuddy/skills` | CodeBuddy Code 中 `/newbie-dev-buddy`；IDE 的实际发现需另核对。[Skills](https://www.codebuddy.ai/docs/cli/skills) |
| `opencode` | `~/.config/opencode/skills` | `.opencode/skills` | 明确要求使用该 Skill，助手通过 `skill` 工具读取；不假设有同名斜杠命令。[Skills](https://opencode.ai/docs/skills/) |
| `pi` | `~/.pi/agent/skills` | `.pi/skills` | `/skill:newbie-dev-buddy`；更新后可 `/reload`。[版本化说明](https://github.com/earendil-works/pi/blob/v1.0.4/packages/coding-agent/docs/skills.md) |
| `zcode` | `~/.zcode/skills` | `.zcode/skills` | `$newbie-dev-buddy`，或从 `/` 的 Skills 分组选择；设置中刷新并确认已启用。[Skills](https://zcode.z.ai/en/docs/skill) |
| `deepseek-harness` | `$DSH_HOME/skills`，默认 `~/.dsh/skills` | `.dsh/skills` | `/newbie-dev-buddy`，需所选组成启用 Skill provider 和 loader。[Skill 目录](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md) |
| `trae` | `~/.trae-cn/skills` | `.trae/skills` | 明确要求使用该 Skill。用户目录依据中国版 TraeCode IDE 文档；其他发行版请核对预览。[Skills](https://docs.trae.cn/ide_skills) |

OpenCode 的 `XDG_CONFIG_HOME`、`OPENCODE_CONFIG_DIR`，pi 的 `PI_CODING_AGENT_DIR`，以及 `CODEX_HOME`、`DSH_HOME` 会改变用户目录。安装器不改这些变量或系统 PATH。WorkBuddy 与 CodeBuddy 会共用同一 Skill 目录，不能由两个更新机制分别覆盖；已有不同版本请通过原管理器更新。

## MCP 配置与需要继续完成的步骤

增强模式只处理 CodeGraph 这一项，保留其他服务、模型设置与未知字段。更改已有 JSON 前，备份保存在用户 `~/.newbie-dev-buddy/setup/backups/`，macOS/Linux 目录权限 0700、文件权限 0600；备份可能含宿主凭据，不输出内容，也不放进项目。Windows 下已有配置只生成手动候选，不复制凭据备份；数字权限不能保证 Windows ACL 私密性。安装目录应由用户控制，安装期间不要同时替换目录或修改配置。项目模式给服务参数绑定所选项目；用户模式由宿主提供工作区信息，宿主不提供时应使用明确项目路径的 CLI 工作流，不能猜测当前项目。

| 助手 | 用户级配置 | 项目级配置 | 处理方式与来源 |
|---|---|---|---|
| Codex | `$CODEX_HOME/config.toml` | `.codex/config.toml` | 生成独立 TOML 片段，按当前 Codex 配置或 `codex mcp add` 应用，不重写已有 TOML。[MCP](https://developers.openai.com/codex/mcp) |
| Claude Code | `~/.claude.json` | `.mcp.json` | 严格 JSON 合并 `mcpServers`；宿主信任与批准仍有效。[MCP](https://code.claude.com/docs/en/mcp) |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | 严格 JSON 合并 `mcpServers`。[MCP](https://cursor.com/docs/context/mcp) |
| Windsurf/Cascade | 优先已有 `~/.codeium/windsurf/mcp_config.json`，否则现配置目录的 `mcp_config.json` | 自动路径未确认，生成候选 | 合并 `mcpServers`；现官方页面说明此格式只适用 **legacy Cascade**，新版 Devin Local 使用另一套 CLI 配置，不在此适配范围。[MCP](https://docs.devin.ai/desktop/cascade/mcp) |
| Copilot CLI | `~/.copilot/mcp-config.json` | 优先已有 `.mcp.json` 或 `.github/mcp.json` | 合并 CLI 的 `mcpServers`，不改 VS Code 的 `servers` 配置。[MCP](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) |
| WorkBuddy | `~/.workbuddy/mcp.json` | `.workbuddy/mcp.json` | 合并 `mcpServers`，再在 WorkBuddy 的 MCP 面板核对；不调用 CodeBuddy CLI 冒充配置桌面版。[MCP](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide) |
| CodeBuddy | `~/.codebuddy/.mcp.json`、`~/.codebuddy/mcp.json`、`~/.codebuddy.json` | `.mcp.json`、`mcp.json` | 选该范围内首个已有文件；没有才新建优先文件。合并 `mcpServers`，不新建文件遮蔽已用配置。[MCP](https://www.codebuddy.cn/docs/cli/mcp) |
| OpenCode | 现 `OPENCODE_CONFIG`，或配置目录 `opencode.jsonc` / `opencode.json` | `opencode.jsonc` / `opencode.json` | 原生 `mcp`，`type: local`，`command` 为数组；JSONC 生成候选，不删除注释。[配置](https://opencode.ai/docs/config/)、[MCP](https://opencode.ai/docs/mcp-servers/) |
| pi | `~/.pi/agent/mcp.json` | `.pi/mcp.json` | 原生 `mcpServers` 已核实于 v1.0.4；旧版可能缺失，改用 CLI 而不自动装桥接插件。[MCP](https://github.com/earendil-works/pi/blob/v1.0.4/packages/coding-agent/docs/mcp.md) |
| ZCode | `~/.zcode/cli/config.json` | `.zcode/config.json` | 合并原生 `mcp.servers`；不写通用 `.agents/mcp.json` 冒充一定会加载。[MCP](https://zcode.z.ai/en/docs/mcp-services) |
| DeepSeek Harness | 所选 profile 的 Cordis 配置 | 独立 `--patch` overlay | 生成 JSON 形式的有效 YAML overlay；先选择已有 MCP 客户端插件的 profile，再显式加载，不改 profile 或自动装插件。[MCP](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md) |
| Trae | 全局自动路径未确认，生成候选 | `.trae/mcp.json` | 项目 JSON 可合并；仍需在 IDE 中启用项目级 MCP，全局候选在设置中手动添加。[MCP](https://docs.trae.cn/ide_add-mcp-servers) |

无法安全自动应用时，候选保存在 `~/.newbie-dev-buddy/setup/<agent>/`，文件扩展名为 `.json`、`.toml` 或 `.patch.yml`，以实际输出为准。安装器可能返回 **退出码 2** 表示还需手动配置；这不同于安装出错，也不能称为连接完成。

DeepSeek overlay 示例：先确认所选 profile 中官方 `@deepseek-ai/dsh-mcp-client` 可解析，再按安装器返回的候选路径启动：

```sh
dsh --profile PROFILE_NAME --patch /path/to/codegraph.patch.yml
```

这条命令启动助手；安装器不会执行它。不要把普通插件加入 `dsh.profile.bundles`，也不要覆盖现有 profile 的完整配置。若插件缺失，先按该助手官方说明处理，或继续基础 CLI 流程。

pi 的旧版或已加载第三方 `/mcp` 扩展，可能不读取新版原生 `mcp.json`。新版可用 `/mcp` 检查；外部配置变化后用 `/reload`。可安装 Skill 不等于 MCP 已启用。

TraeCode CLI 与 IDE 的目录不同：CLI Skill 在 `~/.traecli/skills` / `.traecli/skills`，全局 MCP 使用 `trae_cli.yaml`；本版 `trae` 适配针对 IDE，不宣称已适配 CLI。[CLI Skill](https://docs.trae.cn/cli_skills)、[CLI MCP](https://docs.trae.cn/cli_model-context-protocol)。

## 怎么确认可用

按层次核对，失败时保留已经完成的部分：

1. **文件就绪：**安装输出给出 Skill 和程序位置，不能只看“复制成功”。
2. **宿主发现：**按宿主说明重新加载，在 Skill 列表或对话中确认它能读到 `SKILL.md`。
3. **工具连接：**应用必要候选，检查 MCP 列表与连接错误；不要为消除错误而放宽权限。
4. **实际调用：**在一个允许分析的项目中，让助手读取一项结构事实，核对返回的是该项目，再继续开发流程。

别把配置夹具、协议握手或单个查询说成所有助手端到端通过。遇到未确认的发行版、路径或能力，生成候选或使用明确的 CLI 指令，不猜测安装目录。
