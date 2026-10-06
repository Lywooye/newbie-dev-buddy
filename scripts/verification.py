"""Module coverage requirements for Acceptance Kit; never execute project code."""
import hashlib
import json
from pathlib import Path
import re
import stat


POLICIES = {"manual", "on-change", "required"}
GENERATED = {".git", ".handoff", ".acceptance", "__pycache__", ".DS_Store"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(value):
    require(isinstance(value, str) and value and "\\" not in value and "\0" not in value,
            "use a nonempty project-relative path")
    require(not Path(value).is_absolute() and not re.match(r"^[a-z]:", value, re.I)
            and all(part not in ("", ".", "..") for part in value.split("/")),
            "use project-relative paths without '.', '..' or empty components")
    return value


def safe(root, value):
    root = Path(root).resolve()
    cursor = root
    for part in relative(value).split("/"):
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            mode = cursor.lstat()
            require(not stat.S_ISLNK(mode.st_mode), "symlink is not supported: " + value)
            require(stat.S_ISREG(mode.st_mode) or stat.S_ISDIR(mode.st_mode),
                    "special project files are not supported: " + value)
            require(not stat.S_ISREG(mode.st_mode) or mode.st_nlink == 1,
                    "hard-linked project files are not supported: " + value)
    require(root == cursor.resolve() or root in cursor.resolve().parents, "path leaves project")
    return cursor


def string_list(value, label):
    require(isinstance(value, list) and value and
            all(isinstance(item, str) and item for item in value), label + " must be nonempty")
    require(len(set(value)) == len(value), label + " must not contain duplicates")


def profile(value, *, integration=False):
    require(isinstance(value, dict), "verification profile must be an object")
    allowed = {"policy", "config", "steps", "inputs"}
    require(not set(value) - allowed, "unknown verification profile field")
    require("policy" not in value or isinstance(value["policy"], str) and value["policy"] in POLICIES,
            "invalid verification policy")
    if integration:
        require(value.get("policy") in {"on-change", "required"}, "invalid integration policy")
    configured = any(key in value for key in ("config", "steps", "inputs"))
    require(not integration or configured, "integration check requires a profile")
    if configured:
        relative(value.get("config"))
        string_list(value.get("steps"), "verification steps")
        require(all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", item)
                    for item in value["steps"]), "invalid verification step ID")
        string_list(value.get("inputs"), "verification inputs")
        for value_path in value["inputs"]:
            relative(value_path)


def validate_settings(mapping):
    require(isinstance(mapping, dict), "module map must be an object")
    defaults = mapping.get("verification_defaults", {})
    require(isinstance(defaults, dict) and not set(defaults) - {"policy"},
            "verification_defaults supports only policy")
    require(isinstance(defaults.get("policy", "manual"), str) and
            defaults.get("policy", "manual") in POLICIES, "invalid default verification policy")
    modules = mapping.get("modules", [])
    require(isinstance(modules, list) and all(isinstance(module, dict) for module in modules),
            "modules must be an array of objects")
    ids = [module.get("id") for module in modules]
    require(all(isinstance(item, str) for item in ids) and len(set(ids)) == len(ids),
            "module IDs must be unique strings")
    for module in modules:
        if "verification" in module:
            profile(module["verification"])
    integrations = mapping.get("integration_checks", [])
    require(isinstance(integrations, list), "integration_checks must be an array")
    seen = set()
    for check in integrations:
        require(isinstance(check, dict) and not set(check) -
                {"id", "modules", "policy", "config", "steps", "inputs"}, "invalid integration check")
        name = check.get("id")
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name)
                and name not in seen, "integration IDs must be unique lowercase names")
        seen.add(name)
        string_list(check.get("modules"), "integration modules")
        require(len(check["modules"]) >= 2 and all(item in ids for item in check["modules"]),
                "integration check must reference at least two known modules")
        profile({key: value for key, value in check.items() if key not in {"id", "modules"}},
                integration=True)


def build_plan(mapping, scope):
    validate_settings(mapping)
    require(isinstance(scope, list) and all(isinstance(item, str) for item in scope),
            "verification scope must be an array of module IDs")
    modules = {module["id"]: module for module in mapping["modules"]}
    require(all(item in modules for item in scope), "unknown verification scope module")
    default = mapping.get("verification_defaults", {}).get("policy", "manual")
    plan = {"modules": [], "checks": [], "missing": []}

    def add_check(check_id, kind, checked_modules, value):
        paths = [path for item in checked_modules for path in modules[item]["paths"]]
        paths += mapping.get("context", [])
        plan["checks"].append({"id": check_id, "kind": kind, "modules": checked_modules,
                               "policy": value.get("policy", default), "config": value["config"],
                               "steps": list(value["steps"]), "inputs": list(value["inputs"]),
                               "source_paths": sorted(set(paths))})

    for item in sorted(set(scope)):
        value = modules[item].get("verification", {})
        configured = "config" in value
        plan["modules"].append({"id": item, "policy": value.get("policy", default),
                                "configured": configured,
                                "check_id": "module:" + item if configured else None})
        if configured:
            add_check("module:" + item, "module", [item], value)
        else:
            plan["missing"].append(item)
    for check in mapping.get("integration_checks", []):
        if set(check["modules"]) & set(scope):
            add_check("integration:" + check["id"], "integration", list(check["modules"]), check)
    return plan


def matches(path, prefixes):
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def config_for_check(check, root):
    path = safe(root, check["config"])
    require(path.is_file(), "verification configuration must be a regular file")
    try:
        frozen_bytes = path.read_bytes()
        config = json.loads(frozen_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("cannot read verification configuration: " + str(error)) from None
    if "config_digest" in check:
        require(check["config_digest"] == hashlib.sha256(frozen_bytes).hexdigest(),
                "accepted Kit configuration digest changed; revise the proposal before running checks")
    if "config_snapshot" in check:
        require(check["config_snapshot"] == config,
                "accepted Kit configuration changed; revise the proposal before running checks")
    require(isinstance(config, dict) and config.get("schema") == 1 and
            isinstance(config.get("name"), str) and config["name"].strip(), "invalid Kit configuration")
    exclusions = []
    for key in ("exclude", "dependencyDirs"):
        values = config.get(key, [])
        require(isinstance(values, list), key + " must be an array")
        for value in values:
            exclusions.append(relative(value))
    require(matches(".handoff/newbie-dev-buddy", config.get("exclude", [])),
            "Kit config must exclude .handoff or .handoff/newbie-dev-buddy before recording results")
    steps = config.get("steps")
    require(isinstance(steps, list) and steps and all(isinstance(step, dict) for step in steps),
            "Kit configuration requires steps")
    step_ids = [step.get("id") for step in steps]
    require(all(isinstance(item, str) for item in step_ids) and len(set(step_ids)) == len(step_ids),
            "Kit step IDs must be unique strings")
    require(all(item in step_ids for item in check["steps"]), "configured module step is absent from Kit config")
    selected = [step for step in steps if step["id"] in check["steps"]]
    require(any(isinstance(step.get("format"), str) and step["format"] in {"tap", "checks"}
                for step in selected),
            "module acceptance requires a tap or checks behavior step")
    for step in steps:
        require(isinstance(step.get("format"), str) and step["format"] in {"tap", "checks", "exit"},
                "invalid Kit step format")
        require(isinstance(step.get("evidence", []), list), "Kit evidence must be an array")
        for value in step.get("evidence", []):
            exclusions.append(relative(value))
    require(not matches(check["config"], [".git", ".acceptance"] + exclusions),
            "Kit configuration must remain a source input")
    return config


def input_files(root, paths):
    """Expand required source/test paths without following links or skipping user exclusions."""
    root = Path(root).resolve()
    files = {}

    def visit(value):
        path = safe(root, value)
        require(path.exists(), "required verification input missing: " + value)
        if path.is_file():
            files[value] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            for child in sorted(path.iterdir()):
                if child.name not in GENERATED and not child.name.startswith(".newbie-dev-buddy-"):
                    visit(child.relative_to(root).as_posix())

    for value in sorted(set(paths)):
        require(not set(Path(relative(value)).parts) & GENERATED,
                "generated records cannot be verification inputs")
        visit(value)
    require(files, "required verification inputs must include a regular source/test file")
    return files


def validate_profiles(mapping, root):
    plan = build_plan(mapping, [module["id"] for module in mapping["modules"]])
    for check in plan["checks"]:
        profile_files(check, root)


def profile_files(check, root, config=None):
    config = config if config is not None else config_for_check(check, root)
    files = input_files(root, [check["config"]] + check["inputs"] + check["source_paths"])
    exclusions = [".git", ".acceptance"] + config.get("exclude", []) + config.get("dependencyDirs", [])
    exclusions += [path for step in config["steps"] for path in step.get("evidence", [])]
    for path in files:
        require(not matches(path, exclusions), "required module input excluded by Kit config: " + path)
    return files


def check_coverage(report, check, root):
    """Return coverage failures; Acceptance Kit must still independently recheck the receipt."""
    issues = []
    try:
        config = config_for_check(check, root)
        require(isinstance(report, dict), "Kit report must be a JSON object")
        if report.get("status") != "passed":
            issues.append("Kit report did not pass")
        if report.get("configFile") != check["config"]:
            issues.append("Kit report uses a different module configuration")
        if report.get("config") != config:
            issues.append("module configuration changed since the Kit run")
        actual_steps = report.get("steps")
        require(isinstance(actual_steps, list) and all(isinstance(step, dict) for step in actual_steps),
                "Kit report steps must be an array of objects")
        actual_ids = [step.get("id") for step in actual_steps]
        require(all(isinstance(item, str) for item in actual_ids) and
                len(set(actual_ids)) == len(actual_ids), "Kit report contains invalid or duplicate step IDs")
        expected_steps = {step["id"]: step for step in config["steps"]}
        actual_steps = {step["id"]: step for step in actual_steps}
        for item in check["steps"]:
            actual = actual_steps.get(item, {})
            if actual.get("status") != "passed" or actual.get("exitCode") != 0 or actual.get("signal"):
                issues.append("required module step did not pass: " + item)
            fmt = expected_steps[item]["format"]
            proof = actual.get("proof")
            if fmt in {"tap", "checks"}:
                field = "tests" if fmt == "tap" else "checks"
                if not isinstance(proof, dict) or type(proof.get(field)) is not int or proof[field] < 1:
                    issues.append("required behavior step has no nonempty proof: " + item)
        inputs = report.get("inputs")
        require(isinstance(inputs, dict), "Kit report inputs must be a JSON object")
        files = profile_files(check, root, config)
        for value, current_hash in files.items():
            if inputs.get(value) != current_hash:
                issues.append("required module input absent or changed: " + value)
    except (ValueError, OSError, TypeError, KeyError) as error:
        issues.append(str(error))
    return issues
