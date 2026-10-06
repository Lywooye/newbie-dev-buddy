window.BUDDY_DEMO = {
  "scenes": [
    {
      "seconds": 12,
      "title": "你说想法，搭子陪你一步步做。",
      "lead": "用一个书签小项目，把方案、决定和每次实施进展留在项目里。",
      "prompt": "我想做一个书签小助手，能把收藏导出成表格。",
      "answer": "第一版先分成三个小部分：读取数据、生成表格、接收你的操作。",
      "review": "审阅时看：每部分负责什么？哪些事情不归它管？",
      "recordTitle": "先确认三个模块",
      "path": "docs/newbie-dev-buddy/MODULES.md",
      "modules": [
        {
          "id": "M-STORE",
          "name": "书签数据",
          "purpose": "读取书签；不负责筛选或导出。",
          "paths": [
            "src/store.py",
            "data/bookmarks.json"
          ],
          "depends_on": [],
          "contract": "只读 title、url、tag；导出不得修改原始数据。"
        },
        {
          "id": "M-EXPORT",
          "name": "表格导出",
          "purpose": "生成 CSV；不负责保存书签。",
          "paths": [
            "src/export.py"
          ],
          "depends_on": [],
          "contract": "输入书签列表，返回 CSV 文本；表头保持 title,url。"
        },
        {
          "id": "M-APP",
          "name": "使用入口",
          "purpose": "接收选项，连接数据与导出。",
          "paths": [
            "src/app.py"
          ],
          "depends_on": [
            "M-STORE",
            "M-EXPORT"
          ],
          "contract": "结果写到标准输出；不覆盖任何用户文件。"
        }
      ],
      "note": "模块来自实际 init 记录。对话与决定为合成演示中的预设内容。",
      "caption": "你负责目标和取舍，助手解释技术细节；通过搭子流程保存记录。"
    },
    {
      "seconds": 15,
      "title": "第一稿先留下，不急着改代码。",
      "lead": "方案说清楚要改哪些部分，以及什么结果才算完成。",
      "prompt": "帮我增加书签导出功能。",
      "answer": "第一稿准备导出所有书签。修改导出模块和入口；存储模块保持只读。",
      "review": "审阅时看：这是你想要的范围吗？完成条件能实际观察吗？",
      "recordTitle": "方案 r1 · 待审阅",
      "path": ".handoff/newbie-dev-buddy/drafts/C-EXPORT-r1.md",
      "text": "# 增加书签导出选项\n\n## 方案\n\n第一稿：把所有书签导出成 CSV，保留 title,url 表头。\n\n## 验收条件\n\n三条样例书签都出现在 CSV 中，原始数据不变。",
      "note": "propose 生成真实 Markdown 候选。尚未接受，也尚未开始实施。",
      "caption": "先看到候选方案，再决定接受或要求修改。"
    },
    {
      "seconds": 18,
      "title": "不合适，就让它改第二稿。",
      "lead": "保留第一稿与修改理由，第二稿有自己的版本。",
      "prompt": "先不要做。只导出 learning 标签，原始书签不能改。",
      "answer": "第二稿增加标签选项。不传标签仍导出全部；筛选只作用于导出结果。",
      "review": "审阅时看：没有匹配标签时会怎样？原功能是否保留？",
      "recordTitle": "方案 r2 · 修订后",
      "path": ".handoff/newbie-dev-buddy/drafts/C-EXPORT-r2.md",
      "text": "# 增加书签导出选项\n\n## 方案\n\n第二稿：export_csv 增加可选 tag；入口增加 --tag。只筛选导出结果，不改书签数据或存储模块。\n\n## 验收条件\n\n--tag learning 返回两条 learning 书签；无标签返回三条；不存在的标签只有表头；原始数据不变。",
      "note": "第一稿已记录为拒绝，文件未被覆盖；第二稿随后按其完整 SHA 接受。",
      "caption": "修改意见变成新的方案版本，旧的理由仍可查。"
    },
    {
      "seconds": 18,
      "title": "确认这一稿，再按这一稿实施。",
      "lead": "接受、开始实施、完成实施分别留下记录。",
      "prompt": "同意第二稿，只改导出与入口。",
      "answer": "记录 r2 的确认和实施事件；书签数据保持不变。实现后实际运行三种导出。",
      "review": "本例检查：筛选导出、默认导出、没有匹配项，以及原始数据不变。",
      "recordTitle": "实际程序输出",
      "path": "python3 src/app.py --tag learning",
      "text": "title,url\nPython 入门,https://example.org/python\n网页基础,https://example.org/web\n",
      "note": "实际检查：筛选 2 条；默认 3 条；无匹配 0 条。原始数据未改。",
      "caption": "两条 learning 书签出现在 CSV 中；这些结果来自真实程序执行。"
    },
    {
      "seconds": 14,
      "title": "下一次，从记录接着聊。",
      "lead": "新 CLI 进程已读取状态；模型会话的交接需要让助手实际读文件。",
      "prompt": "请先读模块结构、r2 方案和实施记录，告诉我当前状态。",
      "answer": "r2 已实施，r1 已拒绝，原稿仍在。Kit 验收尚未运行，不能说项目已全面验收。",
      "review": "继续提示词示例：先核对记录和当前源码，再继续已确认的范围。",
      "recordTitle": "新进程读取的真实状态",
      "path": "newbie_dev_buddy.py status",
      "states": [
        [
          "当前方案",
          "C-EXPORT · r2"
        ],
        [
          "实施状态",
          "implemented"
        ],
        [
          "Kit 验收",
          "not_run"
        ],
        [
          "旧方案",
          "r1 保留 · 已拒绝"
        ]
      ],
      "text": "MODULES.md → 当前结构\nchanges/C-EXPORT-r2.md → 已接受方案\n.handoff/.../records/ → 实施记录",
      "note": "这里演示文档与 CLI 交接，不冒充真实模型跨会话测试。",
      "caption": "已实施和已验收是两件事；继续工作时把边界一起带上。"
    },
    {
      "seconds": 16,
      "title": "先试一张模块地图。",
      "lead": "基础安装即可开始；CodeGraph 和 Acceptance Kit 可以以后再选。",
      "prompt": "$newbie-dev-buddy\n先梳理这个项目，给我候选模块地图，确认后再保存。",
      "answer": "你负责目标和取舍，助手负责读代码和准备材料。完整演示可在本地复现。",
      "review": "macOS/Linux：Python 3.9+；Windows 完整流程使用 WSL。",
      "recordTitle": "安装与体验",
      "path": "github.com/Lywooye/newbie-dev-buddy",
      "text": "python3 scripts/install.py --agent codex --dry-run\npython3 scripts/install.py --agent codex\n\n在助手中调用 $newbie-dev-buddy\n\n其他助手：见宿主支持说明。",
      "note": "实验版本。演示播放器是展示材料，不是工具自带的应用界面；不代表生产项目评估。",
      "caption": "先看方案，确认再改，留下记录，方便继续。"
    }
  ]
};
