"""Installed bundled-Kit behavior using real Node and only temporary projects."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
try:
    NODE_MAJOR = int(subprocess.check_output([NODE, "--version"], text=True,
                                           timeout=5).strip().lstrip("v").split(".")[0]) if NODE else 0
except (OSError, ValueError, subprocess.SubprocessError):
    NODE_MAJOR = 0


@unittest.skipUnless(os.name != "nt" and NODE_MAJOR >= 22,
                     "Full workflow requires Unix and Node.js 22+")
class BundledKitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="buddy-bundled-kit-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "installed home 中文"
        self.install(self.home)
        self.skill = self.home / ".claude/skills/newbie-dev-buddy"
        self.script = self.skill / "scripts/newbie_dev_buddy.py"
        self.kit = self.skill / "vendor/acceptance-kit"
        self.project = self.base / "project space 中文 #(v1)"
        self.project.mkdir()
        self.note = self.base / "decision.md"
        self.note.write_text("Synthetic test decision; not real human authorization.\n",
                             encoding="utf-8")

    def install(self, home, env=None):
        result = subprocess.run([sys.executable, str(SOURCE / "scripts/install.py"),
                                 "--agent", "claude-code", "--home", str(home)],
                                cwd=self.base, capture_output=True, text=True,
                                timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["skill"], "installed")

    def write(self, name, text):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def call(self, command, *args, code=0, env=None):
        result = subprocess.run([sys.executable, str(self.script), command,
                                 "--project", str(self.project), *map(str, args)],
                                cwd=self.base, capture_output=True, text=True,
                                timeout=30, env=env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return json.loads(result.stderr if code == 1 else result.stdout)

    def prepare(self, expected="new\n", env=None):
        self.write("src/value.txt", "old\n")
        self.write("tests/value.mjs", "import assert from 'node:assert/strict';\n"
                   "import {readFileSync, writeFileSync} from 'node:fs';\n"
                   "const value = readFileSync('src/value.txt', 'utf8');\n"
                   "assert.equal(value, " + json.dumps(expected) + ");\n"
                   "writeFileSync('result.txt', value);\n"
                   "console.log(JSON.stringify({status:'passed',checks:"
                   "[{name:'stored value and output match',status:'passed'}]}));\n")
        config = {"schema": 1, "name": "Synthetic bundled acceptance",
                  "exclude": [".handoff/newbie-dev-buddy"],
                  "steps": [{"id": "value", "command": ["node", "tests/value.mjs"],
                             "format": "checks", "evidence": ["result.txt"]}]}
        self.config = self.write("acceptance.value.json", json.dumps(config))
        mapping = {"title": "Synthetic bundle project", "modules": [
            {"id": "M-DATA", "name": "Data", "purpose": "Store a text value",
             "paths": ["src/value.txt"], "depends_on": [], "contract": "UTF-8 text",
             "verification": {"policy": "required", "config": "acceptance.value.json",
                              "steps": ["value"], "inputs": ["tests/value.mjs"]}}]}
        map_json = self.base / "map.json"
        map_json.write_text(json.dumps(mapping), encoding="utf-8")
        self.call("init", "--map-json", map_json, "--decision-note-file", self.note, env=env)
        spec = self.base / "proposal.json"
        spec.write_text(json.dumps({"id": "C-001", "title": "Update stored value",
                                   "primary": "M-DATA", "affected": [], "location": "value",
                                   "plan": "Store new text without changing the format.",
                                   "acceptance": "The stored and exported text equals new.",
                                   "documentation": {"files": [], "map_updates": {}, "map_reason": "UTF-8 text contract is unchanged."}}),
                        encoding="utf-8")
        proposal = self.call("propose", "--spec-json", spec, env=env)
        accepted = self.call("decide", "--change", "C-001", "--revision", 1,
                             "--expect-digest", proposal["digest"], "--decision", "accept",
                             "--note-file", self.note, env=env)
        self.args = ["--change", "C-001", "--revision", 1,
                     "--expect-digest", accepted["accepted_digest"]]
        self.call("record", *self.args, "--event", "started", "--note-file", self.note, env=env)
        self.write("src/value.txt", "new\n")
        completion = self.base / "completion.json"
        completion.write_text(json.dumps({"files": [{"path": "src/value.txt", "summary": "Replace old stored text with new text."}]}))
        self.call("record", *self.args, "--completion-json", completion, "--event", "implemented", "--note-file", self.note,
                  env=env)

    def run_checks(self, *args, code=0, env=None):
        return self.call("run-checks", *self.args, "--check-id", "module:M-DATA",
                         *args, code=code, env=env)

    def module_state(self, result):
        return result["status"]["current"][0]["module_verification"]

    def receipt(self, result):
        return self.project / self.module_state(result)["checks"][0]["receipt"]

    def verify(self, receipt, *args, code=0, env=None):
        return self.call("verify", *self.args, "--check-id", "module:M-DATA",
                         "--receipt", receipt, *args, code=code, env=env)

    def external_kit(self):
        external = self.base / "external kit 中文"
        shutil.copytree(self.kit, external)
        # Same protocol, different real tool fingerprint; no fabricated checker.
        package = external / "package.json"
        package.write_bytes(package.read_bytes() + b"\n")
        return external

    def test_installed_bundle_runs_and_rechecks_without_external_kit(self):
        declared = (SOURCE / "PUBLIC_FILES.txt").read_text().splitlines()
        self.assertEqual({p.relative_to(self.skill).as_posix() for p in self.skill.rglob("*")
                          if p.is_file()}, set(declared))
        self.prepare()
        result = self.run_checks()
        self.assertEqual(result["result"], "passed")
        self.assertTrue(self.module_state(result)["delivery_ready"])
        receipt = self.receipt(result)
        report = json.loads(receipt.read_text())
        self.assertEqual(report["steps"][0]["proof"]["checks"], 1)
        self.assertEqual((receipt.parent / "workspace/result.txt").read_text(), "new\n")
        self.assertFalse((self.project / "result.txt").exists())
        self.assertEqual((self.project / "src/value.txt").read_text(), "new\n")
        self.assertEqual(self.verify(receipt)["result"], "passed")
        state = self.call("status")["current"][0]
        self.assertEqual(state["module_verification"]["modules"][0]["state"], "passed")
        self.assertEqual(state["execution"], "implemented")

    def test_real_assertion_failure_keeps_module_unaccepted(self):
        self.prepare(expected="wrong\n")
        result = self.run_checks(code=2)
        self.assertEqual(result["result"], "failed_or_stale")
        self.assertFalse(self.module_state(result)["delivery_ready"])
        self.assertEqual(self.module_state(result)["modules"][0]["state"], "failed")
        report = json.loads(self.receipt(result).read_text())
        self.assertEqual(report["status"], "failed")
        self.assertNotEqual(report["steps"][0]["exitCode"], 0)

    def test_source_change_marks_history_stale_and_cannot_be_verified(self):
        self.prepare()
        result = self.run_checks()
        receipt = self.receipt(result)
        self.write("src/value.txt", "changed later\n")
        state = self.call("status")["current"][0]["module_verification"]
        self.assertEqual(state["modules"][0]["state"], "stale")
        self.assertFalse(state["delivery_ready"])
        self.assertFalse(self.verify(receipt, code=1)["ok"])
        checked = subprocess.run([NODE, str(self.kit / "bin/acceptance.mjs"), "check",
                                  "--project", str(self.project), "--receipt", str(receipt)],
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertFalse(json.loads(checked.stdout)["current"])

    def test_changed_accepted_configuration_is_not_executed(self):
        self.prepare()
        config = json.loads(self.config.read_text())
        config["steps"][0]["command"] = ["node", "-e", "process.exit(0)"]
        self.config.write_text(json.dumps(config), encoding="utf-8")
        self.assertFalse(self.run_checks(code=1)["ok"])
        self.assertFalse((self.project / ".acceptance").exists())
        current = self.call("status")["current"][0]
        self.assertTrue(current["drift"])
        self.assertFalse(current["module_verification"]["delivery_ready"])

    def test_modified_generated_evidence_fails_receipt_recheck(self):
        self.prepare()
        receipt = self.receipt(self.run_checks())
        (receipt.parent / "workspace/result.txt").write_text("substituted output\n")
        result = self.verify(receipt, code=2)
        self.assertFalse(result["receipt_current"])
        self.assertFalse(self.module_state(result)["delivery_ready"])

    def test_explicit_external_kit_precedes_corrupt_bundle_without_fallback(self):
        self.prepare()
        external = self.external_kit()
        (self.kit / "BUNDLE.json").write_text("{}\n")
        result = self.run_checks("--kit", external)
        receipt = self.receipt(result)
        self.assertEqual(self.verify(receipt, "--kit", external)["result"], "passed")
        self.assertFalse(self.verify(receipt, code=1)["ok"])
        self.assertFalse(self.verify(receipt, "--kit", self.base / "missing-kit", code=1)["ok"])

    def test_empty_external_kit_does_not_fall_back_to_bundle(self):
        self.prepare()
        for args in (("--kit", ""), ("--kit=",)):
            with self.subTest(arguments=args, command="run-checks"):
                self.assertFalse(self.run_checks(*args, code=1)["ok"])
                self.assertFalse((self.project / ".acceptance").exists())
        receipt = self.receipt(self.run_checks())
        for args in (("--kit", ""), ("--kit=",)):
            with self.subTest(arguments=args, command="verify"):
                self.assertFalse(self.verify(receipt, *args, code=1)["ok"])

    def test_foreign_tool_fingerprint_requires_correct_external_kit(self):
        self.prepare()
        external = self.external_kit()
        receipt = self.receipt(self.run_checks("--kit", external))
        self.assertFalse(self.verify(receipt, code=2)["receipt_current"])
        self.assertEqual(self.verify(receipt, "--kit", external)["result"], "passed")

    def test_corrupt_or_missing_bundled_runtime_is_never_executed(self):
        self.prepare()
        for name in ("package.json", "bin/acceptance.mjs", "lib/acceptance.mjs"):
            path = self.kit / name
            original = path.read_bytes()
            with self.subTest(file=name, change="bytes"):
                path.write_bytes(original + b"\n")
                self.assertFalse(self.run_checks(code=1)["ok"])
                self.assertFalse((self.project / ".acceptance").exists())
                path.write_bytes(original)
            with self.subTest(file=name, change="missing"):
                path.unlink()
                self.assertFalse(self.run_checks(code=1)["ok"])
                self.assertFalse((self.project / ".acceptance").exists())
                path.write_bytes(original)

    def test_missing_node_keeps_basic_install_and_workflow_usable(self):
        empty_path = self.base / "empty-bin"
        empty_path.mkdir()
        env = {**os.environ, "PATH": str(empty_path)}
        self.install(self.base / "without Node home", env=env)
        self.prepare(env=env)
        self.call("scan", env=env)
        self.assertEqual(self.call("status", env=env)["current"][0]["execution"], "implemented")
        error = self.run_checks(code=1, env=env)["error"]
        self.assertIn("Node", error)
        self.assertIn("22", error)
        self.assertFalse((self.project / ".acceptance").exists())
        receipt = self.receipt(self.run_checks())
        error = self.verify(receipt, code=1, env=env)["error"]
        self.assertIn("Node", error)
        self.assertIn("22", error)

    def test_old_node_is_rejected_before_checks_but_status_still_works(self):
        self.prepare()
        receipt = self.receipt(self.run_checks())
        old_bin = self.base / "old-node-bin"
        old_bin.mkdir()
        node = old_bin / "node"
        node.write_text("#!/bin/sh\nprintf 'v20.0.0\\n'\n", encoding="utf-8")
        node.chmod(0o755)
        env = {**os.environ, "PATH": str(old_bin)}
        self.call("status", env=env)
        before = list((self.project / ".acceptance").iterdir())
        for action in (lambda: self.run_checks(code=1, env=env),
                       lambda: self.verify(receipt, code=1, env=env)):
            error = action()["error"]
            self.assertIn("Node", error)
            self.assertIn("22", error)
        self.assertEqual(list((self.project / ".acceptance").iterdir()), before)


if __name__ == "__main__":
    unittest.main()
