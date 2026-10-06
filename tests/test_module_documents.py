"""Module-data/view consistency, legacy preservation and ordinary write recovery."""
from argparse import Namespace
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import newbie_dev_buddy as buddy
from module_documents import readable_document, serialized


class ModuleDocumentsTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    call = fixtures.WorkflowTests.call
    json_file = fixtures.WorkflowTests.json_file
    proposal = fixtures.WorkflowTests.proposal
    accept = fixtures.WorkflowTests.accept

    @property
    def source(self):
        return self.project / buddy.DOCS / "MODULES.json"

    @property
    def view(self):
        return self.project / buddy.DOCS / "MODULES.md"

    def render(self):
        return self.call("map-render", "--expect-digest", buddy.digest(self.source))

    def legacy(self):
        data = json.loads(self.source.read_text())
        self.source.unlink()
        content = buddy.md(data, "# Legacy view\n\nOriginal manually written detail.")
        self.view.write_text(content)
        return data, content

    def test_initial_map_has_readable_view_and_complete_source(self):
        data = json.loads(self.source.read_text())
        view = self.view.read_text()
        self.assertFalse(view.startswith("---\n"))
        self.assertIn("Data（M-DATA）", view)
        self.assertIn("Keep values as plain text.", view)
        self.assertIn("尚未配置，不能算作通过", view)
        self.assertIn(buddy.digest(self.source), view)
        self.assertEqual(data["map_revision"], 0)
        self.assertEqual(self.call("status")["module_format"], "json-and-markdown")

    def test_handwritten_view_is_rejected_then_preserved_without_adoption(self):
        original = self.source.read_bytes()
        edited = self.view.read_text() + "\nMy suggested boundary.\n"
        self.view.write_text(edited)
        error = self.call("status", ok=False)["error"]
        self.assertIn("out of sync", error)
        self.assertNotIn(str(self.project), error)
        self.render()
        self.assertEqual(self.source.read_bytes(), original)
        archives = list((self.project / buddy.STATE / "maps/repairs").glob("*.md"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_text(), edited)
        self.assertNotIn("My suggested boundary", self.view.read_text())

    def test_repair_preserves_handwritten_crlf_bytes(self):
        edited = self.view.read_bytes().replace(b"\n", b"\r\n") + b"Suggestion\r\n"
        self.view.write_bytes(edited)
        self.render()
        archives = list((self.project / buddy.STATE / "maps/repairs").glob("*.md"))
        self.assertEqual(archives[0].read_bytes(), edited)

    def test_json_byte_change_invalidates_view_and_pending_plan(self):
        proposed = self.proposal()
        self.source.write_text(self.source.read_text() + "\n")
        self.call("status", ok=False)
        self.render()
        self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "accept",
                  "--expect-digest", proposed["digest"], "--note-file", self.note, ok=False)

    def test_missing_view_can_be_rebuilt_but_is_not_silently_ignored(self):
        content = self.view.read_text()
        self.view.unlink()
        self.call("status", ok=False)
        self.render()
        self.assertEqual(self.view.read_text(), content)

    def test_accepted_map_update_updates_pair_and_archives_both_originals(self):
        old_json, old_md = self.source.read_bytes(), self.view.read_bytes()
        scan = self.call("scan")
        data = json.loads(old_json)
        data["modules"][0]["contract"] = "Keep text; never delete values without confirmation."
        candidate = self.call("map-propose", "--scan", scan["path"], "--map-json", self.json_file("updated.json", data))
        _, body = buddy.read_md(self.project / candidate["path"])
        self.assertIn("这是待确认的模块分工", body)
        self.assertIn("版本：" + str(candidate["revision"]), body)
        self.call("map-decide", "--revision", candidate["revision"], "--expect-digest", candidate["digest"],
                  "--decision", "accept", "--note-file", self.note)
        stem = hashlib.sha256(old_md).hexdigest()
        history = self.project / buddy.STATE / "maps/history"
        self.assertEqual((history / (stem + ".md")).read_bytes(), old_md)
        self.assertEqual((history / (stem + ".json")).read_bytes(), old_json)
        self.assertIn(data["modules"][0]["contract"], self.view.read_text())
        self.assertEqual(json.loads(self.source.read_text())["modules"][0]["id"], "M-DATA")
        self.call("status")

    def test_legacy_status_does_not_migrate_and_migration_preserves_original(self):
        data, original = self.legacy()
        self.assertEqual(self.call("status")["module_format"], "legacy-markdown")
        self.assertFalse(self.source.exists())
        sha = buddy.digest(self.view)
        self.call("map-migrate", "--expect-digest", sha)
        self.assertEqual(json.loads(self.source.read_text()), data)
        self.assertEqual((self.project / buddy.STATE / "maps/history" / (sha + ".md")).read_text(), original)
        self.assertFalse(self.view.read_text().startswith("---"))

    def test_migration_retains_accepted_records_but_marks_prior_inputs_changed(self):
        self.legacy()
        accepted = self.accept(self.proposal())
        plan = self.project / accepted["path"]
        original = plan.read_bytes()
        self.call("map-migrate", "--expect-digest", buddy.digest(self.view))
        self.assertEqual(plan.read_bytes(), original)
        self.assertTrue(self.call("status")["current"][0]["drift"])

    def test_wrong_selected_digest_cannot_migrate_or_rebuild(self):
        self.call("map-render", "--expect-digest", "0" * 64, ok=False)
        self.legacy()
        self.call("map-migrate", "--expect-digest", "0" * 64, ok=False)
        self.assertFalse(self.source.exists())

    def test_source_links_are_rejected(self):
        original = self.source.read_bytes()
        external = self.base / "external.json"
        external.write_bytes(original)
        self.source.unlink()
        self.source.symlink_to(external)
        self.call("status", ok=False)
        self.source.unlink()
        os.link(external, self.source)
        self.call("status", ok=False)
        self.assertEqual(external.read_bytes(), original)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO needs POSIX")
    def test_source_fifo_is_rejected_without_blocking(self):
        self.source.unlink()
        os.mkfifo(self.source)
        result = fixtures.subprocess.run([sys.executable, str(fixtures.SCRIPT), "status", "--project", str(self.project)],
                                         capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 1)
        self.assertIn("special project files", result.stderr)

    def test_write_failure_restores_both_existing_documents(self):
        before = self.source.read_bytes(), self.view.read_bytes()
        data = json.loads(before[0])
        data["modules"][0]["name"] = "New name"
        actual_write = buddy.write

        def fail_view(root, relative, content, **kwargs):
            if relative.endswith("MODULES.md"):
                raise OSError("Synthetic disk failure")
            return actual_write(root, relative, content, **kwargs)

        with patch.object(buddy, "write", side_effect=fail_view):
            with self.assertRaises(OSError):
                buddy.write_module_map(self.project.resolve(), data)
        self.assertEqual((self.source.read_bytes(), self.view.read_bytes()), before)

    def test_initial_write_failure_is_retryable(self):
        import shutil
        shutil.rmtree(self.project / buddy.DOCS)
        args = Namespace(map_json=str(self.mapping), decision_note_file=str(self.note))
        actual_write = buddy.write

        def fail_view(root, relative, content, **kwargs):
            if relative.endswith("MODULES.md"):
                raise OSError("Synthetic disk failure")
            return actual_write(root, relative, content, **kwargs)

        with patch.object(buddy, "write", side_effect=fail_view):
            with self.assertRaises(OSError):
                buddy.initialize(self.project.resolve(), args)
        self.assertFalse((self.project / buddy.DOCS).exists())
        self.call("init", "--map-json", self.mapping, "--decision-note-file", self.note)

    def test_readable_view_preserves_conditions_negation_and_extra_fields(self):
        data = json.loads(self.source.read_text())
        data["modules"][0]["purpose"] = "只在确认后导出；不删除数据。"
        data["modules"][0]["not_responsible"] = "不上传"
        data["retention_days"] = 30
        source = serialized(data)
        view = readable_document(data, source)
        self.assertIn("只在确认后导出；不删除数据。", view)
        self.assertIn('"not_responsible": "不上传"', view)
        self.assertIn('"retention_days": 30', view)
        self.assertNotIn("已经通过全部检查", view)

    def test_repeated_view_repairs_preserve_same_view_with_different_json(self):
        edited = self.view.read_text() + "\nSuggestion\n"
        self.view.write_text(edited)
        self.render()
        self.view.write_text(edited)
        self.source.write_text(self.source.read_text() + "\n")
        self.render()
        archives = list((self.project / buddy.STATE / "maps/repairs").glob("*.md"))
        self.assertEqual(len(archives), 2)
        self.assertTrue(all(p.read_text() == edited for p in archives))


if __name__ == "__main__":
    unittest.main()
