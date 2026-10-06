"""Portable security behavior tests; every project and marker is synthetic.

Run with unittest discovery from the repository root.
Optional verification tests use a synthetic Node entrypoint, never a real Kit.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/newbie_dev_buddy.py"


class SecurityRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="newbie-dev-buddy-security-")
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "sample space 中文 #(v1)"
        self.project.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src/value.txt").write_text("Synthetic input.\n", encoding="utf-8")
        self.note = self.base / "note.md"
        self.note.write_text("Synthetic test decision.\n", encoding="utf-8")
        self.mapping = {"title": "Synthetic project", "modules": [
            {"id": "M-DATA", "name": "Data", "purpose": "Store values",
             "contract": "Plain text", "paths": ["src"], "depends_on": []}]}
        self.map_json = self.json_file("map.json", self.mapping)
        self.call("init", "--map-json", self.map_json, "--decision-note-file", self.note)

    def tearDown(self):
        self.temp.cleanup()

    def json_file(self, name, value):
        path = self.base / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def raw(self, command, *args, timeout=4, project=None):
        return subprocess.run([sys.executable, str(SCRIPT), command, "--project",
                               str(project or self.project), *map(str, args)],
                              capture_output=True, text=True, timeout=timeout)

    def call(self, command, *args, ok=True, code=None, project=None):
        result = self.raw(command, *args, project=project)
        self.assertEqual(result.returncode, code if code is not None else (0 if ok else 1),
                         result.stdout + result.stderr)
        channel = result.stdout if ok or code == 2 else result.stderr
        self.assertNotIn("Traceback", result.stderr)
        return json.loads(channel)

    def proposal(self):
        spec = {"id": "C-001", "title": "Synthetic change", "primary": "M-DATA",
                "affected": [], "location": "value", "plan": "Update the stored value.",
                "acceptance": "The stored value is updated."}
        return self.call("propose", "--spec-json", self.json_file("proposal.json", spec))

    def accepted(self):
        proposal = self.proposal()
        result = self.call("decide", "--change", "C-001", "--revision", 1,
                           "--decision", "accept", "--expect-digest", proposal["digest"],
                           "--note-file", self.note)
        return proposal, result

    def implemented(self):
        proposal, adopted = self.accepted()
        for event in ("started", "implemented"):
            self.call("record", "--change", "C-001", "--revision", 1,
                      "--expect-digest", adopted["accepted_digest"], "--event", event,
                      "--note-file", self.note)
        return proposal, adopted

    def kit(self, body=None):
        if shutil.which("node") is None:
            self.skipTest("Node is unavailable for synthetic Kit tests")
        kit = self.base / "synthetic-kit"
        (kit / "bin").mkdir(parents=True)
        (kit / "bin/acceptance.mjs").write_text(body or
            'process.stdout.write(JSON.stringify({current: true, issues: []}));\n', encoding="utf-8")
        return kit

    def verify(self, adopted, receipt, kit, **options):
        return self.call("verify", "--change", "C-001", "--revision", 1,
                         "--expect-digest", adopted["accepted_digest"], "--kit", kit,
                         "--receipt", receipt, **options)

    def receipt(self, value=None):
        receipt = self.project / ".acceptance/synthetic/report.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(value if value is not None else {"status": "passed"}),
                           encoding="utf-8")
        return receipt

    def test_generated_links_are_relative_and_resolve_in_special_character_project(self):
        self.accepted()
        for name in ("CURRENT.md", "HISTORY.md"):
            index = self.project / ".handoff/newbie-dev-buddy" / name
            content = index.read_text(encoding="utf-8")
            self.assertNotIn(str(self.project), content)
            targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
            self.assertGreaterEqual(len(targets), 2)
            for target in targets:
                parts = urlsplit(target)
                self.assertEqual((parts.scheme, parts.netloc, parts.query, parts.fragment), ("", "", "", ""))
                self.assertFalse(Path(unquote(parts.path)).is_absolute())
                self.assertTrue((index.parent / unquote(parts.path)).is_file(), target)

    def test_hardlinked_module_document_cannot_disclose_external_content(self):
        outside = self.base / "outside-document.md"
        value = dict(self.mapping)
        value["modules"] = [dict(value["modules"][0], contract="SYNTHETIC_OUTSIDE_ONLY_MARKER")]
        outside.write_text("---\n" + json.dumps(value) + "\n---\n\n# Synthetic\n", encoding="utf-8")
        document = self.project / "docs/newbie-dev-buddy/MODULES.md"
        document.unlink()
        os.link(outside, document)
        result = self.raw("status")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("SYNTHETIC_OUTSIDE_ONLY_MARKER", result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stderr)["ok"])

    def test_nested_hardlinked_input_is_not_hashed(self):
        outside = self.base / "outside-value.txt"
        outside.write_text("SYNTHETIC_OUTSIDE_ONLY_VALUE\n", encoding="utf-8")
        expected_hash = hashlib.sha256(outside.read_bytes()).hexdigest()
        os.link(outside, self.project / "src/linked.txt")
        result = self.raw("propose", "--spec-json", self.json_file("proposal.json", {
            "id": "C-001", "title": "Synthetic change", "primary": "M-DATA", "affected": [],
            "location": "value", "plan": "Update value.", "acceptance": "Value updates."}))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn(expected_hash, result.stdout + result.stderr)
        self.assertFalse(list((self.project / ".handoff/newbie-dev-buddy/drafts").glob("*.md")))

    def test_nested_symlink_is_refused(self):
        outside = self.base / "outside.txt"
        outside.write_text("Synthetic outside marker\n", encoding="utf-8")
        (self.project / "src/link.txt").symlink_to(outside)
        self.call("propose", "--spec-json", self.json_file("proposal.json", {
            "id": "C-001", "title": "Synthetic change", "primary": "M-DATA", "affected": [],
            "location": "value", "plan": "Update value.", "acceptance": "Value updates."}), ok=False)

    def test_nonobject_module_has_structured_error(self):
        other = self.base / "other-project"
        other.mkdir()
        self.call("init", "--map-json", self.json_file("bad.json", {"modules": [0]}),
                  "--decision-note-file", self.note, project=other, ok=False)

    def test_nonobject_draft_baseline_has_structured_error(self):
        folder = self.project / ".handoff/newbie-dev-buddy/drafts"
        folder.mkdir(parents=True, exist_ok=True)
        metadata = {"id": "C-001", "revision": 1, "primary": "M-DATA", "affected": [],
                    "location": "value", "tracked_paths": ["src"], "baseline": []}
        (folder / "C-001-r1.md").write_text("---\n" + json.dumps(metadata) +
            "\n---\n\n# Synthetic malformed record\n", encoding="utf-8")
        self.call("status", ok=False)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Named pipes are unavailable")
    def test_fifo_module_document_is_refused_without_hanging(self):
        document = self.project / "docs/newbie-dev-buddy/MODULES.md"
        document.unlink()
        os.mkfifo(document)
        self.call("status", ok=False)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Named pipes are unavailable")
    def test_fifo_draft_is_refused_without_hanging(self):
        drafts = self.project / ".handoff/newbie-dev-buddy/drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        os.mkfifo(drafts / "C-PIPE-r1.md")
        self.call("status", ok=False)

    def test_missing_frontmatter_error_does_not_disclose_project_root(self):
        document = self.project / "docs/newbie-dev-buddy/MODULES.md"
        document.write_text("# Synthetic malformed document\n", encoding="utf-8")
        result = self.raw("status")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(str(self.project), result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stderr)["ok"])

    def test_existing_lock_error_does_not_disclose_project_root(self):
        lock = self.project / ".handoff/newbie-dev-buddy/write.lock"
        lock.write_text('{"pid": 999999, "synthetic": true}', encoding="utf-8")
        result = self.raw("refresh")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(str(self.project), result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stderr)["ok"])

    def test_accepted_content_tampering_is_refused_even_with_new_digest(self):
        _, adopted = self.accepted()
        document = self.project / adopted["path"]
        document.write_text(document.read_text(encoding="utf-8") + "Unpresented change.\n", encoding="utf-8")
        digest = hashlib.sha256(document.read_bytes()).hexdigest()
        self.call("record", "--change", "C-001", "--revision", 1, "--expect-digest", digest,
                  "--event", "started", "--note-file", self.note, ok=False)

    def test_outside_receipt_is_refused(self):
        _, adopted = self.implemented()
        outside = self.json_file("outside-report.json", {"status": "passed"})
        self.verify(adopted, outside, self.kit(), ok=False)

    def test_symlink_receipt_is_refused(self):
        _, adopted = self.implemented()
        outside = self.json_file("outside-report.json", {"status": "passed"})
        receipt = self.receipt()
        receipt.unlink()
        receipt.symlink_to(outside)
        self.verify(adopted, receipt, self.kit(), ok=False)

    def test_absolute_receipt_under_explicit_project_alias_is_supported(self):
        _, adopted = self.implemented()
        self.receipt()
        alias = self.base / "project-alias"
        alias.symlink_to(self.project, target_is_directory=True)
        result = self.verify(adopted, alias / ".acceptance/synthetic/report.json", self.kit(), project=alias)
        self.assertEqual(result["result"], "passed")

    def test_hardlinked_receipt_is_refused(self):
        _, adopted = self.implemented()
        outside = self.json_file("outside-report.json", {"status": "passed"})
        receipt = self.receipt()
        receipt.unlink()
        os.link(outside, receipt)
        self.verify(adopted, receipt, self.kit(), ok=False)

    def test_nonobject_receipt_has_structured_error(self):
        _, adopted = self.implemented()
        self.verify(adopted, self.receipt([]), self.kit(), ok=False)

    def test_failed_or_stale_check_is_recorded_as_failure(self):
        _, adopted = self.implemented()
        kit = self.kit('process.stdout.write(JSON.stringify({current: false, issues: ["synthetic stale input"]}));\n')
        result = self.verify(adopted, self.receipt(), kit, code=2)
        self.assertEqual(result["result"], "failed_or_stale")
        self.assertEqual(self.call("status")["current"][0]["verification"], "failed_or_stale")

    def test_kit_stderr_is_not_persisted_or_returned(self):
        _, adopted = self.implemented()
        kit = self.kit('process.stderr.write("SYNTHETIC_STDERR_ONLY_MARKER");\n'
                       'process.stdout.write(JSON.stringify({current: true, issues: []}));\n')
        result = self.verify(adopted, self.receipt(), kit)
        self.assertEqual(result["result"], "passed")
        self.assertNotIn("SYNTHETIC_STDERR_ONLY_MARKER", json.dumps(result))
        for path in self.project.rglob("*.md"):
            self.assertNotIn("SYNTHETIC_STDERR_ONLY_MARKER", path.read_text(encoding="utf-8"))

    def test_input_mutation_during_kit_check_is_refused(self):
        _, adopted = self.implemented()
        kit = self.kit('import fs from "node:fs";\nimport path from "node:path";\n'
                       'const project = process.argv[process.argv.indexOf("--project") + 1];\n'
                       'fs.writeFileSync(path.join(project, "src/value.txt"), "Synthetic mutation.\\n");\n'
                       'process.stdout.write(JSON.stringify({current: true, issues: []}));\n')
        self.verify(adopted, self.receipt(), kit, ok=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
