#!/usr/bin/env python3
"""Replay a scripted example using the real Buddy CLI in a fresh folder."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
BUDDY = REPO / "scripts/newbie_dev_buddy.py"
SAMPLE = [
    {"title": "Python 入门", "url": "https://example.org/python", "tag": "learning"},
    {"title": "工作笔记", "url": "https://example.org/notes", "tag": "work"},
    {"title": "网页基础", "url": "https://example.org/web", "tag": "learning"},
]
STORE = '''import json
from pathlib import Path


def load_items():
    source = Path(__file__).resolve().parents[1] / "data/bookmarks.json"
    return json.loads(source.read_text(encoding="utf-8"))
'''
EXPORT = '''import csv
import io


def export_csv(items):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["title", "url"])
    for item in items:
        writer.writerow([item["title"], item["url"]])
    return output.getvalue()
'''
APP = '''from export import export_csv
from store import load_items


if __name__ == "__main__":
    print(export_csv(load_items()), end="")
'''
MAP = {
    "title": "书签小助手 · 合成演示",
    "context": ["requirements.md"],
    "modules": [
        {"id": "M-STORE", "name": "书签数据", "purpose": "读取书签；不负责筛选或导出。",
         "paths": ["src/store.py", "data/bookmarks.json"], "depends_on": [],
         "contract": "只读 title、url、tag；导出不得修改原始数据。"},
        {"id": "M-EXPORT", "name": "表格导出", "purpose": "生成 CSV；不负责保存书签。",
         "paths": ["src/export.py"], "depends_on": [],
         "contract": "输入书签列表，返回 CSV 文本；表头保持 title,url。"},
        {"id": "M-APP", "name": "使用入口", "purpose": "接收选项，连接数据与导出。",
         "paths": ["src/app.py"], "depends_on": ["M-STORE", "M-EXPORT"],
         "contract": "结果写到标准输出；不覆盖任何用户文件。"},
    ],
}


def replay(output):
    if os.name != "posix":
        raise ValueError("Run the complete demo on macOS/Linux or inside WSL.")
    output.mkdir(parents=True, exist_ok=False)
    project = output / "bookmark-project"
    project.mkdir()
    inputs = output / "inputs"
    inputs.mkdir()
    evidence = []

    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def value_file(name, value):
        path = inputs / name
        write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return str(path)

    def call(command, *args):
        run = subprocess.run([sys.executable, str(BUDDY), command, "--project", str(project),
                              *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        if run.returncode:
            raise RuntimeError(run.stderr or run.stdout)
        result = json.loads(run.stdout)
        evidence.append({"command": command, "result": result})
        return result

    def note(name, text):
        path = inputs / (name + ".md")
        write(path, "合成演示中的预设决定，不代表真实用户授权。\n\n" + text + "\n")
        return str(path)

    call("init", "--map-json", value_file("map.json", MAP), "--decision-note-file",
         note("map-decision", "按这三个模块开始，第一版只在本地处理虚构书签。"))
    write(project / "requirements.md", "合成书签工具：本地 CSV 导出，原始数据保持只读。\n")
    write(project / "src/store.py", STORE)
    write(project / "src/export.py", EXPORT)
    write(project / "src/app.py", APP)
    write(project / "data/bookmarks.json", json.dumps(SAMPLE, ensure_ascii=False, indent=2) + "\n")
    original_data = (project / "data/bookmarks.json").read_bytes()
    spec = {"id": "C-EXPORT", "title": "增加书签导出选项", "primary": "M-EXPORT",
            "affected": ["M-APP"], "location": "export.export_csv / app 的导出入口",
            "plan": "第一稿：把所有书签导出成 CSV，保留 title,url 表头。",
            "acceptance": "三条样例书签都出现在 CSV 中，原始数据不变。"}
    first = call("propose", "--spec-json", value_file("proposal-r1.json", spec))
    draft_path = project / first["path"]
    first_digest = hashlib.sha256(draft_path.read_bytes()).hexdigest()
    call("decide", "--change", "C-EXPORT", "--revision", first["revision"],
         "--decision", "reject", "--expect-digest", first["digest"], "--note-file",
         note("request-revision", "先不要做。只导出 learning 标签；不传标签时保留全量导出，原始书签不能改变。"))
    spec.update(plan="第二稿：export_csv 增加可选 tag；入口增加 --tag。只筛选导出结果，不改书签数据或存储模块。",
                acceptance="--tag learning 返回两条 learning 书签；无标签返回三条；不存在的标签只有表头；原始数据不变。")
    second = call("propose", "--spec-json", value_file("proposal-r2.json", spec))
    accepted = call("decide", "--change", "C-EXPORT", "--revision", second["revision"],
                    "--decision", "accept", "--expect-digest", second["digest"],
                    "--note-file", note("accept-r2", "同意第二稿，只改导出与入口。"))
    common = ["--change", "C-EXPORT", "--revision", second["revision"],
              "--expect-digest", accepted["accepted_digest"]]
    call("record", *common, "--event", "started", "--note-file", note("start", "开始实现第二稿。"))
    write(project / "src/export.py", EXPORT.replace("def export_csv(items):", "def export_csv(items, tag=None):")
          .replace("    for item in items:\n", "    for item in items:\n        if tag is not None and item['tag'] != tag:\n            continue\n"))
    write(project / "src/app.py", '''import argparse
from export import export_csv
from store import load_items


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args()
    print(export_csv(load_items(), tag=args.tag), end="")
''')

    def exported(*args):
        text = subprocess.check_output([sys.executable, str(project / "src/app.py"), *args],
                                       text=True, encoding="utf-8")
        return text, list(csv.DictReader(io.StringIO(text)))

    selected_csv, selected = exported("--tag", "learning")
    _, all_items = exported()
    empty_csv, empty = exported("--tag", "missing")
    if ([row["title"] for row in selected] != ["Python 入门", "网页基础"] or len(all_items) != 3
            or empty or not empty_csv.startswith("title,url")
            or (project / "data/bookmarks.json").read_bytes() != original_data):
        raise RuntimeError("The sample does not satisfy its accepted behavior.")
    call("record", *common, "--event", "implemented", "--note-file",
         note("implemented", "完成第二稿。实际运行三种导出并检查原始数据；此演示未接入 Kit，工具验收状态仍为未运行。"))
    resumed = call("status")  # A new CLI process reads records; no model conversation is simulated here.
    current = resumed["current"][0]
    history_kept = hashlib.sha256(draft_path.read_bytes()).hexdigest() == first_digest
    if not (history_kept and current["revision"] == 2 and current["execution"] == "implemented"
            and current["verification"] == "not_run" and not current["drift"]):
        raise RuntimeError("The replay did not preserve its revision and state boundaries.")
    result = {"kind": "scripted-demo-with-real-cli", "modules": MAP["modules"],
              "first_proposal": first, "second_proposal": second, "accepted": accepted,
              "resumed_status": resumed, "selected_csv": selected_csv,
              "checks": {"selected_rows": len(selected), "all_rows": len(all_items), "empty_rows": len(empty),
                         "source_data_unchanged": True, "first_draft_unchanged": history_kept},
              "kit_verification": "not_run", "real_model_session_tested": False,
              "commands": evidence}
    write(output / "evidence.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "project": str(project), "evidence": str(output / "evidence.json"),
                      "checks": result["checks"], "kit_verification": "not_run"}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new folder; existing folders are refused.")
    args = parser.parse_args()
    try:
        replay(args.output)
    except (ValueError, FileExistsError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
