"""Deterministic module views; preserve supplied prose rather than rewrite facts."""
import hashlib
import json


POLICIES = {"manual": "本次选定后检查", "on-change": "修改涉及它时检查", "required": "涉及本次修改时，交付前必须检查"}


def serialized(mapping):
    return json.dumps(mapping, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def cell(value):
    return str(value).replace("|", "&#124;").replace("\r", " ").replace("\n", "<br>")


def reference(module_id, modules):
    return modules[module_id]["name"] + "（" + module_id + "）"


def check_lines(profile, default):
    policy = profile.get("policy", default)
    lines = ["- 检查安排：" + POLICIES[policy]]
    if "config" not in profile:
        return lines + ["- 检查配置：尚未配置，不能算作通过。"]
    return lines + ["- 配置文件：`" + profile["config"] + "`",
                    "- 必须核对的步骤：" + "、".join(profile["steps"]),
                    "- 必须纳入的测试与输入：" + "、".join(profile["inputs"]),
                    "- 运行结果：本页不记录实时结果，请查看变更记录和验收报告。"]


def map_body(mapping, *, candidate=False):
    modules = {m["id"]: m for m in mapping["modules"]}
    revision = mapping.get("map_revision")
    default = mapping.get("verification_defaults", {}).get("policy", "manual")
    lines = ["# " + mapping.get("title", "项目模块说明"), "",
             "版本：" + (str(revision) if revision is not None else "初始版本"), "",
             ("这是待确认的模块分工，请先核对职责和配合关系。" if candidate else
              "先核对各部分负责什么、怎样配合，再看下面的细节。这里保存的是已确认的安排。") +
             "模块安排不代表功能已经完成或测试已经通过。", "",
             "## 项目分工", "", "| 模块 | 负责什么 | 需要配合哪些模块 |", "|---|---|---|"]
    if not candidate and mapping.get("updated_at"):
        lines[4:4] = ["文档最后更新：" + mapping["updated_at"], ""]
    if not candidate and mapping.get("last_change"):
        last = mapping["last_change"]
        lines[4:4] = ["本次同步对应：" + last["change"] + " r" + str(last["revision"]) +
                      "；具体修改见 [`实施记录`](../../" + last["record"] + ")。", ""]
    for module in mapping["modules"]:
        dependencies = "、".join(reference(i, modules) for i in module.get("depends_on", [])) or "未声明模块依赖"
        lines.append("| " + " | ".join(cell(v) for v in
                     (reference(module["id"], modules), module["purpose"], dependencies)) + " |")
    lines += ["", "## 各模块的详细说明", ""]
    for module in mapping["modules"]:
        lines += ["### " + reference(module["id"], modules), "", "**负责什么**", "", module["purpose"], "",
                  "**需要遵守的约定**", "", module["contract"], "",
                  "**需要配合谁**", ""]
        dependencies = module.get("depends_on", [])
        lines += (["- " + reference(i, modules) for i in dependencies] if dependencies else ["未声明模块依赖，仍需核对实际代码。"])
        lines += ["", "**代码位置**", ""] + ["- `" + p + "`" for p in module["paths"]]
        lines += ["", "路径可以是计划中的位置；路径存在也不能单独证明功能已完成。", "", "**怎样检查**", ""]
        lines += check_lines(module.get("verification", {}), default) + [""]
        if module.get("last_change"):
            last = module["last_change"]
            lines += ["文档同步时间：" + last["at"] + "；对应修改：" + last["change"] + " r" + str(last["revision"]), ""]
        extras = {k: v for k, v in module.items() if k not in
                  {"id", "name", "purpose", "contract", "paths", "depends_on", "verification", "last_change"}}
        if extras:
            lines += ["<details>", "<summary>其他已登记信息（保留原字段）</summary>", "", "```json", serialized(extras).rstrip(), "```", "", "</details>", ""]
    if mapping.get("integration_checks"):
        lines += ["## 模块一起工作时怎样检查", ""]
        for check in mapping["integration_checks"]:
            lines += ["### " + check["id"], "", "涉及模块：" + "、".join(reference(i, modules) for i in check["modules"]), ""]
            lines += check_lines(check, default) + [""]
    if mapping.get("context"):
        lines += ["## 共同需要参考的文件", ""] + ["- `" + p + "`" for p in mapping["context"]] + [""]
    if mapping.get("decision_note"):
        lines += ["## 确认时的说明", "", mapping["decision_note"], ""]
    extras = {k: v for k, v in mapping.items() if k not in
              {"title", "modules", "context", "verification_defaults", "integration_checks",
               "decision_note", "schema", "map_revision", "source_scan", "source_scan_digest", "updated_at", "last_change"}}
    if extras:
        lines += ["<details>", "<summary>其他项目约定（保留原字段）</summary>", "", "```json",
                  serialized(extras).rstrip(), "```", "", "</details>", ""]
    lines += ["## 核对这份分工", "", "- 每部分的职责和约定是否符合你的想法？",
              "- 哪些事情不归它管，是否说清楚了？没写清楚就请助手补充。",
              "- 模块之间怎样配合，有没有遗漏或需要进一步确认的地方？",
              "- 哪些检查尚未配置或尚未运行？不要把它们当成已经通过。", ""]
    return "\n".join(lines).rstrip() + "\n"


def readable_document(mapping, source):
    sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return map_body(mapping) + "\n---\n\n本页由 [MODULES.json](MODULES.json) 自动生成。修改意见交给助手确认后，再同步更新两份文档。\n\n数据指纹：`" + sha + "`\n"
