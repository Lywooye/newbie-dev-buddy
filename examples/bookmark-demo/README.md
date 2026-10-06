# 书签小助手：每次改动，都有记录

这个例子使用虚构书签，演示三个模块如何配合，以及用户如何把“导出全部书签”的第一稿改成“按标签导出”的第二稿。CLI 真实生成模块、候选、决定、实施与状态记录；对话和决定是预设情境，不冒充真实模型会话或用户授权。

[观看 / 下载视频](../../assets/demo.mp4) · [播放器源码](player.html) · [重录脚本](../../scripts/record_demo.py)

## 自己跑一遍

需要 macOS/Linux 或 WSL、Python 3.9+。不需要模型账号、CodeGraph、Kit 或第三方 Python 包。以下命令从仓库根目录运行，输出目录必须尚不存在：

```sh
python3 examples/bookmark-demo/replay.py --output /tmp/newbie-dev-buddy-bookmark-demo
```

它只创建指定的新目录，不安装 Skill、不改助手配置、不上传数据。重复体验时换一个新的输出目录；脚本拒绝覆盖已有目录。

运行后得到：

```text
newbie-dev-buddy-bookmark-demo/
├── bookmark-project/
│   ├── data/bookmarks.json          # 三条虚构书签
│   ├── src/                         # 可运行的书签程序
│   ├── docs/newbie-dev-buddy/        # 模块结构与已接受的第二稿
│   └── .handoff/newbie-dev-buddy/    # 两稿候选、拒绝理由与实施记录
├── inputs/                          # 演示用的地图、方案与预设决定
└── evidence.json                    # 实际命令结果、状态与行为检查
```

从输出中查看原始 Markdown，而不只看播放器里的节选。`evidence.json` 显示实际 CLI 返回值；演示脚本调用 `init → propose → decide reject → propose → decide accept → record started → record implemented → status`。

## 你会看到什么

| 步骤 | 用户的选择 | 实际留下的材料 |
|---|---|---|
| 先确认结构 | 第一版只做本地书签导出 | 数据、导出、入口三个模块 |
| 审阅第一稿 | 不接受全量导出方案 | r1 候选和拒绝理由 |
| 修改第二稿 | 增加标签筛选，保留默认行为 | r2 候选和接受记录；r1 不被覆盖 |
| 实施 | 只改导出模块和入口 | 开始、完成两类实施事件 |
| 继续 | 先读结构、方案和当前状态 | 新 CLI 进程读取 r2 已实施、Kit 未运行 |

程序实际检查：`--tag learning` 返回两条书签；省略标签返回三条；不存在的标签只返回表头；原始书签数据保持不变。

本例没有接入 Acceptance Kit。行为检查成功不能改写成 Kit 已验收，工具状态仍为 `not_run`，没有整项目质量保证。最后一步验证的是新 CLI 进程读取文件；模型跨对话交接仍需要在助手中实际试用。

## 在你的助手中继续试

打开输出里的 `bookmark-project`，在已安装 Skill 的 Codex 中输入：

```text
$newbie-dev-buddy
这是合成书签演示项目。请先读取 MODULES.md、C-EXPORT-r2.md，
以及 .handoff/newbie-dev-buddy/ 中的实施记录，再核对当前源码。
告诉我已完成什么、还有什么没验收。先不要改代码。
```

这是一段给用户试用的提示词，不是本仓库已完成模型会话测试的声明。其他助手使用各自的调用方式。

## 播放与重录

本地直接打开 `player.html`，可以手动翻页或播放六幕。它是用于说明的展示页面，不是搭子的产品界面。视频有画面字幕、没有旁白；宣传图是品牌插画，不是应用截图。

维护者重录时，先生成新的真实演示证据，再运行：

```sh
# 重录额外需要 Playwright、其 Chromium 浏览器和 FFmpeg。
python3 scripts/record_demo.py --evidence /tmp/newbie-dev-buddy-bookmark-demo/evidence.json
```

此命令更新仓库内的 `demo-data.js`、视频和视频封面，不修改宣传图。运行所需工具须已安装；脚本不自动安装依赖，也不发布任何文件。

## English

This reproducible example uses three fictional bookmarks. Scripted review decisions drive the **real Buddy CLI**: reject an all-items export plan, accept a tag-filtered revision, implement it, and read the records from a new CLI process.

Run `python3 examples/bookmark-demo/replay.py --output /tmp/newbie-dev-buddy-bookmark-demo` from the repository root on macOS/Linux or inside WSL. Choose a new output folder; existing folders are refused. Python 3.9+ is the only replay dependency. No model, CodeGraph, or Acceptance Kit is needed.

The sample runs real behavior checks and retains its first draft. Kit verification remains `not_run`. The captioned video and presentation player are in Chinese. The player is a demonstration surface, not a built-in product UI, a production benchmark, or a live model-session recording. Inspect the generated Markdown and `evidence.json` to verify the underlying results.
