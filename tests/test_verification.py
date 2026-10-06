"""Module verification coverage tests using synthetic projects and receipts."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("verification", Path(__file__).resolve().parents[1] /
                                            "scripts/verification.py")
verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verification)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="module-verification-test-")
        self.root = Path(self.temp.name)
        for directory in ("src", "tests", "checks"):
            (self.root / directory).mkdir()
        for name in ("src/data.py", "src/export.py", "tests/data.py", "requirements.md"):
            (self.root / name).write_text("Synthetic verification input.\n")
        self.config = {"schema": 1, "name": "Synthetic module check", "exclude": [".handoff"],
                       "steps": [{"id": "data", "command": ["python", "tests/data.py"], "format": "checks"}]}
        self.save_config()
        self.mapping = {"context": ["requirements.md"], "modules": [
            {"id": "M-DATA", "paths": ["src/data.py"], "verification": {
                "policy": "on-change", "config": "checks/data.json", "steps": ["data"],
                "inputs": ["tests/data.py"]}},
            {"id": "M-EXPORT", "paths": ["src/export.py"]}]}
        self.check = verification.build_plan(self.mapping, ["M-DATA"])["checks"][0]

    def tearDown(self):
        self.temp.cleanup()

    def save_config(self):
        (self.root / "checks/data.json").write_text(json.dumps(self.config))

    def report(self):
        return {"status": "passed", "configFile": "checks/data.json", "config": copy.deepcopy(self.config),
                "steps": [{"id": "data", "status": "passed", "exitCode": 0, "signal": None,
                           "proof": {"checks": 1, "names": ["Synthetic behavior assertion"]}}],
                "inputs": verification.input_files(self.root, ["checks/data.json", "tests/data.py",
                                                                "src/data.py", "requirements.md"])}

    def test_old_maps_remain_manual_and_unconfigured(self):
        self.mapping["modules"][0].pop("verification")
        plan = verification.build_plan(self.mapping, ["M-DATA", "M-EXPORT"])
        self.assertEqual(plan["checks"], [])
        self.assertEqual(plan["missing"], ["M-DATA", "M-EXPORT"])
        self.assertTrue(all(item["policy"] == "manual" for item in plan["modules"]))

    def test_default_policy_can_be_overridden_and_manual_check_is_available(self):
        self.mapping["verification_defaults"] = {"policy": "required"}
        self.mapping["modules"][0]["verification"]["policy"] = "manual"
        plan = verification.build_plan(self.mapping, ["M-DATA", "M-EXPORT"])
        self.assertEqual([item["policy"] for item in plan["modules"]], ["manual", "required"])
        self.assertEqual(plan["checks"][0]["policy"], "manual")
        self.assertEqual(plan["missing"], ["M-EXPORT"])

    def test_profiles_require_the_whole_configuration_group(self):
        for invalid in ({"policy": "automatic"}, {"policy": []}, {"config": "checks/data.json"},
                        {"config": "checks/data.json", "steps": [], "inputs": ["tests/data.py"]},
                        {"config": "checks/data.json", "steps": ["data"], "inputs": []}):
            with self.subTest(invalid=invalid):
                mapping = copy.deepcopy(self.mapping)
                mapping["modules"][0]["verification"] = invalid
                with self.assertRaises(ValueError):
                    verification.validate_settings(mapping)

    def test_integration_is_selected_when_any_member_is_in_scope(self):
        self.mapping["integration_checks"] = [{"id": "data-export", "modules": ["M-DATA", "M-EXPORT"],
                                               "policy": "required", "config": "checks/data.json",
                                               "steps": ["data"], "inputs": ["tests/data.py"]}]
        plan = verification.build_plan(self.mapping, ["M-EXPORT"])
        integration = plan["checks"][0]
        self.assertEqual(integration["id"], "integration:data-export")
        self.assertEqual(integration["source_paths"], ["requirements.md", "src/data.py", "src/export.py"])
        report = self.report()
        self.assertTrue(verification.check_coverage(report, integration, self.root))
        report["inputs"].update(verification.input_files(self.root, ["src/export.py"]))
        self.assertEqual(verification.check_coverage(report, integration, self.root), [])

    def test_unknown_integration_module_or_scope_fails(self):
        with self.assertRaises(ValueError):
            verification.build_plan(self.mapping, ["M-UNKNOWN"])
        self.mapping["integration_checks"] = [{"id": "unknown", "modules": ["M-DATA", "M-UNKNOWN"],
                                               "policy": "required", "config": "checks/data.json",
                                               "steps": ["data"], "inputs": ["tests/data.py"]}]
        with self.assertRaises(ValueError):
            verification.validate_settings(self.mapping)

    def test_complete_matching_profile_passes_and_is_validated(self):
        verification.validate_profiles(self.mapping, self.root)
        self.assertEqual(verification.check_coverage(self.report(), self.check, self.root), [])

    def test_whole_project_pass_cannot_cover_wrong_profile(self):
        report = self.report()
        report["configFile"] = "checks/other.json"
        self.assertIn("different module configuration", " ".join(
            verification.check_coverage(report, self.check, self.root)))

    def test_build_exit_step_cannot_replace_behavior_step(self):
        self.config["steps"][0]["format"] = "exit"
        self.save_config()
        self.assertIn("behavior step", " ".join(verification.check_coverage(self.report(), self.check, self.root)))

    def test_empty_proof_failed_or_missing_required_step_fails(self):
        for mutation in ("empty", "failed", "missing"):
            with self.subTest(mutation=mutation):
                report = self.report()
                if mutation == "empty":
                    report["steps"][0]["proof"] = {"checks": 0}
                elif mutation == "failed":
                    report["steps"][0]["status"] = "failed"
                else:
                    report["steps"] = []
                self.assertTrue(verification.check_coverage(report, self.check, self.root))

    def test_missing_source_or_test_or_context_is_not_covered(self):
        for file in ("src/data.py", "tests/data.py", "requirements.md", "checks/data.json"):
            with self.subTest(file=file):
                report = self.report()
                report["inputs"].pop(file)
                self.assertIn(file, " ".join(verification.check_coverage(report, self.check, self.root)))

    def test_configuration_or_source_drift_fails(self):
        report = self.report()
        self.config["name"] = "Changed synthetic profile"
        self.save_config()
        self.assertIn("configuration changed", " ".join(verification.check_coverage(report, self.check, self.root)))
        report = self.report()
        (self.root / "src/data.py").write_text("Changed synthetic source.\n")
        self.assertIn("src/data.py", " ".join(verification.check_coverage(report, self.check, self.root)))

    def test_accepted_configuration_digest_and_snapshot_reject_command_drift(self):
        for field in ("config_digest", "config_snapshot"):
            self.config["steps"][0]["command"] = ["python", "tests/data.py"]
            self.save_config()
            check = copy.deepcopy(self.check)
            check[field] = (verification.input_files(self.root, ["checks/data.json"])["checks/data.json"]
                            if field == "config_digest" else copy.deepcopy(self.config))
            verification.config_for_check(check, self.root)
            self.config["steps"][0]["command"] = ["python", "tests/replacement.py"]
            self.save_config()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "accepted Kit configuration"):
                verification.config_for_check(check, self.root)

    def test_directory_inputs_cover_every_source_file(self):
        check = copy.deepcopy(self.check)
        check["source_paths"] = ["src"]
        report = self.report()
        self.assertIn("src/export.py", " ".join(verification.check_coverage(report, check, self.root)))

    def test_generated_records_must_be_excluded_by_config(self):
        self.config["exclude"] = []
        self.save_config()
        self.assertIn("must exclude", " ".join(verification.check_coverage(self.report(), self.check, self.root)))

    def test_excluded_or_shared_dependencies_cannot_hide_required_inputs(self):
        for field in ("exclude", "dependencyDirs"):
            self.config[field] = [".handoff", "src"] if field == "exclude" else ["src"]
            self.save_config()
            report = self.report()
            self.assertIn("excluded", " ".join(verification.check_coverage(report, self.check, self.root)))
            with self.assertRaises(ValueError):
                verification.validate_profiles(self.mapping, self.root)

    def test_path_escape_symlink_hardlink_and_fifo_fail_without_reading(self):
        for path in ("../outside", "/absolute", "a/../escape", "C:/outside", "src\\data.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                verification.safe(self.root, path)
        (self.root / "src/link.py").symlink_to(self.root / "src/data.py")
        os.link(self.root / "src/data.py", self.root / "src/hard.py")
        os.mkfifo(self.root / "src/pipe")
        for path in ("src/link.py", "src/hard.py", "src/pipe"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                verification.input_files(self.root, [path])

    def test_malformed_report_is_an_issue_and_never_a_traceback(self):
        for report in ([], None, {"status": "passed", "steps": [], "inputs": []}):
            self.assertTrue(verification.check_coverage(report, self.check, self.root))


if __name__ == "__main__":
    unittest.main()
