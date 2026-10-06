"""Check the public demo's actual behavior and refusal to overwrite user files."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "examples/bookmark-demo/replay.py"


@unittest.skipUnless(os.name == "posix", "The full workflow requires macOS/Linux or WSL")
class BookmarkDemoTests(unittest.TestCase):
    def test_replay_preserves_revision_and_produces_filtered_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "demo"
            subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)],
                           check=True, capture_output=True, text=True)
            evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
            rows = list(csv.DictReader(io.StringIO(evidence["selected_csv"])))
            self.assertEqual([row["url"] for row in rows],
                             ["https://example.org/python", "https://example.org/web"])
            self.assertEqual(evidence["resumed_status"]["current"][0]["revision"], 2)
            self.assertEqual(evidence["kit_verification"], "not_run")
            project = output / "bookmark-project"
            self.assertTrue((project / ".handoff/newbie-dev-buddy/drafts/C-EXPORT-r1.md").is_file())
            self.assertTrue((project / ".handoff/newbie-dev-buddy/decisions/C-EXPORT-r1.md").is_file())
            self.assertEqual(json.loads((project / "data/bookmarks.json").read_text(encoding="utf-8"))[1]["tag"], "work")

    def test_existing_output_is_refused_without_changing_its_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            marker = output / "keep.txt"
            marker.write_text("do not overwrite", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)],
                                       capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "do not overwrite")
            self.assertEqual(list(output.iterdir()), [marker])
