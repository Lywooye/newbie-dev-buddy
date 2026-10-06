"""Observable documentation closure, provenance, scope and legacy follow-ups."""
from argparse import Namespace
from datetime import datetime
import json
import os
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from test_workflow import buddy


class DocumentationClosureTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    call = fixtures.WorkflowTests.call
    json_file = fixtures.WorkflowTests.json_file
    proposal = fixtures.WorkflowTests.proposal
    accept = fixtures.WorkflowTests.accept
    record = fixtures.WorkflowTests.record
    completion = fixtures.WorkflowTests.completion

    def begin(self, documentation=None):
        fields = {} if documentation is None else {"documentation": documentation}
        p = self.proposal(**fields)
        a = self.accept(p)
        self.record(p, a, "started")
        return p, a

    def close(self, p, a, manifest, event="implemented", ok=True):
        path = self.base / "close.json"
        path.write_text(json.dumps(manifest))
        return self.call("record", "--change", p["change"], "--revision", p["revision"],
                         "--expect-digest", a["accepted_digest"], "--event", event,
                         "--completion-json", path, "--note-file", self.note, ok=ok)

    def docs(self, **updates):
        return {"files": ["requirements.md"], "map_updates": {"M-DATA": updates} if updates else {},
                "map_reason": "Store values as labeled UTF-8 text and update the requirement."}

    def edit(self):
        (self.project / "src/value.txt").write_text("value=new\n")
        (self.project / "requirements.md").write_text("Values have a value= label.\n")
        return {"files": [{"path": "src/value.txt", "summary": "Prefix the stored value with value=."},
                          {"path": "requirements.md", "summary": "Describe the new value= label."}]}

    def test_missing_documentation_is_rejected_before_acceptance(self):
        path = self.base / "missing.json"
        path.write_text(json.dumps({"id": "C-001", "title": "Change", "primary": "M-DATA",
                                    "location": "value", "plan": "Change value", "acceptance": "New value"}))
        result = self.call("propose", "--spec-json", path, ok=False)
        self.assertIn("documentation plan required", result["error"])

    def test_cannot_skip_closure_and_claim_implementation(self):
        p, a = self.begin()
        self.record(p, a, "implemented", ok=False)
        state = self.call("status")["current"][0]
        self.assertEqual(state["execution"], "started")
        self.assertFalse(state["handoff_ready"])

    def test_contract_and_both_views_sync_with_exact_history_and_times(self):
        os.utime(self.project / "src/value.txt", (1000000000, 1000000000))
        old = {ext: (self.project / buddy.DOCS / ("MODULES." + ext)).read_bytes() for ext in ("md", "json")}
        p, a = self.begin(self.docs(contract="Each UTF-8 value starts with value=."))
        accepted_bytes = (self.project / a["path"]).read_bytes()
        result = self.close(p, a, self.edit())
        mapping = buddy.module_map(self.project)
        self.assertEqual(mapping["modules"][0]["contract"], "Each UTF-8 value starts with value=.")
        self.assertEqual(mapping["map_revision"], 1)
        self.assertEqual((self.project / a["path"]).read_bytes(), accepted_bytes)
        for ext in old:
            archive = self.project / buddy.STATE / "maps/history" / (buddy.hashlib.sha256(old["md"]).hexdigest() + "." + ext)
            self.assertEqual(archive.read_bytes(), old[ext])
        meta, body = buddy.read_md(self.project / result["path"])
        self.assertEqual(meta["created"], mapping["updated_at"])
        self.assertEqual(meta["documentation"]["at"], mapping["updated_at"])
        self.assertGreater(datetime.fromisoformat(meta["created"]), datetime.fromisoformat(meta["implementation_started_at"]))
        entry = next(i for i in meta["file_changes"] if i["path"] == "src/value.txt")
        self.assertEqual(datetime.fromisoformat(entry["before_mtime"]).timestamp(), 1000000000)
        self.assertNotEqual(entry["before_sha256"], entry["after_sha256"])
        self.assertIn("Prefix the stored value", body)
        state = self.call("status")["current"][0]
        self.assertEqual(state["documentation"]["state"], "synced")
        self.assertTrue(state["handoff_ready"])
        self.assertEqual(state["verification"], "not_run")

    def test_interrupted_then_resumed_work_retains_earlier_file_changes(self):
        p, a = self.begin()
        (self.project / "src/value.txt").write_text("partial\n")
        self.record(p, a, "interrupted")
        self.record(p, a, "started")
        (self.project / "requirements.md").write_text("Revised requirement\n")
        self.close(p, a, {"files": [{"path": "requirements.md", "summary": "Revised"}]}, ok=False)
        result = self.close(p, a, {"files": [{"path": "src/value.txt", "summary": "Earlier partial edit"},
                                            {"path": "requirements.md", "summary": "Later requirement edit"}]})
        meta, _ = buddy.read_md(self.project / result["path"])
        starts = [e[0] for e in buddy.execution_events(self.project, "C-001", 1) if e[0]["event"] == "started"]
        self.assertEqual(meta["implementation_started_at"], starts[0]["created"])

    def test_cannot_omit_or_invent_changed_file_summaries(self):
        p, a = self.begin()
        (self.project / "src/value.txt").write_text("new\n")
        for files in ([], [{"path": "src/ui.txt", "summary": "Invented"}],
                      [{"path": "src/value.txt", "summary": "Updated"}, {"path": "requirements.md", "summary": "Not changed"}]):
            result = self.close(p, a, {"files": files}, ok=False)
            self.assertIn("exactly", result["error"])
        self.assertEqual(self.call("status")["current"][0]["execution"], "started")

    def test_unchanged_doc_requires_review_and_deleted_doc_cannot_close(self):
        p, a = self.begin(self.docs())
        result = self.close(p, a, {"files": []}, ok=False)
        self.assertIn("review reason", result["error"])
        self.close(p, a, {"files": [], "reviewed_documents": {"requirements.md": "Existing UTF-8 requirement still covers this no-op."}})
        self.record(p, a, "started")
        (self.project / "requirements.md").unlink()
        result = self.close(p, a, {"files": [{"path": "requirements.md", "summary": "Removed"}]}, ok=False)
        self.assertIn("missing", result["error"])

    def test_structural_and_out_of_scope_map_edits_are_rejected(self):
        for updates in ({"M-DATA": {"paths": ["src"]}}, {"M-UI": {"contract": "Changed"}}):
            p = self.json_file("bad.json", {"id": "C-001", "title": "Change", "primary": "M-DATA",
                "location": "value", "plan": "Change", "acceptance": "New", "documentation": {
                    "files": [], "map_updates": updates, "map_reason": "Change contract"}})
            self.call("propose", "--spec-json", p, ok=False)

    def test_closure_cannot_override_accepted_text_or_supply_a_timestamp(self):
        p, a = self.begin()
        for extra in ({"documentation": self.docs(contract="Unaccepted")}, {"created": "2000-01-01"}):
            self.close(p, a, {"files": [], **extra}, ok=False)

    def test_external_map_change_blocks_frozen_plan(self):
        p, a = self.begin()
        mapping = buddy.module_map(self.project)
        mapping["modules"][0]["contract"] = "Another change"
        buddy.write_module_map(self.project, mapping)
        result = self.close(p, a, {"files": []}, ok=False)
        self.assertIn("map changed", result["error"])

    def test_file_drift_and_new_execution_clear_readiness(self):
        p, a = self.begin()
        self.close(p, a, {"files": []})
        self.record(p, a, "started")
        state = self.call("status")["current"][0]
        self.assertEqual(state["documentation"]["state"], "pending")
        self.close(p, a, {"files": []})
        (self.project / "src/value.txt").write_text("external\n")
        state = self.call("status")["current"][0]
        self.assertEqual(state["documentation"]["state"], "needs_review")
        self.assertFalse(state["handoff_ready"])

    def test_event_write_failure_restores_map_and_allows_retry(self):
        p, a = self.begin(self.docs(contract="Each value has a label."))
        manifest = self.edit()
        path = self.base / "close.json"
        path.write_text(json.dumps(manifest))
        originals = {ext: (self.project / buddy.DOCS / ("MODULES." + ext)).read_bytes() for ext in ("json", "md")}
        data, _ = buddy.accepted(self.project, p["change"], p["revision"])
        started = buddy.execution_events(self.project, p["change"], p["revision"])[-1][0]
        args = Namespace(completion_json=path, note_file=self.note, event="implemented")
        with patch.object(buddy, "event", side_effect=OSError("Synthetic record write failure")):
            with self.assertRaises(OSError):
                buddy.complete_implementation(self.project, args, data, started)
        for ext in originals:
            self.assertEqual((self.project / buddy.DOCS / ("MODULES." + ext)).read_bytes(), originals[ext])
        self.close(p, a, manifest)
        self.assertTrue(self.call("status")["current"][0]["handoff_ready"])

    def legacy(self):
        p = self.proposal()
        a = self.accept(p)
        draft_path = self.project / p["path"]
        data, body = buddy.read_md(draft_path)
        data.pop("documentation_plan")
        draft_path.write_text(buddy.md(data, body))
        accepted, accepted_body = buddy.read_md(self.project / a["path"])
        accepted.pop("documentation_plan")
        accepted["proposal_digest"] = buddy.digest(draft_path)
        (self.project / a["path"]).write_text(buddy.md(accepted, accepted_body))
        a["accepted_digest"] = buddy.digest(self.project / a["path"])
        self.record(p, a, "started")
        self.edit()
        result = self.call("record", "--change", p["change"], "--revision", p["revision"],
                           "--expect-digest", a["accepted_digest"], "--event", "implemented", "--note-file", self.note)
        return p, a, result

    def test_legacy_followup_preserves_implementation_time_and_original_records(self):
        p, a, impl = self.legacy()
        before = {path: path.read_bytes() for path in [self.project / a["path"], self.project / impl["path"]]}
        old_meta, _ = buddy.read_md(self.project / impl["path"])
        state = self.call("status")["current"][0]
        self.assertEqual(state["documentation"]["state"], "legacy_unreviewed")
        self.assertFalse(state["handoff_ready"])
        manifest = self.edit()
        manifest["documentation"] = self.docs(contract="Each value has the value= prefix.")
        result = self.close(p, a, manifest, event="documented")
        new_meta, _ = buddy.read_md(self.project / result["path"])
        self.assertGreater(new_meta["created"], old_meta["created"])
        self.assertEqual(new_meta["implementation_recorded_at"], old_meta["created"])
        self.assertTrue(new_meta["documentation"]["legacy_followup"])
        for path in before:
            self.assertEqual(path.read_bytes(), before[path])
        self.assertTrue(self.call("status")["current"][0]["handoff_ready"])

    def test_new_plans_cannot_use_legacy_escape_hatch(self):
        p, a = self.begin()
        self.close(p, a, {"files": []}, event="documented", ok=False)

    def test_bad_reserved_map_reference_is_rejected_without_traceback(self):
        mapping = buddy.module_map(self.project)
        mapping["last_change"] = {"change": "C-001", "revision": 1, "at": "now", "record": "../../outside"}
        with self.assertRaises(ValueError):
            buddy.validate_map(mapping)

    def test_next_map_proposal_advances_after_automatic_sync(self):
        p, a = self.begin(self.docs(contract="Each value has a label."))
        self.close(p, a, self.edit())
        scan = self.call("scan")
        candidate = self.json_file("next-map.json", buddy.module_map(self.project))
        result = self.call("map-propose", "--scan", scan["path"], "--map-json", candidate)
        self.assertEqual(result["revision"], 2)
