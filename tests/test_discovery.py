"""Read-only discovery tests using synthetic projects and sensitive markers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("discovery", Path(__file__).resolve().parents[1] / "scripts/discovery.py")
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="module-discovery-test-")
        self.base = Path(self.temp.name)
        self.root = self.base / "synthetic-project"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def paths(self, result):
        return {item["path"] for item in result["files"]}

    def omissions(self, result):
        return {item["path"]: item["reason"] for item in result["excluded"]}

    def test_python_syntax_facts_keep_relative_imports_and_nested_scopes(self):
        self.write("src/service.py", "import os as system\nfrom .helpers import run\nfrom .. import shared\n"
                   "class Store:\n    async def read(self):\n        import json\n        return shared\n")
        result = discovery.collect(self.root)
        item = result["files"][0]
        self.assertEqual(item["language"], "python")
        self.assertEqual(item["category"], "source")
        self.assertEqual([(symbol["name"], symbol["kind"]) for symbol in item["symbols"]],
                         [("Store", "class"), ("Store.read", "async_function")])
        self.assertEqual([(value["module"], value["level"], value["scope"]) for value in item["imports"]],
                         [("os", 0, ""), ("helpers", 1, ""), ("", 2, ""), ("json", 0, "Store.read")])

    def test_never_executes_project_code_or_emits_configuration_values(self):
        marker = self.base / "execution-marker"
        self.write("danger.py", "from pathlib import Path\nPath(" + repr(str(marker)) +
                   ").write_text('executed')\nSECRET = 'SYNTHETIC_PRIVATE_VALUE'\n")
        self.write("config.json", '{"token": "SYNTHETIC_PRIVATE_VALUE"}\n')
        result = discovery.collect(self.root)
        serialized = json.dumps(result)
        self.assertFalse(marker.exists())
        self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(str(marker), serialized)

    def test_fingerprint_changes_on_edit_add_and_delete(self):
        file = self.write("src/value.txt", "old\n")
        baseline = discovery.collect(self.root)["summary"]["inventory_sha256"]
        file.write_text("new\n")
        self.assertNotEqual(baseline, discovery.collect(self.root)["summary"]["inventory_sha256"])
        file.write_text("old\n")
        added = self.write("src/added.txt", "added\n")
        self.assertNotEqual(baseline, discovery.collect(self.root)["summary"]["inventory_sha256"])
        added.unlink()
        self.assertEqual(baseline, discovery.collect(self.root)["summary"]["inventory_sha256"])
        file.unlink()
        self.assertNotEqual(baseline, discovery.collect(self.root)["summary"]["inventory_sha256"])

    def test_output_and_hashes_are_stable_and_relative(self):
        self.write("src/中文 file.txt", "Synthetic content.\n")
        self.write("README.md", "# Synthetic\n")
        first = discovery.collect(self.root)
        second = discovery.collect(self.root)
        self.assertEqual(first, second)
        self.assertEqual(first["files"][1]["sha256"], hashlib.sha256(b"Synthetic content.\n").hexdigest())
        self.assertTrue(all(not Path(item["path"]).is_absolute() for item in first["files"] + first["excluded"]))

    def test_default_sensitive_and_generated_directories_are_not_traversed(self):
        excluded = [".git/object.txt", ".handoff/proposal.md", ".acceptance/report.json", "node_modules/dependency.js",
                    ".venv/python.py", "venv/python.py", "dist/result.js", "build/result.js",
                    "__pycache__/cache.py", ".ssh/key", ".aws/credentials", ".credentials/token",
                    "docs/module-change/MODULES.md", ".env", ".env.local", "private.KEY", "server.crt", "id_ed25519"]
        for relative in excluded:
            self.write(relative, "SYNTHETIC_EXCLUDED_CONTENT\n")
        self.write("docs/user-guide.md", "Synthetic docs\n")
        result = discovery.collect(self.root)
        self.assertEqual(self.paths(result), {"docs/user-guide.md"})
        self.assertGreater(len(result["excluded"]), 10)
        self.assertFalse(any("sha256" in item for item in result["excluded"]))
        self.assertIn(".aws", self.omissions(result))
        self.assertNotIn(".aws/credentials", self.omissions(result))
        self.assertNotIn("SYNTHETIC_EXCLUDED_CONTENT", json.dumps(result))

    def test_user_exclusions_support_directory_paths_and_globs(self):
        self.write("private/note.md", "Private synthetic note\n")
        self.write("src/ignored.test.js", "export const ignored = 1;\n")
        self.write("src/kept.js", "export const kept = 1;\n")
        result = discovery.collect(self.root, excludes=("private", "**/*.test.js"))
        self.assertEqual(self.paths(result), {"src/kept.js"})
        self.assertEqual(self.omissions(result), {"private": "user_exclusion", "src/ignored.test.js": "user_exclusion"})

    def test_symlink_files_directories_and_loops_are_skipped(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "private.py").write_text("SECRET = 'SYNTHETIC_OUTSIDE_CONTENT'\n")
        (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
        (self.root / "linked-file.py").symlink_to(outside / "private.py")
        (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        result = discovery.collect(self.root)
        self.assertEqual(result["files"], [])
        self.assertEqual(set(self.omissions(result).values()), {"symlink"})
        self.assertNotIn("SYNTHETIC_OUTSIDE_CONTENT", json.dumps(result))

    def test_hardlinks_and_fifo_are_skipped_without_reading(self):
        outside = self.base / "outside-value.txt"
        outside.write_text("SYNTHETIC_OUTSIDE_CONTENT\n")
        os.link(outside, self.root / "hardlink.txt")
        os.mkfifo(self.root / "pipe")
        result = discovery.collect(self.root)
        self.assertEqual(result["files"], [])
        self.assertEqual(self.omissions(result), {"hardlink.txt": "hard_link", "pipe": "special_file"})
        self.assertNotIn(hashlib.sha256(outside.read_bytes()).hexdigest(), json.dumps(result))

    def test_directory_replaced_with_symlink_does_not_escape_root(self):
        self.write("race/local.txt", "Synthetic local content\n")
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "outside.txt"
        secret.write_text("SYNTHETIC_OUTSIDE_CONTENT\n")
        original_open = os.open

        def racing_open(path, flags, *args, **kwargs):
            if path == "race" and "dir_fd" in kwargs:
                (self.root / "race").rename(self.base / "saved-directory")
                (self.root / "race").symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(discovery.os, "open", side_effect=racing_open):
            # Keep capability detection tied to the original supported function.
            with patch.object(discovery.os, "supports_dir_fd", os.supports_dir_fd | {discovery.os.open}):
                result = discovery.collect(self.root)
        self.assertEqual(result["files"], [])
        self.assertEqual(self.omissions(result), {"race": "io_error"})
        self.assertNotIn(hashlib.sha256(secret.read_bytes()).hexdigest(), json.dumps(result))

    def test_regular_file_replaced_with_fifo_is_opened_nonblocking_and_rejected(self):
        file = self.write("race.txt", "Synthetic input\n")
        original_open = os.open

        def racing_open(path, flags, *args, **kwargs):
            if path == "race.txt" and "dir_fd" in kwargs:
                self.assertTrue(flags & os.O_NONBLOCK)
                file.unlink()
                os.mkfifo(file)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(discovery.os, "open", side_effect=racing_open):
            with patch.object(discovery.os, "supports_dir_fd", os.supports_dir_fd | {discovery.os.open}):
                result = discovery.collect(self.root)
        self.assertEqual(result["files"], [])
        self.assertEqual(self.omissions(result), {"race.txt": "special_file"})

    def test_binary_non_utf8_and_large_files_report_coverage_gaps(self):
        (self.root / "binary.dat").write_bytes(b"synthetic\x00binary")
        (self.root / "legacy.txt").write_bytes(b"\xff\xfe")
        self.write("big.txt", "x" * 17)
        self.write("small.txt", "x" * 16)
        result = discovery.collect(self.root, max_bytes=16)
        self.assertEqual(self.paths(result), {"small.txt"})
        self.assertEqual(self.omissions(result), {"big.txt": "too_large", "binary.dat": "binary_or_non_utf8",
                                                 "legacy.txt": "binary_or_non_utf8"})
        self.assertEqual(result["summary"]["coverage"], "included_text_files_only")

    def test_invalid_python_stays_fingerprinted_without_fabricated_dependencies(self):
        self.write("broken.py", "def broken(:\n")
        result = discovery.collect(self.root)
        self.assertEqual(self.paths(result), {"broken.py"})
        self.assertNotIn("imports", result["files"][0])
        self.assertTrue(any("AST unavailable" in value for value in result["warnings"]))

    def test_non_python_is_inventory_only(self):
        self.write("src/service.ts", 'import other from "./other";\n')
        self.write("tests/test_service.py", "def test_service():\n    pass\n")
        result = discovery.collect(self.root)
        typescript = next(item for item in result["files"] if item["language"] == "typescript")
        self.assertNotIn("imports", typescript)
        self.assertNotIn("symbols", typescript)
        self.assertEqual(result["files"][1]["category"], "test")
        self.assertTrue(any("Non-Python" in value for value in result["warnings"]))

    def test_excluded_content_changes_are_not_claimed_as_covered(self):
        hidden = self.write(".env", "SYNTHETIC_SECRET_A\n")
        first = discovery.collect(self.root)
        hidden.write_text("SYNTHETIC_SECRET_B\n")
        second = discovery.collect(self.root)
        self.assertEqual(first["summary"]["inventory_sha256"], second["summary"]["inventory_sha256"])
        self.assertTrue(any("outside content coverage" in value for value in first["warnings"]))

    def test_depth_and_entry_limits_are_reported_as_exclusions(self):
        self.write("deep/further/file.txt", "Synthetic\n")
        with patch.object(discovery, "MAX_DEPTH", 1):
            result = discovery.collect(self.root)
        self.assertEqual(self.omissions(result), {"deep/further": "depth_limit"})
        with patch.object(discovery, "MAX_ENTRIES", 0):
            result = discovery.collect(self.root)
        self.assertEqual(self.omissions(result), {".": "entry_limit"})

    def test_invalid_options_and_root_fail_without_machine_paths(self):
        for patterns in [("../outside",), (str(self.base),), ("bad\\path",), "private"]:
            with self.assertRaises(ValueError):
                discovery.collect(self.root, excludes=patterns)
        for limit in [0, -1, True, "large"]:
            with self.assertRaises(ValueError):
                discovery.collect(self.root, max_bytes=limit)
        alias = self.base / "root-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            discovery.collect(alias)
        with self.assertRaises(ValueError) as caught:
            discovery.collect(self.base / "missing")
        self.assertNotIn(str(self.base), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
