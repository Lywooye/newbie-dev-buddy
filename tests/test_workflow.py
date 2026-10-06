"""Behavior tests through the public CLI; all projects and decisions are synthetic."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import newbie_dev_buddy as buddy


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/newbie_dev_buddy.py"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="newbie-dev-buddy-test-")
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "src").mkdir()
        (self.project / "src/value.txt").write_text("old\n")
        (self.project / "requirements.md").write_text("Synthetic requirement: export in UTF-8.\n")
        self.note = self.base / "decision.md"
        self.note.write_text("Synthetic test decision; not real human authorization.\n")
        mapping = {"title": "Synthetic project", "context": ["requirements.md"], "modules": [
            {"id": "M-DATA", "name": "Data", "purpose": "Store values", "paths": ["src/value.txt"],
             "depends_on": [], "contract": "Keep values as plain text."},
            {"id": "M-UI", "name": "UI", "purpose": "Read values", "paths": ["src/ui.txt"],
             "depends_on": ["M-DATA"], "contract": "Display stored values."}]}
        self.mapping = self.json_file("map.json", mapping)
        self.call("init", "--map-json", self.mapping, "--decision-note-file", self.note)

    def tearDown(self):
        self.temp.cleanup()

    def json_file(self, name, value):
        if isinstance(value, dict) and "plan" in value and "primary" in value:
            value = dict(value)
            value.setdefault("documentation", {"files": [], "map_updates": {},
                                               "map_reason": "The synthetic value change preserves the registered text format."})
        path = self.base / name
        path.write_text(json.dumps(value))
        return path

    def call(self, command, *args, ok=True):
        completed = subprocess.run([sys.executable, str(SCRIPT), command, "--project", str(self.project),
                                    *map(str, args)], capture_output=True, text=True)
        self.assertEqual(completed.returncode == 0, ok, completed.stdout + completed.stderr)
        return json.loads(completed.stdout if ok else completed.stderr)

    def proposal(self, change="C-001", **fields):
        spec = {"id": change, "title": "Change a stored value", "primary": "M-DATA", "affected": [],
                "location": "stored value", "plan": "Change value, keep UI compatible.",
                "acceptance": "New value appears in output; old format still parses.", **fields}
        return self.call("propose", "--spec-json", self.json_file("proposal.json", spec))

    def accept(self, proposal):
        return self.call("decide", "--change", proposal["change"], "--revision", proposal["revision"],
                         "--decision", "accept", "--expect-digest", proposal["digest"], "--note-file", self.note)

    def completion(self, proposal):
        data, _ = buddy.accepted(self.project, proposal["change"], proposal["revision"])
        events = buddy.execution_events(self.project, proposal["change"], proposal["revision"])
        starts = [e[0] for e in events if e[0]["event"] == "started"]
        before = buddy.implementation_start(events, starts[-1])["inputs"] if starts else data["baseline"]
        after = buddy.current_inputs(self.project, data)
        automatic = {buddy.DOCS + "/MODULES.json", buddy.DOCS + "/MODULES.md"}
        paths = [p for p in buddy.changed(before, after) if p not in automatic and
                 (before.get(p) not in {None, "<directory>", "<missing>"} or after.get(p) not in {None, "<directory>", "<missing>"})]
        return self.json_file("completion.json", {"files": [{"path": p, "summary": "Synthetic fixture edit to " + p} for p in paths]})

    def record(self, proposal, adopted, event, ok=True):
        completion = ["--completion-json", WorkflowTests.completion(self, proposal)] if event == "implemented" and ok else []
        return self.call("record", "--change", proposal["change"], "--revision", proposal["revision"],
                         "--expect-digest", adopted["accepted_digest"], "--event", event,
                         "--note-file", self.note, *completion, ok=ok)

    def test_accepted_is_not_implemented_or_verified(self):
        result = self.accept(self.proposal())
        state = result["status"]["current"][0]
        self.assertEqual(state["execution"], "not_started")
        self.assertEqual(state["verification"], "not_run")
        self.assertEqual(state["drift"], [])

    def test_cannot_record_unaccepted_or_skip_start(self):
        p = self.proposal()
        self.call("record", "--change", "C-001", "--revision", 1, "--expect-digest", p["digest"],
                  "--event", "started", "--note-file", self.note, ok=False)
        adopted = self.accept(p)
        self.record(p, adopted, "implemented", ok=False)

    def test_new_draft_does_not_replace_accepted_plan(self):
        first = self.proposal()
        adopted = self.accept(first)
        self.proposal(plan="A different candidate plan.")
        state = self.call("status")
        self.assertEqual(state["current"][0]["revision"], 1)
        self.assertEqual(state["current"][0]["drift"], [])
        self.record(first, adopted, "started")

    def test_reject_preserves_draft_and_blocks_execution(self):
        p = self.proposal()
        self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "reject",
                  "--expect-digest", p["digest"], "--note-file", self.note)
        self.assertTrue((self.project / p["path"]).is_file())
        self.assertEqual(self.call("status")["current"], [])

    def test_obsolete_revision_cannot_be_accepted(self):
        first = self.proposal()
        self.proposal(plan="Revised plan.")
        self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "accept",
                  "--expect-digest", first["digest"], "--note-file", self.note, ok=False)

    def test_requirements_drift_blocks_acceptance(self):
        p = self.proposal()
        (self.project / "requirements.md").write_text("Changed requirement.\n")
        result = self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "accept",
                           "--expect-digest", p["digest"], "--note-file", self.note, ok=False)
        self.assertIn("baseline", result["error"])

    def test_proposal_tampering_is_detected(self):
        p = self.proposal()
        with (self.project / p["path"]).open("a") as stream:
            stream.write("Unpresented change.\n")
        self.call("decide", "--change", "C-001", "--revision", 1, "--decision", "accept",
                  "--expect-digest", p["digest"], "--note-file", self.note, ok=False)

    def test_interrupted_work_can_resume_without_losing_events(self):
        p = self.proposal()
        adopted = self.accept(p)
        self.record(p, adopted, "started")
        (self.project / "src/value.txt").write_text("partial\n")
        self.record(p, adopted, "interrupted")
        self.record(p, adopted, "started")
        (self.project / "src/value.txt").write_text("final\n")
        self.record(p, adopted, "implemented")
        events = list((self.project / ".handoff/newbie-dev-buddy/records").glob("*.md"))
        self.assertEqual(len(events), 4)
        self.assertEqual(self.call("status")["current"][0]["drift"], [])

    def test_external_change_after_interruption_is_flagged(self):
        p = self.proposal()
        adopted = self.accept(p)
        self.record(p, adopted, "started")
        self.record(p, adopted, "interrupted")
        (self.project / "src/value.txt").write_text("external change\n")
        self.assertIn("src/value.txt", self.call("status")["current"][0]["drift"])
        self.record(p, adopted, "started", ok=False)

    def test_new_accepted_revision_preserves_old_but_blocks_execution(self):
        p1 = self.proposal()
        adopted1 = self.accept(p1)
        old = (self.project / adopted1["path"]).read_bytes()
        p2 = self.proposal(plan="Replacement plan.")
        self.accept(p2)
        self.assertEqual((self.project / adopted1["path"]).read_bytes(), old)
        self.assertEqual(self.call("status")["current"][0]["revision"], 2)
        self.record(p1, adopted1, "started", ok=False)
        current = (self.project / ".handoff/newbie-dev-buddy/CURRENT.md").read_text()
        history = (self.project / ".handoff/newbie-dev-buddy/HISTORY.md").read_text()
        self.assertNotIn("## C-001 r1", current)
        self.assertIn("## C-001 r2", current)
        self.assertIn("## C-001 r1", history)

    def test_cross_change_replacement_keeps_scope(self):
        p1 = self.proposal()
        adopted1 = self.accept(p1)
        p2 = self.proposal("C-002", supersedes=[{"change": "C-001", "revision": 1, "scope": "value selection only; keep UTF-8"}])
        self.accept(p2)
        state = self.call("status")
        old = next(i for i in state["accepted"] if i["id"] == "C-001")
        self.assertIn("keep UTF-8", old["replaced_by"][0]["scope"])
        self.record(p1, adopted1, "started", ok=False)

    def test_dependencies_are_review_candidates_not_silent_scope(self):
        proposal = self.proposal()
        self.assertEqual(proposal["review_candidates"], ["M-UI"])
        adopted = self.accept(proposal)
        self.assertEqual(adopted["status"]["current"][0]["affected"], [])

    def test_writer_lock_and_regenerated_index(self):
        p = self.proposal()
        lock = self.project / ".handoff/newbie-dev-buddy/write.lock"
        lock.write_text('{"pid": 999999, "synthetic": true}')
        self.call("refresh", ok=False)
        lock.unlink()
        index = self.project / ".handoff/newbie-dev-buddy/CURRENT.md"
        index.write_text("incomplete index\n")
        self.call("refresh")
        self.assertIn("C-001", index.read_text())
        self.assertTrue((self.project / p["path"]).is_file())

    def test_path_escape_and_symlinks_are_refused(self):
        self.call("propose", "--spec-json", self.json_file("bad.json", {
            "id": "../../escape", "primary": "M-DATA"}), ok=False)
        (self.project / "src/value.txt").unlink()
        outside = self.base / "outside.txt"
        outside.write_text("private synthetic marker\n")
        (self.project / "src/value.txt").symlink_to(outside)
        self.call("status", ok=False)
        self.assertEqual(outside.read_text(), "private synthetic marker\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
