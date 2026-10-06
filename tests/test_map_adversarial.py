"""Module-map integrity and drift regressions with synthetic projects only."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/newbie_dev_buddy.py"


class MapAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="module-map-adversarial-")
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        (self.project / "src/old").mkdir(parents=True)
        (self.project / "src/current").mkdir(parents=True)
        (self.project / "src/old/value.txt").write_text("old synthetic value\n")
        (self.project / "src/current/value.txt").write_text("current synthetic value\n")
        self.note = self.base / "decision.md"
        self.note.write_text("Synthetic decision note.\n")
        self.mapping = {"title": "Synthetic project", "modules": [
            {"id": "M-OLD", "name": "Old", "purpose": "Old synthetic responsibility",
             "paths": ["src/old"], "depends_on": [], "contract": "Plain text."},
            {"id": "M-CURRENT", "name": "Current", "purpose": "Current synthetic responsibility",
             "paths": ["src/current"], "depends_on": [], "contract": "Plain text."}]}
        self.call("init", "--map-json", self.json_file("initial.json", self.mapping),
                  "--decision-note-file", self.note)

    def tearDown(self):
        self.temp.cleanup()

    def json_file(self, name, data):
        path = self.base / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def raw(self, command, *args):
        return subprocess.run([sys.executable, str(SCRIPT), command, "--project", str(self.project),
                               *map(str, args)], capture_output=True, text=True, timeout=5)

    def call(self, command, *args, ok=True):
        result = self.raw(command, *args)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return json.loads(result.stdout if ok else result.stderr)

    def proposal(self, mapping=None, lineage=None):
        scan = self.call("scan")
        args = ["--map-json", self.json_file("candidate.json", mapping or self.mapping), "--scan", scan["path"]]
        if lineage is not None:
            args += ["--lineage-json", self.json_file("lineage.json", lineage)]
        return self.call("map-propose", *args)

    def decision(self, proposal, ok=True, decision="accept"):
        return self.call("map-decide", "--revision", proposal["revision"], "--expect-digest", proposal["digest"],
                         "--decision", decision, "--note-file", self.note, ok=ok)

    def retire_old(self):
        reduced = copy.deepcopy(self.mapping)
        reduced["modules"] = reduced["modules"][1:]
        proposal = self.proposal(reduced, [{"from": ["M-OLD"], "to": [], "reason": "Synthetic retirement."}])
        return self.decision(proposal)

    def edit_record(self, relative, update):
        path = self.project / relative
        content = path.read_text(encoding="utf-8")
        header, body = content[4:].split("\n---\n", 1)
        metadata = json.loads(header)
        update(metadata)
        rewritten = "---\n" + json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n---\n\n" + body.lstrip("\n")
        path.write_text(rewritten, encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def metadata(self, relative):
        header = (self.project / relative).read_text(encoding="utf-8")[4:].split("\n---\n", 1)[0]
        return json.loads(header)

    def test_normal_retired_id_reuse_is_blocked(self):
        self.retire_old()
        scan = self.call("scan")
        result = self.call("map-propose", "--map-json", self.json_file("reuse.json", self.mapping),
                           "--scan", scan["path"], ok=False)
        self.assertIn("retired", result["error"])

    def test_tampered_accepted_lineage_cannot_reactivate_retired_id(self):
        adopted = self.retire_old()
        self.edit_record(adopted["path"], lambda metadata: metadata.update(lineage=[]))
        scan = self.call("scan")
        self.call("map-propose", "--map-json", self.json_file("reuse.json", self.mapping),
                  "--scan", scan["path"], ok=False)

    def test_tampered_draft_cannot_reactivate_retired_id_with_new_digest(self):
        self.retire_old()
        reduced = copy.deepcopy(self.mapping)
        reduced["modules"] = reduced["modules"][1:]
        proposal = self.proposal(reduced)

        def reuse(metadata):
            metadata["mapping"] = copy.deepcopy(self.mapping)
            metadata["difference"]["added"] = ["M-OLD"]

        proposal["digest"] = self.edit_record(proposal["path"], reuse)
        self.decision(proposal, ok=False)

    def test_tampered_draft_cannot_remove_module_without_lineage(self):
        proposal = self.proposal()

        def remove(metadata):
            metadata["mapping"]["modules"] = metadata["mapping"]["modules"][1:]
            metadata["difference"]["removed"] = ["M-OLD"]

        proposal["digest"] = self.edit_record(proposal["path"], remove)
        self.decision(proposal, ok=False)

    def test_scanned_source_edit_add_and_delete_block_map_acceptance(self):
        proposal = self.proposal()
        original = self.project / "src/old/value.txt"
        added = self.project / "src/new.txt"
        original.write_text("changed synthetic value\n")
        self.assertIn("scanned source changed", self.decision(proposal, ok=False)["error"])
        original.write_text("old synthetic value\n")
        added.write_text("new synthetic value\n")
        self.assertIn("scanned source changed", self.decision(proposal, ok=False)["error"])
        added.unlink()
        original.unlink()
        self.assertIn("scanned source changed", self.decision(proposal, ok=False)["error"])

    def test_current_map_change_blocks_acceptance_even_though_discovery_excludes_it(self):
        proposal = self.proposal()
        current = self.project / "docs/newbie-dev-buddy/MODULES.md"
        current.write_text(current.read_text(encoding="utf-8") + "\nSynthetic external edit.\n", encoding="utf-8")
        self.assertIn("current module map changed", self.decision(proposal, ok=False)["error"])

    def test_selected_scan_tampering_blocks_map_acceptance(self):
        proposal = self.proposal()
        scan = self.metadata(proposal["path"])["scan"]
        self.edit_record(scan, lambda metadata: metadata["inventory"]["warnings"].append("Synthetic changed warning."))
        self.assertIn("scan record changed", self.decision(proposal, ok=False)["error"])

    def test_corrupt_history_backup_blocks_adoption_before_decision_is_written(self):
        proposal = self.proposal()
        current = self.project / "docs/newbie-dev-buddy/MODULES.md"
        previous_digest = hashlib.sha256(current.read_bytes()).hexdigest()
        backup = self.project / ".handoff/newbie-dev-buddy/maps/history" / (previous_digest + ".md")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text("Synthetic corrupted history.\n")
        self.assertIn("previous map archive changed", self.decision(proposal, ok=False)["error"])
        self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(), previous_digest)
        self.assertFalse((self.project / ".handoff/newbie-dev-buddy/maps/accepted/MAP-r1.md").exists())

    def test_conflicting_change_directory_cannot_consume_map_decision(self):
        proposal = self.proposal()
        current = self.project / "docs/newbie-dev-buddy/MODULES.md"
        previous_digest = hashlib.sha256(current.read_bytes()).hexdigest()
        change_directory = self.project / "docs/newbie-dev-buddy/changes"
        change_directory.rmdir()
        change_directory.write_text("Synthetic conflicting file.\n")
        self.decision(proposal, ok=False)
        self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(), previous_digest)
        self.assertFalse((self.project / ".handoff/newbie-dev-buddy/maps/accepted/MAP-r1.md").exists())

    def test_malformed_change_record_does_not_half_apply_map_acceptance(self):
        updated = copy.deepcopy(self.mapping)
        updated["modules"][0]["name"] = "Updated synthetic name"
        proposal = self.proposal(updated)
        current = self.project / "docs/newbie-dev-buddy/MODULES.md"
        previous_digest = hashlib.sha256(current.read_bytes()).hexdigest()
        broken = self.project / ".handoff/newbie-dev-buddy/drafts/C-BROKEN-r1.md"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text('---\n{"schema": 1}\n---\n\n# Synthetic malformed draft\n')
        self.decision(proposal, ok=False)
        self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(), previous_digest)
        self.assertFalse((self.project / ".handoff/newbie-dev-buddy/maps/accepted/MAP-r1.md").exists())

    def test_map_update_preserves_old_proposal_scope_and_blocks_stale_start(self):
        spec = {"id": "C-001", "title": "Synthetic old scope", "primary": "M-OLD", "affected": [],
                "location": "value", "plan": "Update the old value.", "acceptance": "Old value updates.",
                "documentation": {"files": [], "map_updates": {}, "map_reason": "Stored value format is unchanged."}}
        proposal = self.call("propose", "--spec-json", self.json_file("change.json", spec))
        approved = self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "accept",
                             "--expect-digest", proposal["digest"], "--note-file", self.note)
        previous = self.metadata(approved["path"])
        updated = copy.deepcopy(self.mapping)
        updated["modules"][0]["paths"].append("src/future")
        self.decision(self.proposal(updated))
        current = self.metadata(approved["path"])
        self.assertEqual(previous["tracked_paths"], current["tracked_paths"])
        self.assertNotIn("src/future", current["tracked_paths"])
        result = self.call("record", "--change", "C-001", "--revision", 1, "--event", "started",
                           "--expect-digest", approved["accepted_digest"], "--note-file", self.note, ok=False)
        self.assertIn("inputs changed", result["error"])


if __name__ == "__main__":
    unittest.main()
