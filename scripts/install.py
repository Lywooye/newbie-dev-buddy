#!/usr/bin/env python3
"""Install a selected host Skill and optionally configure external CodeGraph.

Only standard JSON is merged. Other formats receive a separate candidate file.
No host is launched and no project is indexed by this installer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile

import codegraph_setup

NAME = "newbie-dev-buddy"
NATIVE_WINDOWS = os.name == "nt"
SOURCE = Path(__file__).absolute().parent.parent
# user Skill directory, project Skill directory, user MCP paths, project MCP paths
HOSTS = {
    "codex": (".codex/skills", ".agents/skills", [".codex/config.toml"], [".codex/config.toml"]),
    "claude-code": (".claude/skills", ".claude/skills", [".claude.json"], [".mcp.json"]),
    "cursor": (".cursor/skills", ".cursor/skills", [".cursor/mcp.json"], [".cursor/mcp.json"]),
    "windsurf": (".config/devin/skills", ".devin/skills", [".codeium/windsurf/mcp_config.json", ".config/devin/mcp_config.json"], []),
    "copilot": (".copilot/skills", ".github/skills", [".copilot/mcp-config.json"], [".mcp.json", ".github/mcp.json"]),
    "workbuddy": (".codebuddy/skills", ".codebuddy/skills", [".workbuddy/mcp.json"], [".workbuddy/mcp.json"]),
    "codebuddy": (".codebuddy/skills", ".codebuddy/skills", [".codebuddy/.mcp.json", ".codebuddy/mcp.json", ".codebuddy.json"], [".mcp.json", "mcp.json"]),
    "opencode": (".config/opencode/skills", ".opencode/skills", [".config/opencode/opencode.jsonc", ".config/opencode/opencode.json"], ["opencode.jsonc", "opencode.json"]),
    "pi": (".pi/agent/skills", ".pi/skills", [".pi/agent/mcp.json"], [".pi/mcp.json"]),
    "zcode": (".zcode/skills", ".zcode/skills", [".zcode/cli/config.json"], [".zcode/config.json"]),
    "deepseek-harness": (".dsh/skills", ".dsh/skills", [], []),
    "trae": (".trae-cn/skills", ".trae/skills", [], [".trae/mcp.json"]),
}
ALIASES = {"claude": "claude-code", "github-copilot": "copilot", "dsh": "deepseek-harness", "deepseekharness": "deepseek-harness"}


class InstallError(Exception):
    pass


def safe_path(path):
    """Reject link/reparse ancestors, special files, and multiply linked files."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InstallError("Refusing link/reparse path: " + str(part))
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise InstallError("Refusing special file: " + str(part))
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise InstallError("Refusing hard-linked file: " + str(part))
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise InstallError("Non-directory ancestor: " + str(part))
    return path


def read_regular(path, limit=4 * 1024 * 1024):
    path = safe_path(path)
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise InstallError("Unsafe or oversized file: " + str(path))
        return stream.read(limit + 1)


def write_private(path, data, expected=None):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path.parent)
    if path.exists():
        current = read_regular(path)
        if current == data:
            return
        if expected is None or current != expected:
            raise InstallError("Existing file changed or conflicts: " + str(path))
    elif expected is not None:
        raise InstallError("Configuration disappeared: " + str(path))
    fd, temp = tempfile.mkstemp(prefix=".newbie-dev-buddy-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(path)
        if expected is not None and read_regular(path) != expected:
            raise InstallError("Configuration changed during installation: " + str(path))
        if expected is None and path.exists():
            raise InstallError("Destination appeared during installation: " + str(path))
        os.replace(temp, str(path))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def public_package(source):
    source = safe_path(source)
    entries = read_regular(source / "PUBLIC_FILES.txt").decode("utf-8").splitlines()
    if len(entries) != len(set(entries)) or "SKILL.md" not in entries or "LICENSE" not in entries:
        raise InstallError("Invalid public file manifest")
    package = {}
    for name in entries:
        rel = PurePosixPath(name)
        if not name or rel.is_absolute() or any(x in ("..", ".git") for x in rel.parts) or "\\" in name or ":" in name:
            raise InstallError("Unsafe public file manifest entry")
        if str(rel) != name:
            raise InstallError("Noncanonical public file manifest entry")
        package[name] = read_regular(source / name)
    return package


def copy_skill(source, destination, package, dry_run=False):
    destination = safe_path(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        raise InstallError("Source and installation destination overlap")
    if destination.exists():
        if not destination.is_dir() or any(not (destination / name).exists() or read_regular(destination / name) != data for name, data in package.items()):
            raise InstallError("Existing Skill differs; update through its manager or move it aside: " + str(destination))
        return "unchanged"
    if dry_run:
        return "would_install"
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe_path(destination.parent)
    stage = Path(tempfile.mkdtemp(prefix=".newbie-dev-buddy-", dir=str(destination.parent)))
    try:
        for name, data in package.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        safe_path(destination)
        if destination.exists():
            raise InstallError("Skill destination appeared during installation")
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return "installed"


def environment_path(value, key):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise InstallError(key + " must be an absolute path")
    return path


def paths_for(host, home, project, scope, env):
    user_skill, project_skill, user_configs, project_configs = HOSTS[host]
    root = home if scope == "user" else project
    skill = root / (user_skill if scope == "user" else project_skill) / NAME
    configs = [root / x for x in (user_configs if scope == "user" else project_configs)]
    if scope == "user":
        override = {"codex": ("CODEX_HOME", "skills", "config.toml"), "pi": ("PI_CODING_AGENT_DIR", "skills", "mcp.json"), "deepseek-harness": ("DSH_HOME", "skills", None)}.get(host)
        if override and env.get(override[0]):
            base = environment_path(env[override[0]], override[0])
            skill = base / override[1] / NAME
            configs = [base / override[2]] if override[2] else []
        if host in ("opencode", "windsurf"):
            xdg = environment_path(env.get("XDG_CONFIG_HOME", str(home / ".config")), "XDG_CONFIG_HOME")
            if host == "opencode":
                base = environment_path(env.get("OPENCODE_CONFIG_DIR", str(xdg / "opencode")), "OPENCODE_CONFIG_DIR")
                skill = base / "skills" / NAME
                configs = [environment_path(env["OPENCODE_CONFIG"], "OPENCODE_CONFIG")] if env.get("OPENCODE_CONFIG") else [base / "opencode.jsonc", base / "opencode.json"]
            else:
                if os.name == "nt":
                    base = environment_path(env.get("APPDATA", str(home / "AppData/Roaming")), "APPDATA") / "devin"
                else:
                    base = xdg / "devin"
                configs[-1] = base / "mcp_config.json"
                legacy = home / ".codeium/windsurf/skills"
                skill = (legacy if legacy.exists() else base / "skills") / NAME
    if scope == "project" and host == "windsurf" and (project / ".windsurf/skills").exists():
        skill = project / ".windsurf/skills" / NAME
    # Select the first already-existing config. Never shadow a fallback config.
    config = next((x for x in configs if os.path.lexists(x)), None)
    if config is None and configs:
        config = configs[-1] if host in ("windsurf", "opencode") else configs[0]
    return safe_path(skill), safe_path(config) if config else None


def server_config(host, graph, project=None):
    args = list(graph["args"])
    if project:
        args += ["--path", str(project)]
    env = graph["env"]
    entry = {"command": graph["command"], "args": args, "env": env}
    if host == "opencode":
        return {"mcp": {"codegraph": {"type": "local", "command": [graph["command"], *args], "environment": env, "enabled": True}}}
    if host == "zcode":
        return {"mcp": {"servers": {"codegraph": entry}}}
    if host == "deepseek-harness":
        return [{"insert": [{"id": "newbie-dev-buddy-codegraph", "name": "@deepseek-ai/dsh-mcp-client", "config": {"serverName": "codegraph", "transport": "stdio", **entry}}]}]
    if host in ("claude-code", "codebuddy"):
        entry["type"] = "stdio"
    if host == "copilot":
        entry["tools"] = ["*"]  # Copilot CLI server schema; host approvals still apply.
    return {"mcpServers": {"codegraph": entry}}


def strict_json(data):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("duplicate JSON key")
            obj[key] = value
        return obj
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def configure(host, config, graph, setup_dir, project=None, dry_run=False):
    candidate = server_config(host, graph, project)
    reason = None
    if host == "codex":
        entry = candidate["mcpServers"]["codegraph"]
        # JSON string/array escaping is also valid for these TOML basic strings.
        text = "[mcp_servers.codegraph]\ncommand = " + json.dumps(entry["command"], ensure_ascii=False) + "\nargs = " + json.dumps(entry["args"], ensure_ascii=False) + "\n\n[mcp_servers.codegraph.env]\n"
        text += "".join(key + " = " + json.dumps(value, ensure_ascii=False) + "\n" for key, value in entry["env"].items())
        data, suffix, reason = text.encode("utf-8"), ".toml", "Use codex mcp add with this command, or merge the TOML in your selected config. Existing TOML was not changed."
    else:
        data = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        suffix = ".patch.yml" if host == "deepseek-harness" else ".json"
    if host == "deepseek-harness":
        reason = "Select a DSH profile with the official MCP plugin available, then start with --patch pointing to this overlay; existing profiles were not changed."
    if config is None and reason is None:
        reason = "Apply this candidate in the host MCP settings; an automatic config path is not established for this scope."
    if config is not None and reason is None and config.suffix.lower() != ".json":
        reason = "JSONC or another configuration format requires a manual merge; the original was not changed."
    current = None
    if reason is None:
        if config.exists():
            current = read_regular(config)
            try:
                existing = strict_json(current.decode("utf-8"))
                if not isinstance(existing, dict):
                    raise ValueError("nonobject JSON")
            except (ValueError, UnicodeError):
                reason = "Existing config is JSONC, invalid JSON, or has duplicate keys. Review and merge the separate candidate; original config was not changed."
        else:
            existing = {}
        if reason is None and current is not None and NATIVE_WINDOWS:
            reason = "Existing Windows configuration is preserved; merge manually. The installer does not establish private Windows backup ACLs."
        if reason is None:
            keys = ["mcp", "servers"] if host == "zcode" else ["mcp"] if host == "opencode" else ["mcpServers"]
            # Bare Copilot CLI server objects would be shadowed by adding a wrapper.
            if host == "copilot" and current and "mcpServers" not in existing and existing:
                reason = "Existing Copilot config uses a different layout; merge the candidate manually."
            else:
                container, addition = existing, candidate
                for key in keys:
                    if key in container and not isinstance(container[key], dict):
                        reason = "Existing server container has a different type; merge manually."
                        break
                    container = container.setdefault(key, {})
                    addition = addition[key]
                if reason is None:
                    if "codegraph" in container:
                        if container["codegraph"] == addition["codegraph"]:
                            return {"status": "unchanged", "path": str(config)}
                        reason = "An existing CodeGraph server is preserved. Review the separate candidate before changing it."
                    else:
                        container.update(addition)
                        merged = (json.dumps(existing, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                        if not dry_run:
                            # Secret-bearing backups stay in private user state, outside the project.
                            if current is not None:
                                backup_dir = safe_path(setup_dir / "backups")
                                backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                                os.chmod(backup_dir, 0o700)
                                identity = hashlib.sha256(str(config).encode("utf-8")).hexdigest()[:16]
                                digest = hashlib.sha256(current).hexdigest()[:16]
                                write_private(backup_dir / (identity + "-" + digest + ".bak"), current)
                            write_private(config, merged, expected=current)
                        return {"status": "would_configure" if dry_run else "configured", "path": str(config)}
    output = setup_dir / host / ("codegraph-" + hashlib.sha256(data).hexdigest()[:16] + suffix)
    if not dry_run:
        write_private(output, data)
    return {"status": "manual_required", "candidate": str(output), "target": str(config) if config else None, "reason": reason}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent", action="append", help="Host ID; repeat for explicitly selected hosts")
    p.add_argument("--mode", choices=("basic", "enhanced"), default="basic")
    p.add_argument("--scope", choices=("user", "project"), default="user")
    p.add_argument("--project", type=Path)
    p.add_argument("--home", type=Path, default=Path.home(), help="Installation home (isolated validation or portable installs)")
    p.add_argument("--codegraph", help="Existing CodeGraph executable (never upgraded)")
    p.add_argument("--mcp-config", type=Path, help="Explicit selected host MCP config path; one agent only")
    p.add_argument("--dry-run", action="store_true", help="Print paths/operations without writes, downloads or execution")
    p.add_argument("--list-agents", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.list_agents:
        print(json.dumps({"agents": list(HOSTS)}, ensure_ascii=False, indent=2))
        return 0
    if not args.agent and sys.stdin.isatty():
        print("Select agent / 选择编程助手: " + ", ".join(HOSTS), file=sys.stderr)
        args.agent = [input("Agent: ").strip()]
        args.mode = input("Mode basic/enhanced [basic]: ").strip() or "basic"
    results = []
    try:
        hosts = list(dict.fromkeys(ALIASES.get(x.lower(), x.lower()) for x in args.agent or []))
        if not hosts or any(x not in HOSTS for x in hosts):
            raise InstallError("Select a known --agent; use --list-agents")
        if args.mode not in ("basic", "enhanced"):
            raise InstallError("Mode must be basic or enhanced")
        if args.mcp_config and (len(hosts) != 1 or hosts[0] in ("deepseek-harness", "codex")):
            raise InstallError("--mcp-config requires one JSON host")
        if args.scope == "project" and not args.project:
            raise InstallError("Project scope requires --project")
        home = safe_path(args.home.expanduser())
        project = safe_path(args.project.expanduser()) if args.project else None
        if project and not project.is_dir():
            raise InstallError("Project must be an existing directory")
        if args.mode == "enhanced" and project and (home == project or project in home.parents):
            raise InstallError("Enhanced installation home must be outside the project to keep backups private")
        # --home is isolated: do not leak the real user's configured roots into it.
        env = os.environ if home == safe_path(Path.home()) else {}
        package = public_package(SOURCE)
        selected = [(host, *paths_for(host, home, project, args.scope, env)) for host in hosts]
        if args.mcp_config:
            selected = [(selected[0][0], selected[0][1], safe_path(args.mcp_config.expanduser()))]
        # Preflight every selected Skill before mutating any of them.
        for host, skill, config in selected:
            copy_skill(SOURCE, skill, package, dry_run=True)
        for host, skill, config in selected:
            results.append({"agent": host, "skill_path": str(skill), "skill": copy_skill(SOURCE, skill, package, args.dry_run)})
        if args.mode == "enhanced":
            for item in results:
                item["mcp"] = {"status": "not_attempted"}
        graph = None
        if args.mode == "enhanced" and not args.dry_run:
            graph = codegraph_setup.discover(args.codegraph)
            if graph is None:
                cache = safe_path(home / ".newbie-dev-buddy/tools/codegraph" / codegraph_setup.VERSION)
                if cache.exists():
                    node = safe_path(cache / ("node.exe" if os.name == "nt" else "node"))
                    graph = codegraph_setup.discover(str(node))
                else:
                    graph = codegraph_setup.install(cache)
        for item, (host, skill, config) in zip(results, selected):
            if args.mode == "enhanced":
                if args.dry_run:
                    item["codegraph"] = {"status": "would_reuse_or_download", "pinned_version": codegraph_setup.VERSION}
                    item["mcp"] = {"status": "would_review_config", "path": str(config) if config else None}
                else:
                    item["codegraph"] = {key: graph[key] for key in ("version", "origin", "command")}
                    try:
                        item["mcp"] = configure(host, config, graph, home / ".newbie-dev-buddy/setup", project if args.scope == "project" else None)
                    except (InstallError, OSError, UnicodeError) as exc:
                        item["mcp"] = {"status": "failed", "error": str(exc)}
        failed = any(x.get("mcp", {}).get("status") == "failed" for x in results)
        print(json.dumps({"ok": not failed, "dry_run": args.dry_run, "mode": args.mode, "scope": args.scope, "results": results, "project_indexed": False, "host_session_tested": False}, ensure_ascii=False, indent=2), file=sys.stderr if failed else sys.stdout)
        if failed:
            return 1
        return 2 if any(x.get("mcp", {}).get("status") == "manual_required" for x in results) else 0
    except (InstallError, codegraph_setup.SetupError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "results": results, "project_indexed": False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
