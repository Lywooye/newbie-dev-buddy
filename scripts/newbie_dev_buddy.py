#!/usr/bin/env python3
"""Newbie Dev Buddy: local Markdown plans and optional trusted Kit verification."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import quote

from discovery import collect
from verification import build_plan, check_coverage, config_for_check, profile_files, validate_settings


DOCS = "docs/newbie-dev-buddy"
STATE = ".handoff/newbie-dev-buddy"
MODULE_ID = r"M-[A-Z0-9][A-Z0-9-]{0,47}"
CHANGE_ID = r"C-[A-Za-z0-9][A-Za-z0-9-]{0,47}"
SKIP = {".git", ".handoff", ".acceptance", "__pycache__", ".DS_Store"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    require(path.is_file(), "expected a regular project file")
    require(path.stat().st_nlink == 1, "hard-linked project files are not supported")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_file(value):
    path = Path(value)
    require(path.is_file(), "note must be a regular file")
    value = path.read_text(encoding="utf-8").strip()
    require(value, "note file must not be empty")
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def safe(root, relative):
    require(isinstance(relative, str) and relative, "path must be a nonempty string")
    p = Path(relative)
    require(not p.is_absolute() and ".." not in p.parts and p.parts,
            "use project-relative paths without '..'")
    cursor = root
    for part in p.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), f"symlink is not supported: {relative}")
    require(cursor.resolve().is_relative_to(root), "path leaves project")
    require(not cursor.exists() or cursor.is_file() or cursor.is_dir(), "special project files are not supported")
    if cursor.is_file():
        require(cursor.stat().st_nlink == 1, "hard-linked project files are not supported")
    return cursor


def md(metadata, body):
    return "---\n" + json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n---\n\n" + body.rstrip() + "\n"


def read_md(path):
    require(path.is_file(), "Markdown record must be a regular file")
    require(path.stat().st_nlink == 1, "hard-linked project files are not supported")
    value = path.read_text(encoding="utf-8")
    require(value.startswith("---\n"), f"missing JSON frontmatter: {path.name}")
    header, body = value[4:].split("\n---\n", 1)
    metadata = json.loads(header)
    require(isinstance(metadata, dict), "frontmatter must be a JSON object")
    return metadata, body.lstrip("\n")


def write(root, relative, content, *, new=False):
    target = safe(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    require(not new or not target.exists(), f"record already exists: {relative}")
    fd, temporary = tempfile.mkstemp(prefix=".newbie-dev-buddy-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(root):
    folder = safe(root, STATE)
    folder.mkdir(parents=True, exist_ok=True)
    lock = safe(root, STATE + "/write.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"another writer or interrupted process owns {STATE}/write.lock; inspect its PID before removing it") from None
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "created": now()}))
        yield
    finally:
        lock.unlink()


def validate_map(data):
    require(isinstance(data, dict) and isinstance(data.get("modules"), list) and data["modules"], "modules must be nonempty")
    require(all(isinstance(m, dict) for m in data["modules"]), "each module must be an object")
    require("title" not in data or isinstance(data["title"], str), "title must be a string")
    ids = [m.get("id") for m in data["modules"]]
    require(all(isinstance(i, str) and re.fullmatch(MODULE_ID, i) for i in ids), "invalid module ID")
    require(len(set(ids)) == len(ids), "duplicate module ID")
    for module in data["modules"]:
        for key in ("name", "purpose", "contract"):
            require(isinstance(module.get(key), str) and module[key].strip(), f"missing module {key}")
        require(isinstance(module.get("paths"), list) and module["paths"], "module paths must be nonempty")
        dependencies = module.get("depends_on", [])
        require(isinstance(dependencies, list) and all(d in ids for d in dependencies), "unknown module dependency")
    require(isinstance(data.get("context", []), list), "context must be an array")
    validate_settings(data)


def module_map(root):
    data, _ = read_md(safe(root, DOCS + "/MODULES.md"))
    validate_map(data)
    for item in data["modules"]:
        for path in item["paths"]:
            safe(root, path)
    for path in data.get("context", []):
        safe(root, path)
    return data


def snapshot(root, paths):
    result = {}

    def visit(path):
        rel = path.relative_to(root).as_posix()
        require(not path.is_symlink(), f"symlink in tracked inputs: {rel}")
        if path.is_file():
            result[rel] = digest(path)
        elif path.is_dir():
            result[rel] = "<directory>"
            for child in sorted(path.iterdir()):
                if child.name not in SKIP and not child.name.startswith(".newbie-dev-buddy-"):
                    visit(child)
        elif not path.exists():
            result[rel] = "<missing>"
        else:
            raise ValueError(f"unsupported input: {rel}")

    for path in sorted(set(paths)):
        require(not set(Path(path).parts) & SKIP, "generated records cannot be tracked inputs")
        visit(safe(root, path))
    return result


def changed(before, after):
    require(isinstance(before, dict) and isinstance(after, dict), "input snapshots must be JSON objects")
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def draft_path(change, revision):
    require(re.fullmatch(CHANGE_ID, change), "invalid change ID")
    require(revision >= 1, "revision must be positive")
    return f"{STATE}/drafts/{change}-r{revision}.md"


def accepted_path(change, revision):
    draft_path(change, revision)
    return f"{DOCS}/changes/{change}-r{revision}.md"


def drafts(root, change=None):
    folder = safe(root, STATE + "/drafts")
    items = []
    for path in sorted(folder.glob("*.md")):
        safe(root, path.relative_to(root).as_posix())
        data, _ = read_md(path)
        if change is None or data["id"] == change:
            items.append((data, path))
    return items


def accepted(root, change, revision, expected=None):
    path = safe(root, accepted_path(change, revision))
    data, body = read_md(path)
    require(data.get("decision") == "accept" and data.get("id") == change and data.get("revision") == revision,
            "proposal has not been accepted under this ID and revision")
    if expected is not None:
        require(digest(path) == expected, "accepted revision digest changed")
    original = {k: v for k, v in data.items() if k not in {"decision", "decision_note", "proposal_digest"}}
    source = safe(root, draft_path(change, revision))
    rebuilt = hashlib.sha256(md(original, body).encode()).hexdigest()
    require(rebuilt == data["proposal_digest"] == digest(source), "accepted content differs from the selected proposal")
    return data, path


def replacements(root, change, revision):
    found = []
    for path in sorted(safe(root, DOCS + "/changes").glob("*.md")):
        safe(root, path.relative_to(root).as_posix())
        data, _ = read_md(path)
        if data["id"] == change and data["revision"] > revision:
            found.append({"change": data["id"], "revision": data["revision"], "scope": "newer accepted revision"})
        for previous in data.get("supersedes", []):
            if previous["change"] == change and previous["revision"] == revision:
                found.append({"change": data["id"], "revision": data["revision"], "scope": previous["scope"]})
    return found


def execution_events(root, change, revision):
    events = []
    for path in sorted(safe(root, STATE + "/records").glob("*.md")):
        safe(root, path.relative_to(root).as_posix())
        data, _ = read_md(path)
        if data["id"] == change and data["revision"] == revision:
            events.append((data, path))
    return events


def current_inputs(root, data):
    return snapshot(root, data["tracked_paths"])


def event(root, data, kind, note, **extra):
    history = execution_events(root, data["id"], data["revision"])
    sequence = max((e[0]["sequence"] for e in history), default=0) + 1
    metadata = {"id": data["id"], "revision": data["revision"], "sequence": sequence,
                "event": kind, "created": now(), "inputs": current_inputs(root, data),
                "accepted_digest": digest(safe(root, accepted_path(data["id"], data["revision"]))), **extra}
    path = f"{STATE}/records/{data['id']}-r{data['revision']}-{sequence:06d}-{uuid.uuid4().hex[:8]}.md"
    write(root, path, md(metadata, "# 执行记录\n\n" + note), new=True)
    return path


def verification_status(root, data, events):
    plan = data.get("verification_plan", {"modules": [{"id": i, "policy": "manual", "configured": False}
                                                    for i in [data["primary"]] + data["affected"]], "checks": []})
    checks = []
    for target in plan["checks"]:
        runs = [e[0] for e in events if e[0].get("check_id") == target["id"] and e[0]["event"] == "verification"]
        latest = max(runs, key=lambda e: e["sequence"], default=None)
        item = {"id": target["id"], "modules": target["modules"], "policy": target["policy"], "state": "not_run"}
        if latest:
            receipt = safe(root, latest["receipt"])
            current = not changed(latest["inputs"], current_inputs(root, data)) and receipt.is_file() and digest(receipt) == latest["receipt_digest"]
            item.update(state="stale" if not current else "passed" if latest["result"] == "passed" else "failed",
                        receipt=latest["receipt"], receipt_recheck_required=True,
                        coverage_issues=latest.get("coverage_issues", []))
        checks.append(item)
    modules = []
    for module in plan["modules"]:
        relevant = [c for c in checks if module["id"] in c["modules"]]
        states = [c["state"] for c in relevant]
        state = "not_configured" if not module["configured"] else "not_run"
        if "stale" in states:
            state = "stale"
        elif "failed" in states:
            state = "failed"
        elif states and all(s == "passed" for s in states) and module["configured"]:
            state = "passed"
        elif "passed" in states:
            state = "partial"
        modules.append({**module, "state": state})
    required = [c for c in checks if c["policy"] == "required"]
    required_modules = [m for m in modules if m["policy"] == "required"]
    missing = [m["id"] for m in modules if m["policy"] == "required" and not m["configured"]]
    ready = all(m["state"] == "passed" for m in required_modules) and all(c["state"] == "passed" for c in required) if required or required_modules else None
    if ready and any(c["state"] in {"failed", "stale"} for c in checks):
        ready = False
    return {"modules": modules, "checks": checks, "delivery_ready": ready,
            "missing_required": missing, "note": "Recorded checks only; recheck receipts before delivery. No required policy means no delivery gate."}


def status(root):
    mapping = module_map(root)
    decisions, accepted_items = [], []
    for data, path in drafts(root):
        decision_path = safe(root, f"{STATE}/decisions/{data['id']}-r{data['revision']}.md")
        adopted = safe(root, accepted_path(data["id"], data["revision"]))
        item = {"id": data["id"], "revision": data["revision"], "primary": data["primary"],
                "affected": data["affected"], "location": data["location"],
                "path": path.relative_to(root).as_posix(), "digest": digest(path), "decision": "draft"}
        if adopted.exists():
            approved, _ = accepted(root, data["id"], data["revision"])
            item.update(decision="accept", path=adopted.relative_to(root).as_posix(), digest=digest(adopted))
            events = execution_events(root, data["id"], data["revision"])
            last = max((e[0] for e in events), key=lambda e: e["sequence"], default=None)
            implementation = max((e[0] for e in events if e[0]["event"] != "verification"),
                                 key=lambda e: e["sequence"], default=None)
            baseline = last["inputs"] if last else approved["baseline"]
            actual = current_inputs(root, approved)
            if not last:
                actual.pop(adopted.relative_to(root).as_posix(), None)
            differences = changed(baseline, actual)
            item.update(execution=implementation["event"] if implementation else "not_started", drift=differences,
                        supersedes=approved.get("supersedes", []), replaced_by=replacements(root, data["id"], data["revision"]),
                        verification="not_run")
            if last and last["accepted_digest"] != digest(adopted):
                item["drift"].append("<accepted revision digest changed>")
            checks = [e[0] for e in events if e[0]["event"] == "verification"]
            if checks:
                check = max(checks, key=lambda e: e["sequence"])
                receipt = safe(root, check["receipt"])
                stale = changed(check["inputs"], current_inputs(root, approved))
                item.update(verification=check["result"], verification_input_changes=stale,
                            receipt=check["receipt"], receipt_file_current=receipt.is_file() and digest(receipt) == check["receipt_digest"],
                            receipt_recheck_required=True)
            item["module_verification"] = verification_status(root, approved, events)
            accepted_items.append(item)
        elif decision_path.exists():
            decision, _ = read_md(decision_path)
            item["decision"] = decision["decision"]
        else:
            item["drift"] = changed(data["baseline"], current_inputs(root, data))
        decisions.append(item)
    return {"modules": mapping["modules"], "map_revision": mapping.get("map_revision"),
            "map_digest": digest(safe(root, DOCS + "/MODULES.md")), "decisions": decisions,
            "accepted": accepted_items, "current": [i for i in accepted_items if not i["replaced_by"]],
            "trust_boundary": "Recorded acceptance is not authenticated; status does not re-run receipt validation."}


def refresh(root):
    data = status(root)
    def link(relative):
        return quote(Path(os.path.relpath(root / relative, root / STATE)).as_posix(), safe="/.-_")

    header = ["# 模块修改交接", "", "此页由记录派生；不要手工改进度。方案接受、实施与验收分别记录。",
              "验收显示历史运行结果；继续依赖它之前仍需复核原始凭据。", "", f"模块总览：[{DOCS}/MODULES.md]({link(DOCS + '/MODULES.md')})", ""]
    body, history = list(header), list(header)
    visible = {(item["id"], item["revision"]) for item in data["current"]}
    latest = {}
    for item in data["decisions"]:
        if item["revision"] > latest.get(item["id"], {}).get("revision", 0):
            latest[item["id"]] = item
    visible.update((item["id"], item["revision"]) for item in latest.values() if item["decision"] == "draft")
    for item in data["decisions"]:
        lines = [f"## {item['id']} r{item['revision']} · {item['location']}", "",
                 f"方案：{item['decision']}；主模块：{item['primary']}；关联：{', '.join(item['affected']) or '无记录'}",
                 f"文档：[{item['path']}]({link(item['path'])})"]
        if item["decision"] == "accept":
            lines.append(f"实施：{item['execution']}；验收历史：{item['verification']}；输入变化：{', '.join(item['drift']) or '未发现（仅跟踪范围）'}")
            if item["replaced_by"]:
                lines.append("旧方案已被替换（不再执行）：" + json.dumps(item["replaced_by"], ensure_ascii=False))
            verification = item["module_verification"]
            lines.append("模块验收：" + ", ".join(f"{m['id']}={m['state']}" for m in verification["modules"]))
            lines.append("交付证据门槛：" + ("未设置" if verification["delivery_ready"] is None else "满足已配置要求（交付前复核凭据）" if verification["delivery_ready"] else "尚未满足"))
        lines.append("")
        history.extend(lines)
        if (item["id"], item["revision"]) in visible:
            body.extend(lines)
    body.append("完整历史：[HISTORY.md](HISTORY.md)")
    write(root, STATE + "/HISTORY.md", "\n".join(history) + "\n")
    write(root, STATE + "/CURRENT.md", "\n".join(body) + "\n")
    return data


def map_body(mapping):
    body = ["# " + mapping.get("title", "模块总览"), "", "此表记录已确定的职责和关系；尚未存在的路径代表计划。", ""]
    for module in mapping["modules"]:
        body += [f"## {module['id']} · {module['name']}", "", module["purpose"], "",
                 "路径：" + ", ".join(module["paths"]), "依赖：" + ", ".join(module.get("depends_on", [])), "", module["contract"], ""]
        if module.get("verification"):
            body += ["验收配置：" + json.dumps(module["verification"], ensure_ascii=False, sort_keys=True), ""]
    return "\n".join(body)


def json_input(value):
    path = Path(value)
    require(not path.is_symlink() and path.is_file() and path.stat().st_nlink == 1, "JSON input must be an ordinary unlinked file")
    return json.loads(path.read_text(encoding="utf-8"))


def scan_project(root, args):
    options = {"excludes": args.exclude, "max_bytes": args.max_bytes}
    inventory = collect(root, **options)
    relative = f"{STATE}/discovery/S-{uuid.uuid4().hex}.md"
    body = ["# 现有项目扫描", "", "只提供结构证据；业务模块划分仍需核对代码和用户确认。", "",
            "## 已纳入文件", ""]
    body += ["- " + item["path"] for item in inventory["files"]]
    body += ["", "## 未覆盖", ""]
    body += [f"- {item['path']}: {item['reason']}" for item in inventory["excluded"]]
    body += ["", "## 限制", ""] + ["- " + warning for warning in inventory["warnings"]]
    write(root, relative, md({"schema": 1, "kind": "inventory", "created": now(), "options": options,
                              "inventory": inventory}, "\n".join(body)), new=True)
    return {"path": relative, "digest": digest(safe(root, relative)), "summary": inventory["summary"]}


def map_drafts(root):
    items = []
    for path in sorted(safe(root, STATE + "/maps/drafts").glob("MAP-r*.md")):
        safe(root, path.relative_to(root).as_posix())
        data, body = read_md(path)
        require(data.get("kind") == "module-map" and isinstance(data.get("revision"), int), "invalid map draft")
        items.append((data, body, path))
    return items


def checked_inventory(root, relative, expected=None):
    path = safe(root, relative)
    if expected is not None:
        require(digest(path) == expected, "scan record changed")
    scan, _ = read_md(path)
    require(scan.get("kind") == "inventory" and isinstance(scan.get("options"), dict), "invalid scan record")
    current = collect(root, **scan["options"])
    original = {f["path"]: f["sha256"] for f in scan["inventory"]["files"]}
    actual = {f["path"]: f["sha256"] for f in current["files"]}
    require(not changed(original, actual), "scanned source changed; scan again before accepting a map")
    require(scan["inventory"]["excluded"] == current["excluded"], "scan exclusions changed; scan again")
    return scan["inventory"]


def validate_transition(root, previous, mapping, lineage):
    old = {m["id"]: m for m in previous["modules"]}
    new = {m["id"]: m for m in mapping["modules"]}
    require(isinstance(lineage, list), "lineage must be an array")
    explained = []
    for entry in lineage:
        require(isinstance(entry, dict) and isinstance(entry.get("from"), list) and entry["from"] and
                isinstance(entry.get("to"), list) and isinstance(entry.get("reason"), str) and entry["reason"].strip(), "invalid lineage entry")
        require(all(i in old for i in entry["from"]) and all(i in new for i in entry["to"]), "unknown lineage module")
        require(len(entry["from"]) == len(set(entry["from"])) and len(entry["to"]) == len(set(entry["to"])), "duplicate lineage module")
        explained += entry["from"]
    require(len(explained) == len(set(explained)), "old module appears in multiple lineage entries")
    require(set(old) - set(new) <= set(explained), "removed module IDs need explicit retirement, split or merge lineage")
    retired = set()
    for path in sorted(safe(root, STATE + "/maps/accepted").glob("MAP-r*.md")):
        safe(root, path.relative_to(root).as_posix())
        historical, body = read_md(path)
        require(historical.get("decision") == "accept", "invalid accepted map")
        original = {k: v for k, v in historical.items() if k not in {"decision", "decision_note", "proposal_digest"}}
        source = safe(root, f"{STATE}/maps/drafts/MAP-r{historical['revision']}.md")
        rebuilt = hashlib.sha256(md(original, body).encode()).hexdigest()
        require(rebuilt == historical["proposal_digest"] == digest(source), "accepted map differs from its selected draft")
        retired.update(i for e in historical.get("lineage", []) for i in e["from"] if i not in {m["id"] for m in historical["mapping"]["modules"]})
    require(not (set(new) - set(old)) & retired, "retired module IDs must not be reused")
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
            "changed": sorted(i for i in set(old) & set(new) if old[i] != new[i])}


def candidate_map_body(data):
    body = map_body(data["mapping"]) + "\n\n## 与原图的差异\n\n" + json.dumps(data["difference"], ensure_ascii=False, indent=2, sort_keys=True)
    body += "\n\n## 模块对应关系\n\n" + json.dumps(data["lineage"], ensure_ascii=False, indent=2, sort_keys=True)
    return body + "\n\n## 覆盖与待确认\n\n" + json.dumps(data["coverage"], ensure_ascii=False, indent=2, sort_keys=True)


def propose_map(root, args):
    inventory = checked_inventory(root, args.scan)
    mapping = json_input(args.map_json)
    validate_map(mapping)
    for path in mapping.get("context", []) + [p for m in mapping["modules"] for p in m["paths"]]:
        safe(root, path)
    current_path = safe(root, DOCS + "/MODULES.md")
    previous = module_map(root) if current_path.exists() else {"modules": []}
    new = {m["id"]: m for m in mapping["modules"]}
    lineage = json_input(args.lineage_json) if args.lineage_json else []
    difference = validate_transition(root, previous, mapping, lineage)
    assignments = {}
    for item in inventory["files"]:
        path = item["path"]
        assignments[path] = [m["id"] for m in new.values() if any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in m["paths"])]
    coverage = {"unassigned": [p for p, ids in assignments.items() if not ids],
                "overlapping": {p: ids for p, ids in assignments.items() if len(ids) > 1},
                "excluded": inventory["excluded"]}
    revision = max((d[0]["revision"] for d in map_drafts(root)), default=0) + 1
    relative = f"{STATE}/maps/drafts/MAP-r{revision}.md"
    metadata = {"schema": 1, "kind": "module-map", "revision": revision, "created": now(), "mapping": mapping,
                "scan": args.scan, "scan_digest": digest(safe(root, args.scan)),
                "previous_digest": digest(current_path) if current_path.exists() else None,
                "lineage": lineage, "difference": difference, "coverage": coverage}
    write(root, relative, md(metadata, candidate_map_body(metadata)), new=True)
    return {"path": relative, "revision": revision, "digest": digest(safe(root, relative)), "difference": difference, "coverage": coverage}


def decide_map(root, args):
    path = safe(root, f"{STATE}/maps/drafts/MAP-r{args.revision}.md")
    data, body = read_md(path)
    require(digest(path) == args.expect_digest, "selected map digest changed")
    require(args.revision == max(d[0]["revision"] for d in map_drafts(root)), "a newer map revision exists")
    destination = f"{STATE}/maps/accepted/MAP-r{args.revision}.md"
    rejected = f"{STATE}/maps/rejected/MAP-r{args.revision}.md"
    require(not safe(root, destination).exists() and not safe(root, rejected).exists(), "map revision already has a decision")
    note = text_file(args.note_file)
    if args.decision == "reject":
        write(root, rejected, md({"revision": args.revision, "proposal_digest": args.expect_digest, "created": now()}, "# 模块图拒绝记录\n\n" + note), new=True)
        return {"decision": "reject", "path": rejected}
    checked_inventory(root, data["scan"], data["scan_digest"])
    current = safe(root, DOCS + "/MODULES.md")
    require((digest(current) if current.exists() else None) == data["previous_digest"], "current module map changed; revise the candidate")
    mapping = data["mapping"]
    validate_map(mapping)
    previous = module_map(root) if current.exists() else {"modules": []}
    difference = validate_transition(root, previous, mapping, data["lineage"])
    require(difference == data["difference"], "map difference no longer matches the candidate")
    require(body == candidate_map_body(data).rstrip() + "\n", "candidate body differs from module data; propose again")
    for p in mapping.get("context", []) + [p for m in mapping["modules"] for p in m["paths"]]:
        safe(root, p)
    changes_folder = safe(root, DOCS + "/changes")
    require(not changes_folder.exists() or changes_folder.is_dir(), "module changes path must be a directory")
    for relative in (STATE + "/CURRENT.md", STATE + "/HISTORY.md"):
        target = safe(root, relative)
        require(not target.exists() or target.is_file(), "index path must be a regular file")
    if current.exists():
        status(root)  # Refuse malformed old records before applying the new map.
    if current.exists():
        backup = f"{STATE}/maps/history/{data['previous_digest']}.md"
        if not safe(root, backup).exists():
            write(root, backup, current.read_text(encoding="utf-8"), new=True)
        require(digest(safe(root, backup)) == data["previous_digest"], "previous map archive changed")
    else:
        require(not safe(root, DOCS).exists(), "module documentation already exists without MODULES.md; inspect before accepting")
    data.update(decision="accept", decision_note=note, proposal_digest=args.expect_digest)
    mapping = dict(mapping, schema=1, map_revision=args.revision, decision_note=note, source_scan=data["scan"],
                   source_scan_digest=data["scan_digest"])
    created_folder = not safe(root, DOCS).exists()
    try:
        changes_folder.mkdir(parents=True, exist_ok=True)
        write(root, destination, md(data, body), new=True)
        write(root, DOCS + "/MODULES.md", md(mapping, map_body(mapping)))
    except (OSError, ValueError):
        decision_path = safe(root, destination)
        if decision_path.exists():
            decision_path.unlink()
        if created_folder:
            if changes_folder.exists() and not any(changes_folder.iterdir()):
                changes_folder.rmdir()
            folder = safe(root, DOCS)
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        raise
    return {"decision": "accept", "path": destination, "module_document": DOCS + "/MODULES.md",
            "map_digest": digest(current), "note": "Existing proposal scopes stay frozen; map updates may require re-evaluation."}


def initialize(root, args):
    require(Path(args.map_json).is_file(), "module map input must be a regular file")
    mapping = json.loads(Path(args.map_json).read_text(encoding="utf-8"))
    validate_map(mapping)
    for module in mapping["modules"]:
        for path in module["paths"]:
            safe(root, path)
    for path in mapping.get("context", []):
        safe(root, path)
    require(not safe(root, DOCS).exists(), "module documentation already exists; reuse it instead of overwriting")
    mapping.update(schema=1, decision_note=text_file(args.decision_note_file))
    safe(root, DOCS + "/changes").mkdir(parents=True)
    write(root, DOCS + "/MODULES.md", md(mapping, map_body(mapping)), new=True)
    return {"module_document": DOCS + "/MODULES.md"}


def propose(root, args):
    require(Path(args.spec_json).is_file(), "proposal input must be a regular file")
    spec = json.loads(Path(args.spec_json).read_text(encoding="utf-8"))
    require(isinstance(spec, dict), "proposal must be an object")
    change = spec.get("id", "")
    require(isinstance(change, str) and re.fullmatch(CHANGE_ID, change), "invalid change ID")
    mapping = module_map(root)
    modules = {m["id"]: m for m in mapping["modules"]}
    primary, affected = spec.get("primary"), spec.get("affected", [])
    require(isinstance(affected, list) and primary in modules and all(m in modules for m in affected), "unknown affected module")
    require(primary not in affected and len(set(affected)) == len(affected), "affected modules must be unique and exclude primary")
    for key in ("title", "location", "plan", "acceptance"):
        require(isinstance(spec.get(key), str) and spec[key].strip(), f"missing proposal {key}")
    supersedes = spec.get("supersedes", [])
    require(isinstance(supersedes, list), "supersedes must be an array")
    for previous in supersedes:
        require(isinstance(previous, dict) and isinstance(previous.get("scope"), str) and previous["scope"].strip(), "replacement scope required")
        accepted(root, previous["change"], previous["revision"])
    revision = max((d[0]["revision"] for d in drafts(root, change)), default=0) + 1
    scope = [primary] + affected
    verification_plan = build_plan(mapping, scope)
    for check in verification_plan["checks"]:
        profile_files(check, root)
        check["config_digest"] = digest(safe(root, check["config"]))
        check["config_snapshot"] = config_for_check(check, root)
    check_paths = [p for c in verification_plan["checks"] for p in [c["config"]] + c["inputs"] + c["source_paths"]]
    paths = sorted(set([DOCS] + mapping.get("context", []) + [p for m in scope for p in modules[m]["paths"]] + check_paths))
    metadata = {"schema": 1, "id": change, "revision": revision, "title": spec["title"],
                "primary": primary, "affected": affected, "location": spec["location"],
                "supersedes": supersedes, "created": now(), "tracked_paths": paths, "baseline": snapshot(root, paths),
                "map_digest": digest(safe(root, DOCS + "/MODULES.md")), "verification_plan": verification_plan}
    body = f"# {spec['title']}\n\n## 方案\n\n{spec['plan']}\n\n## 验收条件\n\n{spec['acceptance']}\n"
    if verification_plan["checks"] or any(m["policy"] != "manual" for m in verification_plan["modules"]):
        body += "\n## 模块验收计划\n\n" + json.dumps(verification_plan, ensure_ascii=False, indent=2) + "\n"
    relative = draft_path(change, revision)
    write(root, relative, md(metadata, body), new=True)
    candidates = {primary}
    while True:
        expanded = candidates | {m["id"] for m in modules.values() if set(m.get("depends_on", [])) & candidates}
        if expanded == candidates:
            break
        candidates = expanded
    return {"change": change, "revision": revision, "path": relative, "digest": digest(safe(root, relative)),
            "review_candidates": sorted(candidates - set(scope)), "coverage_note": "Dependency candidates are not an exhaustive impact analysis."}


def decide(root, args):
    path = safe(root, draft_path(args.change, args.revision))
    data, body = read_md(path)
    require(digest(path) == args.expect_digest, "selected proposal digest changed")
    require(args.revision == max(d[0]["revision"] for d in drafts(root, args.change)), "a newer proposal revision exists")
    destination = accepted_path(args.change, args.revision)
    rejection = f"{STATE}/decisions/{args.change}-r{args.revision}.md"
    require(not safe(root, destination).exists() and not safe(root, rejection).exists(), "revision already has a decision")
    note = text_file(args.note_file)
    if args.decision == "accept":
        require(not changed(data["baseline"], current_inputs(root, data)), "proposal baseline changed; revise before acceptance")
        data.update(decision="accept", decision_note=note, proposal_digest=args.expect_digest)
        write(root, destination, md(data, body), new=True)
        return {"path": destination, "accepted_digest": digest(safe(root, destination))}
    write(root, rejection, md({"id": args.change, "revision": args.revision, "decision": "reject", "created": now(),
                              "proposal_digest": args.expect_digest}, "# 用户决定\n\n" + note), new=True)
    return {"decision": "reject", "path": rejection}


def record(root, args):
    data, path = accepted(root, args.change, args.revision, args.expect_digest)
    require(not replacements(root, args.change, args.revision), "accepted revision has been replaced; use the current proposal")
    history = execution_events(root, args.change, args.revision)
    last = max((e[0] for e in history), key=lambda e: e["sequence"], default=None)
    if args.event == "started":
        require(last is None or last["event"] in {"interrupted", "implemented", "verification"}, "execution is already started")
        before = last["inputs"] if last else data["baseline"]
        after = current_inputs(root, data)
        if not last:
            after.pop(path.relative_to(root).as_posix(), None)
        require(not changed(before, after), "inputs changed since selected baseline; inspect and revise or restore before starting")
    else:
        require(last is not None and last["event"] == "started", "record started before implementation or interruption")
    relative = event(root, data, args.event, text_file(args.note_file))
    return {"event": args.event, "path": relative}


def verification_context(root, args):
    data, _ = accepted(root, args.change, args.revision, args.expect_digest)
    require(not replacements(root, args.change, args.revision), "accepted revision has been replaced; use the current proposal")
    history = execution_events(root, args.change, args.revision)
    last = max((e[0] for e in history), key=lambda e: e["sequence"], default=None)
    require(last is not None and last["event"] in {"implemented", "verification"}, "record implemented before verification")
    require(not changed(last["inputs"], current_inputs(root, data)), "inputs changed after implementation record")
    return data


def selected_check(data, check_id):
    plan = data.get("verification_plan", {"checks": []})
    found = next((c for c in plan["checks"] if c["id"] == check_id), None)
    require(found is not None, "check is not in the accepted verification plan")
    return found


def kit_entry(value=None):
    require(value is None or isinstance(value, str) and bool(value), "explicit --kit directory must not be empty")
    kit_root = (Path(value).expanduser().resolve() if value is not None else
                Path(__file__).resolve().parents[1] / "vendor/acceptance-kit")
    kit = kit_root / "bin/acceptance.mjs"
    require(kit.is_file(), "Acceptance Kit entrypoint not found")
    if value is None:
        bundle = json.loads(safe(kit_root, "BUNDLE.json").read_text(encoding="utf-8"))
        files = bundle.get("files") if isinstance(bundle, dict) else None
        require(isinstance(files, dict) and set(files) ==
                {"package.json", "bin/acceptance.mjs", "lib/acceptance.mjs"},
                "invalid bundled Acceptance Kit manifest")
        require(all(digest(safe(kit_root, name)) == expected for name, expected in files.items()),
                "bundled Acceptance Kit changed; restore the package or explicitly select a trusted --kit")
    return kit


def node_runtime():
    node = shutil.which("node")
    require(node is not None, "Acceptance Kit verification requires Node.js 22+; install it in the same environment")
    completed = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
    version = re.fullmatch(r"v(\d+)\.\d+\.\d+", completed.stdout.strip())
    require(completed.returncode == 0 and version is not None and int(version.group(1)) >= 22,
            "Acceptance Kit verification requires Node.js 22+; basic planning and records do not require Node.js")
    return node


def verify(root, args):
    data = verification_context(root, args)
    receipt_path = Path(args.receipt)
    if receipt_path.is_absolute():
        try:
            receipt_path = receipt_path.relative_to(root)
        except ValueError:
            project_alias = Path(os.path.abspath(Path(args.project).expanduser()))
            receipt_path = receipt_path.relative_to(project_alias)
    receipt = safe(root, receipt_path.as_posix())
    require(receipt.is_file(), "receipt not found")
    kit = kit_entry(args.kit)
    node = node_runtime()
    target = selected_check(data, args.check_id) if getattr(args, "check_id", None) else None
    before = current_inputs(root, data)
    receipt_before = digest(receipt)
    completed = subprocess.run([node, str(kit), "check", "--project", str(root), "--receipt", str(receipt)],
                               capture_output=True, text=True, timeout=60)
    check = json.loads(completed.stdout)
    report = json.loads(receipt.read_text(encoding="utf-8"))
    require(isinstance(check, dict), "invalid Acceptance Kit check response")
    require(isinstance(report, dict), "receipt must be a JSON object")
    require(not changed(before, current_inputs(root, data)) and receipt_before == digest(receipt), "inputs or receipt changed during verification")
    current = completed.returncode == 0 and check.get("current") is True and check.get("issues") == []
    coverage_issues = check_coverage(report, target, root) if target else []
    result = "passed" if current and report.get("status") == "passed" and not coverage_issues else "failed_or_stale"
    note = "Acceptance Kit check（不重新执行测试）：\n\n```json\n" + json.dumps(check, ensure_ascii=False, indent=2) + "\n```"
    extra = {"check_id": target["id"], "modules": target["modules"], "coverage_issues": coverage_issues} if target else {}
    relative = event(root, data, "verification", note, result=result, receipt=receipt.relative_to(root).as_posix(),
                     receipt_digest=digest(receipt), kit_check=check, **extra)
    return {"result": result, "receipt_current": current, "path": relative, "coverage_issues": coverage_issues,
            "check_id": target["id"] if target else None}


def run_checks(root, args):
    data = verification_context(root, args)
    require(len(args.check_id) == len(set(args.check_id)), "duplicate check ID")
    selections = [selected_check(data, i) for i in args.check_id]
    kit = kit_entry(args.kit)
    node = node_runtime()
    # Validate every requested configuration before executing any of its commands.
    for target in selections:
        profile_files(target, root)
    results = []
    for target in selections:
        before = current_inputs(root, data)
        timeout = 60 + sum(s.get("timeoutMs", 180000) / 1000 for s in config_for_check(target, root)["steps"])
        completed = subprocess.run([node, str(kit), "run", "--project", str(root), "--config", target["config"]],
                                   capture_output=True, text=True, timeout=timeout)
        require(not changed(before, current_inputs(root, data)), "inputs changed during check execution")
        receipts = re.findall(r"^(?:passed|failed|incomplete): (.+)$", completed.stdout, re.MULTILINE)
        require(len(receipts) == 1, "Kit did not return one receipt; inspect its run output")
        verification_args = argparse.Namespace(**vars(args))
        verification_args.receipt = receipts[0]
        verification_args.check_id = target["id"]
        results.append(verify(root, verification_args))
    return {"result": "passed" if all(r["result"] == "passed" for r in results) else "failed_or_stale", "checks": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "scan", "map-propose", "map-decide", "propose", "decide", "record", "verify", "run-checks", "status", "refresh"):
        command = commands.add_parser(name)
        command.add_argument("--project", required=True)
        if name == "init":
            command.add_argument("--map-json", required=True)
            command.add_argument("--decision-note-file", required=True)
        if name == "scan":
            command.add_argument("--exclude", action="append", default=[])
            command.add_argument("--max-bytes", type=int, default=262144)
        if name == "map-propose":
            command.add_argument("--map-json", required=True)
            command.add_argument("--scan", required=True)
            command.add_argument("--lineage-json")
        if name == "map-decide":
            command.add_argument("--revision", required=True, type=int)
            command.add_argument("--expect-digest", required=True)
            command.add_argument("--decision", choices=("accept", "reject"), required=True)
            command.add_argument("--note-file", required=True)
        if name == "propose":
            command.add_argument("--spec-json", required=True)
        if name in {"decide", "record", "verify", "run-checks"}:
            command.add_argument("--change", required=True)
            command.add_argument("--revision", required=True, type=int)
            command.add_argument("--expect-digest", required=True)
        if name == "decide":
            command.add_argument("--decision", choices=("accept", "reject"), required=True)
        if name in {"decide", "record"}:
            command.add_argument("--note-file", required=True)
        if name == "record":
            command.add_argument("--event", choices=("started", "implemented", "interrupted"), required=True)
        if name in {"verify", "run-checks"}:
            command.add_argument("--kit", help="trusted external Kit directory; defaults to bundled Acceptance Kit")
        if name == "verify":
            command.add_argument("--receipt", required=True)
            command.add_argument("--check-id")
        if name == "run-checks":
            command.add_argument("--check-id", action="append", required=True)
    args = parser.parse_args()
    try:
        root = Path(args.project).expanduser().resolve(strict=True)
        require(root.is_dir(), "project must be an existing directory")
        if args.command == "status":
            result = status(root)
        else:
            with locked(root):
                action = {"init": initialize, "scan": scan_project, "map-propose": propose_map, "map-decide": decide_map,
                          "propose": propose, "decide": decide, "record": record, "verify": verify, "run-checks": run_checks}
                result = action[args.command](root, args) if args.command != "refresh" else {}
                if safe(root, DOCS + "/MODULES.md").exists():
                    result["status"] = refresh(root)
        passed = args.command not in {"verify", "run-checks"} or result["result"] == "passed"
        print(json.dumps({"ok": passed, **result}, ensure_ascii=False, indent=2))
        if not passed:
            return 2
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
