#!/usr/bin/env python3
"""Local Markdown change records; optional verification runs a trusted Kit checker."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import quote


DOCS = "docs/module-change"
STATE = ".handoff/module-change"
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
    fd, temporary = tempfile.mkstemp(prefix=".module-change-", dir=target.parent)
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
                if child.name not in SKIP and not child.name.startswith(".module-change-"):
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
            accepted_items.append(item)
        elif decision_path.exists():
            decision, _ = read_md(decision_path)
            item["decision"] = decision["decision"]
        else:
            item["drift"] = changed(data["baseline"], current_inputs(root, data))
        decisions.append(item)
    return {"modules": mapping["modules"], "decisions": decisions,
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
        lines.append("")
        history.extend(lines)
        if (item["id"], item["revision"]) in visible:
            body.extend(lines)
    body.append("完整历史：[HISTORY.md](HISTORY.md)")
    write(root, STATE + "/HISTORY.md", "\n".join(history) + "\n")
    write(root, STATE + "/CURRENT.md", "\n".join(body) + "\n")
    return data


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
    body = ["# " + mapping.get("title", "模块总览"), "", "此表记录已确定的职责和关系；尚未存在的路径代表计划。", ""]
    for module in mapping["modules"]:
        body += [f"## {module['id']} · {module['name']}", "", module["purpose"], "",
                 "路径：" + ", ".join(module["paths"]), "依赖：" + ", ".join(module.get("depends_on", [])), "", module["contract"], ""]
    safe(root, DOCS + "/changes").mkdir(parents=True)
    write(root, DOCS + "/MODULES.md", md(mapping, "\n".join(body)), new=True)
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
    paths = sorted(set([DOCS] + mapping.get("context", []) + [p for m in scope for p in modules[m]["paths"]]))
    metadata = {"schema": 1, "id": change, "revision": revision, "title": spec["title"],
                "primary": primary, "affected": affected, "location": spec["location"],
                "supersedes": supersedes, "created": now(), "tracked_paths": paths, "baseline": snapshot(root, paths)}
    body = f"# {spec['title']}\n\n## 方案\n\n{spec['plan']}\n\n## 验收条件\n\n{spec['acceptance']}\n"
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


def verify(root, args):
    data, _ = accepted(root, args.change, args.revision, args.expect_digest)
    require(not replacements(root, args.change, args.revision), "accepted revision has been replaced; use the current proposal")
    history = execution_events(root, args.change, args.revision)
    last = max((e[0] for e in history), key=lambda e: e["sequence"], default=None)
    require(last is not None and last["event"] in {"implemented", "verification"}, "record implemented before verification")
    require(not changed(last["inputs"], current_inputs(root, data)), "inputs changed after implementation record")
    receipt_path = Path(args.receipt)
    if receipt_path.is_absolute():
        try:
            receipt_path = receipt_path.relative_to(root)
        except ValueError:
            project_alias = Path(os.path.abspath(Path(args.project).expanduser()))
            receipt_path = receipt_path.relative_to(project_alias)
    receipt = safe(root, receipt_path.as_posix())
    require(receipt.is_file(), "receipt not found")
    kit = Path(args.kit).expanduser().resolve() / "bin/acceptance.mjs"
    require(kit.is_file(), "Acceptance Kit entrypoint not found")
    before = current_inputs(root, data)
    receipt_before = digest(receipt)
    completed = subprocess.run(["node", str(kit), "check", "--project", str(root), "--receipt", str(receipt)],
                               capture_output=True, text=True, timeout=60)
    check = json.loads(completed.stdout)
    report = json.loads(receipt.read_text(encoding="utf-8"))
    require(isinstance(check, dict), "invalid Acceptance Kit check response")
    require(isinstance(report, dict), "receipt must be a JSON object")
    require(not changed(before, current_inputs(root, data)) and receipt_before == digest(receipt), "inputs or receipt changed during verification")
    current = completed.returncode == 0 and check.get("current") is True and check.get("issues") == []
    result = "passed" if current and report.get("status") == "passed" else "failed_or_stale"
    note = "Acceptance Kit check（不重新执行测试）：\n\n```json\n" + json.dumps(check, ensure_ascii=False, indent=2) + "\n```"
    relative = event(root, data, "verification", note, result=result, receipt=receipt.relative_to(root).as_posix(),
                     receipt_digest=digest(receipt), kit_check=check)
    return {"result": result, "receipt_current": current, "path": relative}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "propose", "decide", "record", "verify", "status", "refresh"):
        command = commands.add_parser(name)
        command.add_argument("--project", required=True)
        if name == "init":
            command.add_argument("--map-json", required=True)
            command.add_argument("--decision-note-file", required=True)
        if name == "propose":
            command.add_argument("--spec-json", required=True)
        if name in {"decide", "record", "verify"}:
            command.add_argument("--change", required=True)
            command.add_argument("--revision", required=True, type=int)
            command.add_argument("--expect-digest", required=True)
        if name == "decide":
            command.add_argument("--decision", choices=("accept", "reject"), required=True)
        if name in {"decide", "record"}:
            command.add_argument("--note-file", required=True)
        if name == "record":
            command.add_argument("--event", choices=("started", "implemented", "interrupted"), required=True)
        if name == "verify":
            command.add_argument("--kit", required=True)
            command.add_argument("--receipt", required=True)
    args = parser.parse_args()
    try:
        root = Path(args.project).expanduser().resolve(strict=True)
        require(root.is_dir(), "project must be an existing directory")
        if args.command == "status":
            result = status(root)
        else:
            with locked(root):
                action = {"init": initialize, "propose": propose, "decide": decide, "record": record, "verify": verify}
                result = action[args.command](root, args) if args.command != "refresh" else {}
                result["status"] = refresh(root)
        passed = args.command != "verify" or result["result"] == "passed"
        print(json.dumps({"ok": passed, **result}, ensure_ascii=False, indent=2))
        if not passed:
            return 2
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
