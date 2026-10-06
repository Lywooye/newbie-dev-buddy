"""Public CLI coverage regressions; the synthetic checker is not a real Kit validation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import test_workflow as fixtures


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/module_change.py"


@unittest.skipUnless(shutil.which("node"), "Node required for the synthetic checker")
class ModuleAdversarialTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    json_file = fixtures.WorkflowTests.json_file
    call = fixtures.WorkflowTests.call
    proposal = fixtures.WorkflowTests.proposal
    accept = fixtures.WorkflowTests.accept
    record = fixtures.WorkflowTests.record

    def configure(self, *, required=True, integration=None, missing=False):
        (self.project / "src/ui.txt").write_text("Synthetic UI source.\n")
        (self.project / "tests").mkdir(exist_ok=True)
        (self.project / "tests/data.py").write_text("Synthetic behavioral test input.\n")
        path = self.project / "docs/module-change/MODULES.md"
        header, body = path.read_text()[4:].split("\n---\n", 1)
        mapping = json.loads(header)
        value = {"policy": "required" if required else "on-change"}
        if not missing:
            value.update(self.profile("data"))
        mapping["modules"][0]["verification"] = value
        if integration:
            mapping["integration_checks"] = [{"id": "data-ui", "modules": ["M-DATA", "M-UI"],
                                                "policy": integration, **self.profile("interface")}]
        path.write_text("---\n" + json.dumps(mapping, sort_keys=True, indent=2) + "\n---\n" + body)
        kit = self.base / "synthetic-kit/bin"
        kit.mkdir(parents=True)
        (kit / "acceptance.mjs").write_text(
            "import fs from 'node:fs'; import path from 'node:path';\n"
            "const args=process.argv; const action=args[2];\n"
            "const project=args[args.indexOf('--project')+1];\n"
            "fs.appendFileSync(path.join(project,'.acceptance/checker-calls.txt'),action+'\\n');\n"
            "if(action==='run'){const config=args[args.indexOf('--config')+1];"
            " console.log('passed: '+path.join(project,'.acceptance',config,'report.json'));}\n"
            "else console.log(JSON.stringify({current:true,issues:[]}));\n")
        (self.project / ".acceptance").mkdir(exist_ok=True)
        self.kit = kit.parent

    def profile(self, name):
        config_path = "acceptance." + name + ".json"
        config = {"schema": 1, "name": "Synthetic " + name + " coverage", "exclude": [".handoff"],
                  "steps": [{"id": name, "command": ["python", "tests/data.py"], "format": "checks"}]}
        (self.project / config_path).write_text(json.dumps(config))
        return {"config": config_path, "steps": [name], "inputs": ["tests/data.py"]}

    def implement(self, **spec):
        proposed = self.proposal(**spec)
        adopted = self.accept(proposed)
        self.record(proposed, adopted, "started")
        self.record(proposed, adopted, "implemented")
        self.adopted = adopted
        self.proposed = proposed
        path = self.project / adopted["path"]
        self.accepted_data = json.loads(path.read_text()[4:].split("\n---\n", 1)[0])
        return adopted

    def receipt(self, check_id, *, omit=None, failed=False):
        target = next(check for check in self.accepted_data["verification_plan"]["checks"]
                      if check["id"] == check_id)
        config = json.loads((self.project / target["config"]).read_text())
        required = [target["config"]] + target["inputs"] + target["source_paths"]
        inputs = {value: hashlib.sha256((self.project / value).read_bytes()).hexdigest() for value in required}
        if omit:
            inputs.pop(omit)
        report = {"status": "failed" if failed else "passed", "configFile": target["config"], "config": config,
                  "inputs": inputs, "steps": [{"id": step["id"], "command": step["command"],
                                               "status": "failed" if failed else "passed", "exitCode": 1 if failed else 0,
                                               "signal": None, "proof": {"checks": 1, "names": ["Synthetic assertion"]}}
                                              for step in config["steps"]]}
        path = self.project / ".acceptance" / target["config"] / "report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report))
        return path

    def evidence(self, *arguments):
        completed = subprocess.run([sys.executable, str(SCRIPT), *arguments, "--project", str(self.project),
                                    "--change", "C-001", "--revision", "1", "--expect-digest",
                                    self.adopted["accepted_digest"], "--kit", str(self.kit)],
                                   capture_output=True, text=True)
        result = json.loads(completed.stderr if completed.returncode == 1 else completed.stdout)
        return completed.returncode, result

    def verify(self, receipt, check_id=None):
        args = ["verify", "--receipt", str(receipt)]
        if check_id:
            args += ["--check-id", check_id]
        return self.evidence(*args)

    def module_state(self):
        return self.call("status")["current"][0]["module_verification"]

    def test_generic_passing_receipt_never_satisfies_required_module(self):
        self.configure()
        self.implement()
        exit_code, result = self.verify(self.receipt("module:M-DATA"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["result"], "passed")
        state = result["status"]["current"][0]["module_verification"]
        self.assertFalse(state["delivery_ready"])
        self.assertEqual(state["modules"][0]["state"], "not_run")

    def test_required_policy_without_profile_is_explicitly_blocked(self):
        self.configure(missing=True)
        self.implement()
        state = self.module_state()
        self.assertFalse(state["delivery_ready"])
        self.assertEqual(state["missing_required"], ["M-DATA"])
        self.assertEqual(state["modules"][0]["state"], "not_configured")

    def test_required_interface_must_pass_as_well_as_module(self):
        self.configure(integration="required")
        self.implement()
        code, _ = self.verify(self.receipt("module:M-DATA"), "module:M-DATA")
        self.assertEqual(code, 0)
        state = self.module_state()
        self.assertFalse(state["delivery_ready"])
        self.assertEqual(state["modules"][0]["state"], "partial")
        code, _ = self.verify(self.receipt("integration:data-ui"), "integration:data-ui")
        self.assertEqual(code, 0)
        state = self.module_state()
        self.assertTrue(state["delivery_ready"])
        self.assertEqual(state["modules"][0]["state"], "passed")
        self.assertTrue(all(check["receipt_recheck_required"] for check in state["checks"]))

    def test_required_module_cannot_be_green_with_unrun_on_change_interface(self):
        self.configure(integration="on-change")
        self.implement()
        code, _ = self.verify(self.receipt("module:M-DATA"), "module:M-DATA")
        self.assertEqual(code, 0)
        state = self.module_state()
        self.assertEqual(state["modules"][0]["state"], "partial")
        self.assertFalse(state["delivery_ready"])
        code, _ = self.verify(self.receipt("integration:data-ui"), "integration:data-ui")
        self.assertEqual(code, 0)
        self.assertTrue(self.module_state()["delivery_ready"])

    def test_command_change_after_start_is_not_authorized_by_implementation_record(self):
        self.configure()
        proposed = self.proposal()
        adopted = self.accept(proposed)
        self.record(proposed, adopted, "started")
        config_path = self.project / "acceptance.data.json"
        config = json.loads(config_path.read_text())
        config["steps"][0]["command"] = ["python", "tests/replacement.py"]
        config_path.write_text(json.dumps(config))
        self.record(proposed, adopted, "implemented")
        self.adopted = adopted
        self.accepted_data = json.loads((self.project / adopted["path"]).read_text()[4:].split("\n---\n", 1)[0])
        receipt = self.receipt("module:M-DATA")
        code, result = self.evidence("run-checks", "--check-id", "module:M-DATA")
        self.assertEqual(code, 1)
        self.assertIn("accepted Kit configuration", result["error"])
        self.assertFalse((self.project / ".acceptance/checker-calls.txt").exists())
        code, result = self.verify(receipt, "module:M-DATA")
        self.assertEqual(code, 2)
        self.assertTrue(any("accepted Kit configuration" in issue for issue in result["coverage_issues"]))
        self.assertFalse(self.module_state()["delivery_ready"])

    def test_out_of_scope_interface_source_is_required_by_receipt(self):
        self.configure(integration="required")
        self.implement()
        receipt = self.receipt("integration:data-ui", omit="src/ui.txt")
        code, result = self.verify(receipt, "integration:data-ui")
        self.assertEqual(code, 2)
        self.assertTrue(any("src/ui.txt" in issue for issue in result["coverage_issues"]))
        self.assertFalse(result["status"]["current"][0]["module_verification"]["delivery_ready"])

    def test_receipt_tamper_or_source_drift_invalidates_recorded_green(self):
        self.configure()
        self.implement()
        receipt = self.receipt("module:M-DATA")
        self.assertEqual(self.verify(receipt, "module:M-DATA")[0], 0)
        self.assertTrue(self.module_state()["delivery_ready"])
        receipt.write_text(receipt.read_text() + "\n")
        state = self.module_state()
        self.assertEqual(state["modules"][0]["state"], "stale")
        self.assertFalse(state["delivery_ready"])
        receipt = self.receipt("module:M-DATA")
        self.assertEqual(self.verify(receipt, "module:M-DATA")[0], 0)
        (self.project / "tests/data.py").write_text("Changed synthetic test.\n")
        self.assertEqual(self.module_state()["modules"][0]["state"], "stale")
        self.assertFalse(self.module_state()["delivery_ready"])
        self.assertEqual(self.verify(receipt, "module:M-DATA")[0], 1)

    def test_failed_later_receipt_replaces_previous_module_green(self):
        self.configure()
        self.implement()
        receipt = self.receipt("module:M-DATA")
        self.assertEqual(self.verify(receipt, "module:M-DATA")[0], 0)
        receipt = self.receipt("module:M-DATA", failed=True)
        self.assertEqual(self.verify(receipt, "module:M-DATA")[0], 2)
        state = self.module_state()
        self.assertEqual(state["modules"][0]["state"], "failed")
        self.assertFalse(state["delivery_ready"])

    def test_failed_on_change_check_blocks_gate_after_all_required_checks_pass(self):
        self.configure(integration="required")
        path = self.project / "docs/module-change/MODULES.md"
        header, body = path.read_text()[4:].split("\n---\n", 1)
        mapping = json.loads(header)
        mapping["modules"][1]["verification"] = {"policy": "on-change", **self.profile("ui")}
        path.write_text("---\n" + json.dumps(mapping, sort_keys=True, indent=2) + "\n---\n" + body)
        self.implement(affected=["M-UI"])
        for check_id in ("module:M-DATA", "integration:data-ui"):
            self.assertEqual(self.verify(self.receipt(check_id), check_id)[0], 0)
        self.assertTrue(self.module_state()["delivery_ready"])
        self.assertEqual(self.verify(self.receipt("module:M-UI", failed=True), "module:M-UI")[0], 2)
        state = self.module_state()
        self.assertTrue(all(check["state"] == "passed" for check in state["checks"]
                            if check["policy"] == "required"))
        self.assertFalse(state["delivery_ready"])

    def test_unaccepted_check_is_rejected_before_checker_runs(self):
        self.configure()
        self.implement()
        code, result = self.verify(self.receipt("module:M-DATA"), "module:M-UI")
        self.assertEqual(code, 1)
        self.assertIn("not in the accepted", result["error"])
        self.assertFalse((self.project / ".acceptance/checker-calls.txt").exists())

    def test_batch_preflight_stops_all_runs_if_any_profile_is_invalid(self):
        self.configure(integration="required")
        self.implement()
        self.record(self.proposed, self.adopted, "started")
        config_path = self.project / "acceptance.interface.json"
        config = json.loads(config_path.read_text())
        config["exclude"].append("src/ui.txt")
        config_path.write_text(json.dumps(config))
        self.record(self.proposed, self.adopted, "implemented")
        self.receipt("module:M-DATA")
        self.receipt("integration:data-ui")
        code, result = self.evidence("run-checks", "--check-id", "module:M-DATA",
                                     "--check-id", "integration:data-ui")
        self.assertEqual(code, 1)
        self.assertIn("accepted Kit configuration", result["error"])
        self.assertFalse((self.project / ".acceptance/checker-calls.txt").exists())

    def test_proposal_rejects_configuration_that_excludes_interface_source(self):
        self.configure(integration="required")
        config_path = self.project / "acceptance.interface.json"
        config = json.loads(config_path.read_text())
        config["exclude"].append("src/ui.txt")
        config_path.write_text(json.dumps(config))
        spec = {"id": "C-001", "title": "Synthetic change", "primary": "M-DATA", "affected": [],
                "location": "stored value", "plan": "Keep the interface compatible.",
                "acceptance": "Known value remains visible."}
        result = self.call("propose", "--spec-json", self.json_file("excluded-proposal.json", spec), ok=False)
        self.assertIn("excluded", result["error"])

    def test_batch_only_runs_selected_checks_and_does_not_fill_other_evidence(self):
        self.configure(integration="required")
        self.implement()
        self.receipt("module:M-DATA")
        code, result = self.evidence("run-checks", "--check-id", "module:M-DATA")
        self.assertEqual(code, 0)
        self.assertEqual([check["check_id"] for check in result["checks"]], ["module:M-DATA"])
        state = result["status"]["current"][0]["module_verification"]
        self.assertFalse(state["delivery_ready"])
        self.assertEqual([check["state"] for check in state["checks"]], ["passed", "not_run"])


if __name__ == "__main__":
    unittest.main()
