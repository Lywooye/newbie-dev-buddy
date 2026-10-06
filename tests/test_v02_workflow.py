"""Discovery adoption and module evidence through the public CLI; synthetic only."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import test_workflow as fixtures


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/newbie_dev_buddy.py"


class MapWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="map-workflow-test-")
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src/data.py").write_text("def value():\n    return 1\n")
        self.note = self.base / "note.md"
        self.note.write_text("Synthetic approval used only by tests.\n")
        self.mapping = {"title": "Synthetic existing project", "modules": [
            {"id": "M-DATA", "name": "Data", "purpose": "Return a value", "paths": ["src/data.py"],
             "depends_on": [], "contract": "value() returns an integer."}]}

    def tearDown(self):
        self.temp.cleanup()

    def call(self, command, *args, ok=True):
        completed = subprocess.run([sys.executable, str(SCRIPT), command, "--project", str(self.project),
                                    *map(str, args)], capture_output=True, text=True)
        self.assertEqual(completed.returncode == 0, ok, completed.stdout + completed.stderr)
        return json.loads(completed.stdout if ok else completed.stderr)

    def candidate(self, mapping=None, lineage=None):
        scan = self.call("scan")
        source = self.base / "map.json"
        source.write_text(json.dumps(mapping or self.mapping))
        args = ["--scan", scan["path"], "--map-json", source]
        if lineage is not None:
            path = self.base / "lineage.json"
            path.write_text(json.dumps(lineage))
            args += ["--lineage-json", path]
        return self.call("map-propose", *args)

    def decide(self, candidate, decision="accept", ok=True):
        return self.call("map-decide", "--revision", candidate["revision"], "--expect-digest", candidate["digest"],
                         "--decision", decision, "--note-file", self.note, ok=ok)

    def test_scan_is_not_acceptance_and_adoption_keeps_old_format(self):
        candidate = self.candidate()
        self.assertFalse((self.project / "docs/newbie-dev-buddy/MODULES.md").exists())
        accepted = self.decide(candidate)
        self.assertEqual(accepted["status"]["map_revision"], 1)
        self.assertEqual(accepted["status"]["modules"][0]["id"], "M-DATA")
        self.assertEqual(accepted["status"]["current"], [])

    def test_new_source_and_modified_source_block_adoption(self):
        candidate = self.candidate()
        (self.project / "src/new.py").write_text("x = 2\n")
        self.assertIn("source changed", self.decide(candidate, ok=False)["error"])
        (self.project / "src/new.py").unlink()
        (self.project / "src/data.py").write_text("x = 3\n")
        self.decide(candidate, ok=False)

    def test_candidate_tamper_and_newer_revision_block_acceptance(self):
        first = self.candidate()
        self.candidate()
        self.assertIn("newer", self.decide(first, ok=False)["error"])
        latest = self.candidate()
        with (self.project / latest["path"]).open("a") as stream:
            stream.write("Unpresented change.\n")
        self.assertIn("digest", self.decide(latest, ok=False)["error"])

    def test_rejection_preserves_candidate_without_installing_map(self):
        candidate = self.candidate()
        self.decide(candidate, "reject")
        self.assertTrue((self.project / candidate["path"]).is_file())
        self.assertFalse((self.project / "docs/newbie-dev-buddy/MODULES.md").exists())
        self.decide(candidate, ok=False)

    def test_map_update_keeps_previous_bytes_and_module_ids(self):
        first = self.decide(self.candidate())
        map_path = self.project / "docs/newbie-dev-buddy/MODULES.md"
        before = map_path.read_bytes()
        revised = json.loads(json.dumps(self.mapping))
        revised["modules"][0]["name"] = "Renamed data"
        candidate = self.candidate(revised)
        self.assertEqual(candidate["difference"]["changed"], ["M-DATA"])
        second = self.decide(candidate)
        archive = self.project / ".handoff/newbie-dev-buddy/maps/history" / (first["map_digest"] + ".md")
        self.assertEqual(archive.read_bytes(), before)
        self.assertEqual(second["status"]["modules"][0]["id"], "M-DATA")

    def test_removed_id_requires_lineage_and_cannot_be_reused(self):
        self.decide(self.candidate())
        new = json.loads(json.dumps(self.mapping))
        new["modules"][0]["id"] = "M-NEW"
        scan = self.call("scan")
        source = self.base / "new.json"
        source.write_text(json.dumps(new))
        self.call("map-propose", "--scan", scan["path"], "--map-json", source, ok=False)
        self.decide(self.candidate(new, [{"from": ["M-DATA"], "to": ["M-NEW"], "reason": "Synthetic retirement."}]))
        source.write_text(json.dumps(self.mapping))
        scan = self.call("scan")
        lineage = self.base / "again.json"
        lineage.write_text(json.dumps([{"from": ["M-NEW"], "to": ["M-DATA"], "reason": "Attempted reuse."}]))
        result = self.call("map-propose", "--scan", scan["path"], "--map-json", source, "--lineage-json", lineage, ok=False)
        self.assertIn("must not be reused", result["error"])

    def test_map_update_does_not_expand_old_proposal_scope(self):
        self.decide(self.candidate())
        spec = self.base / "spec.json"
        spec.write_text(json.dumps({"id": "C-1", "title": "Value", "primary": "M-DATA", "affected": [],
                                    "location": "value", "plan": "Return 2", "acceptance": "Returns 2",
                                    "documentation": {"files": [], "map_updates": {}, "map_reason": "Plain text format remains unchanged."}}))
        proposed = self.call("propose", "--spec-json", spec)
        adopted = self.call("decide", "--change", "C-1", "--revision", 1, "--expect-digest", proposed["digest"],
                            "--decision", "accept", "--note-file", self.note)
        accepted_path = self.project / adopted["path"]
        accepted_bytes = accepted_path.read_bytes()
        revised = json.loads(json.dumps(self.mapping))
        revised["modules"][0]["paths"] = ["src"]
        self.decide(self.candidate(revised))
        self.assertEqual(accepted_path.read_bytes(), accepted_bytes)
        self.assertTrue(self.call("status")["current"][0]["drift"])
        self.call("record", "--change", "C-1", "--revision", 1, "--expect-digest", adopted["accepted_digest"],
                  "--event", "started", "--note-file", self.note, ok=False)

    def test_unassigned_and_shared_files_are_reported(self):
        (self.project / "unassigned.txt").write_text("value\n")
        mapping = json.loads(json.dumps(self.mapping))
        shared = dict(mapping["modules"][0], id="M-SHARED", name="Shared")
        mapping["modules"].append(shared)
        candidate = self.candidate(mapping)
        self.assertIn("unassigned.txt", candidate["coverage"]["unassigned"])
        self.assertEqual(candidate["coverage"]["overlapping"]["src/data.py"], ["M-DATA", "M-SHARED"])


class ModuleEvidenceTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    json_file = fixtures.WorkflowTests.json_file
    call = fixtures.WorkflowTests.call
    proposal = fixtures.WorkflowTests.proposal
    accept = fixtures.WorkflowTests.accept
    record = fixtures.WorkflowTests.record

    def configure(self):
        (self.project / "tests").mkdir()
        (self.project / "tests/value.py").write_text("assert True\n")
        config = {"schema": 1, "name": "Synthetic value checks", "exclude": [".handoff/newbie-dev-buddy"],
                  "steps": [{"id": "value", "command": ["node", "tests/value.mjs"], "format": "checks"}]}
        (self.project / "acceptance.value.json").write_text(json.dumps(config))
        path = self.project / "docs/newbie-dev-buddy/MODULES.json"
        # Synthetic fixture configuration before proposing; no simulated user record is modified.
        mapping = json.loads(path.read_text())
        mapping["modules"][0]["verification"] = {"policy": "required", "config": "acceptance.value.json",
                                                 "steps": ["value"], "inputs": ["tests/value.py"]}
        path.write_text(json.dumps(mapping))
        self.call("map-render", "--expect-digest", hashlib.sha256(path.read_bytes()).hexdigest())
        return config

    def test_required_module_stays_unchecked_until_covered(self):
        self.configure()
        adopted = self.accept(self.proposal())
        state = adopted["status"]["current"][0]["module_verification"]
        self.assertEqual(state["modules"][0]["state"], "not_run")
        self.assertFalse(state["delivery_ready"])

    def test_test_and_config_changes_are_bound_to_acceptance(self):
        self.configure()
        proposed = self.proposal()
        (self.project / "tests/value.py").write_text("assert False\n")
        self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "accept",
                  "--expect-digest", proposed["digest"], "--note-file", self.note, ok=False)

    @unittest.skipUnless(shutil.which("node"), "Node required for a synthetic Kit checker")
    def test_unrelated_passing_receipt_does_not_pass_module(self):
        config = self.configure()
        proposed = self.proposal()
        adopted = self.accept(proposed)
        self.record(proposed, adopted, "started")
        self.record(proposed, adopted, "implemented")
        kit = self.base / "kit/bin"
        kit.mkdir(parents=True)
        (kit / "acceptance.mjs").write_text('console.log(JSON.stringify({current:true,issues:[]}));\n')
        receipt = self.project / ".acceptance/run/report.json"
        receipt.parent.mkdir(parents=True)
        report = {"status": "passed", "configFile": "unrelated.json", "config": config,
                  "inputs": {}, "steps": [{"id": "value", "status": "passed", "exitCode": 0,
                                             "proof": {"checks": 1}}]}
        receipt.write_text(json.dumps(report))
        completed = subprocess.run([sys.executable, str(SCRIPT), "verify", "--project", str(self.project),
                                    "--change", "C-001", "--revision", "1", "--expect-digest", adopted["accepted_digest"],
                                    "--kit", str(kit.parent), "--receipt", str(receipt), "--check-id", "module:M-DATA"],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["coverage_issues"])
        self.assertEqual(result["status"]["current"][0]["module_verification"]["modules"][0]["state"], "failed")


if __name__ == "__main__":
    unittest.main()
