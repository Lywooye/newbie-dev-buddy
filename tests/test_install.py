"""Installer behavior and security regressions using only synthetic host homes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("buddy_installer_tests", SCRIPTS / "install.py")
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class InstallTests(unittest.TestCase):
    def setUp(self):
        windows = mock.patch.object(INSTALL, "NATIVE_WINDOWS", False)
        windows.start()
        self.addCleanup(windows.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="newbie-dev-buddy-installer-")
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.source = self.root / "public-source"
        self.source.mkdir()
        for name, text in {"SKILL.md": "Synthetic Skill\n", "LICENSE": "Synthetic license\n",
                           "references/setup.md": "Synthetic setup\n"}.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.source / "PUBLIC_FILES.txt").write_text(
            "SKILL.md\nLICENSE\nreferences/setup.md\n", encoding="utf-8")
        self.package = INSTALL.public_package(self.source)
        self.graph = {"command": "/synthetic/codegraph", "args": ["serve", "--mcp"],
                      "env": {"DO_NOT_TRACK": "1"}, "version": "1.6.2", "origin": "existing"}

    def tearDown(self):
        self.temp.cleanup()

    def json_file(self, name, value):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def call_main(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with mock.patch.object(INSTALL, "SOURCE", self.source), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = INSTALL.main(["--home", str(self.home), *arguments])
        return code, json.loads(output.getvalue() or error.getvalue()), output.getvalue() + error.getvalue()

    def configure(self, host, config, dry_run=False):
        return INSTALL.configure(host, config, self.graph, self.home / "setup", dry_run=dry_run)

    def test_only_manifest_files_are_copied(self):
        (self.source / ".env").write_text("SYNTHETIC_PRIVATE_EXTRA", encoding="utf-8")
        (self.source / ".git").mkdir()
        (self.source / ".git/private").write_text("SYNTHETIC_PRIVATE_EXTRA", encoding="utf-8")
        destination = self.home / "skills/buddy"
        self.assertEqual(INSTALL.copy_skill(self.source, destination, self.package), "installed")
        self.assertEqual({str(x.relative_to(destination)) for x in destination.rglob("*") if x.is_file()},
                         set(self.package))

    def test_unsafe_and_duplicate_manifest_entries_are_refused(self):
        for entry in ("../outside", "/absolute", ".git/private", "nested\\file", "./SKILL.md", "SKILL.md"):
            with self.subTest(entry=entry):
                (self.source / "PUBLIC_FILES.txt").write_text("SKILL.md\nLICENSE\n" + entry + "\n", encoding="utf-8")
                with self.assertRaises(INSTALL.InstallError):
                    INSTALL.public_package(self.source)

    def test_manifest_source_link_is_refused(self):
        original = self.source / "SKILL.md"
        target = self.root / "private"
        target.write_text("SYNTHETIC_PRIVATE_EXTRA", encoding="utf-8")
        original.unlink()
        original.symlink_to(target)
        with self.assertRaises(INSTALL.InstallError):
            INSTALL.public_package(self.source)

    def test_existing_skill_with_different_content_is_preserved(self):
        destination = self.home / "skills/buddy"
        destination.mkdir(parents=True)
        private = destination / "SKILL.md"
        private.write_text("Synthetic existing content", encoding="utf-8")
        with self.assertRaises(INSTALL.InstallError):
            INSTALL.copy_skill(self.source, destination, self.package)
        self.assertEqual(private.read_text(), "Synthetic existing content")
        self.assertFalse((destination / "LICENSE").exists())

    def test_matching_skill_is_idempotent_and_preserves_extra_local_file(self):
        destination = self.home / "skills/buddy"
        INSTALL.copy_skill(self.source, destination, self.package)
        (destination / "local-note").write_text("Synthetic local note", encoding="utf-8")
        self.assertEqual(INSTALL.copy_skill(self.source, destination, self.package), "unchanged")
        self.assertTrue((destination / "local-note").exists())

    def test_symlink_destination_or_ancestor_is_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        linked = self.home / "linked"
        linked.symlink_to(outside, target_is_directory=True)
        for destination in (linked, linked / "skills/buddy"):
            with self.assertRaises(INSTALL.InstallError):
                INSTALL.copy_skill(self.source, destination, self.package)
        self.assertEqual(list(outside.iterdir()), [])

    def test_hardlinked_existing_config_is_refused(self):
        config = self.json_file("cursor.json", {"mcpServers": {}})
        os.link(config, self.root / "external-config")
        with self.assertRaises(INSTALL.InstallError):
            self.configure("cursor", config)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Named pipes are unavailable")
    def test_fifo_config_is_refused_without_reading(self):
        config = self.home / "pipe.json"
        os.mkfifo(config)
        with self.assertRaises(INSTALL.InstallError):
            self.configure("cursor", config)

    def test_config_merge_preserves_other_servers_and_settings_without_secret_output(self):
        original = {"theme": "synthetic", "mcpServers": {
            "private-tool": {"command": "synthetic-tool", "env": {"TOKEN": "SYNTHETIC_SECRET_MARKER"}}}}
        config = self.json_file(".cursor/mcp.json", original)
        result = self.configure("cursor", config)
        updated = json.loads(config.read_text())
        self.assertEqual(result["status"], "configured")
        self.assertEqual(updated["theme"], original["theme"])
        self.assertEqual(updated["mcpServers"]["private-tool"], original["mcpServers"]["private-tool"])
        self.assertNotIn("SYNTHETIC_SECRET_MARKER", json.dumps(result))
        self.assertEqual(updated["mcpServers"]["codegraph"]["env"], {"DO_NOT_TRACK": "1"})
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)

    def test_existing_windows_config_is_preserved_without_a_secret_backup(self):
        config = self.json_file("windows-host.json", {"mcpServers": {"synthetic": {
            "env": {"KEY": "SYNTHETIC_SECRET_MARKER"}}}})
        original = config.read_bytes()
        with mock.patch.object(INSTALL, "NATIVE_WINDOWS", True):
            result = self.configure("cursor", config)
        self.assertEqual(result["status"], "manual_required")
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((self.home / "setup/backups").exists())
        candidate = Path(result["candidate"])
        self.assertNotIn("SYNTHETIC_SECRET_MARKER", candidate.read_text() + json.dumps(result))
        self.assertIn("Windows", result["reason"])

    def test_new_windows_config_can_be_created_without_copying_credentials(self):
        config = self.home / "new-windows-host.json"
        with mock.patch.object(INSTALL, "NATIVE_WINDOWS", True):
            result = self.configure("cursor", config)
        self.assertEqual(result["status"], "configured")
        self.assertEqual(json.loads(config.read_text()), INSTALL.server_config("cursor", self.graph))
        self.assertFalse((self.home / "setup/backups").exists())

    def test_existing_codegraph_server_is_preserved_and_candidate_is_separate(self):
        original = {"mcpServers": {"codegraph": {"command": "existing-graph", "env": {"KEY": "SYNTHETIC_SECRET_MARKER"}}}}
        config = self.json_file("existing.json", original)
        before = config.read_bytes()
        result = self.configure("cursor", config)
        self.assertEqual(result["status"], "manual_required")
        self.assertEqual(config.read_bytes(), before)
        candidate = Path(result["candidate"])
        self.assertTrue(candidate.is_file())
        self.assertNotIn("SYNTHETIC_SECRET_MARKER", candidate.read_text() + json.dumps(result))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(candidate.stat().st_mode), 0o600)

    def test_matching_server_is_unchanged_without_backup_or_candidate(self):
        config = self.json_file("matching.json", INSTALL.server_config("cursor", self.graph))
        before = {p.relative_to(self.home) for p in self.home.rglob("*")}
        result = self.configure("cursor", config)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual({p.relative_to(self.home) for p in self.home.rglob("*")}, before)

    def test_opencode_preserves_local_remote_servers_and_uses_command_array(self):
        original = {"model": "synthetic/model", "mcp": {
            "remote-tool": {"type": "remote", "url": "https://example.invalid/mcp", "headers": {"Authorization": "SYNTHETIC_SECRET_MARKER"}}}}
        config = self.json_file("opencode.json", original)
        result = self.configure("opencode", config)
        updated = json.loads(config.read_text())
        self.assertEqual(result["status"], "configured")
        self.assertEqual(updated["mcp"]["remote-tool"], original["mcp"]["remote-tool"])
        self.assertEqual(updated["mcp"]["codegraph"]["command"], ["/synthetic/codegraph", "serve", "--mcp"])
        self.assertNotIn("mcpServers", updated)

    def test_zcode_uses_nested_servers_and_preserves_mcp_options(self):
        original = {"provider": "synthetic", "mcp": {"timeout": 123, "servers": {
            "other": {"command": "synthetic", "args": []}}}}
        config = self.json_file("zcode.json", original)
        self.assertEqual(self.configure("zcode", config)["status"], "configured")
        updated = json.loads(config.read_text())
        self.assertEqual(updated["mcp"]["timeout"], 123)
        self.assertEqual(updated["mcp"]["servers"]["other"], original["mcp"]["servers"]["other"])
        self.assertIn("codegraph", updated["mcp"]["servers"])
        self.assertNotIn("mcpServers", updated)

    def test_invalid_json_jsonc_and_duplicate_keys_are_never_rewritten(self):
        for text in ('{ // Synthetic comment\n "mcpServers": {} }',
                     '{"mcpServers": {}, "mcpServers": {}}', '{"token":"SYNTHETIC_SECRET_MARKER",'):
            with self.subTest(text=text):
                config = self.home / "manual.json"
                config.write_text(text, encoding="utf-8")
                result = self.configure("opencode", config)
                self.assertEqual(result["status"], "manual_required")
                self.assertEqual(config.read_text(), text)
                self.assertNotIn("SYNTHETIC_SECRET_MARKER", json.dumps(result))

    def test_wrong_server_container_type_uses_candidate(self):
        config = self.json_file("container.json", {"mcpServers": []})
        before = config.read_bytes()
        self.assertEqual(self.configure("cursor", config)["status"], "manual_required")
        self.assertEqual(config.read_bytes(), before)

    def test_codex_toml_and_dsh_profile_are_not_mutated(self):
        config = self.home / "config.toml"
        config.write_text('token = "SYNTHETIC_SECRET_MARKER"\n', encoding="utf-8")
        before = config.read_bytes()
        codex = self.configure("codex", config)
        dsh = self.configure("deepseek-harness", None)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(codex["status"], "manual_required")
        self.assertIn("[mcp_servers.codegraph]", Path(codex["candidate"]).read_text())
        patch = json.loads(Path(dsh["candidate"]).read_text())
        self.assertEqual(patch[0]["insert"][0]["name"], "@deepseek-ai/dsh-mcp-client")
        self.assertNotIn("SYNTHETIC_SECRET_MARKER", json.dumps([codex, dsh, patch]))

    def test_manual_candidates_for_different_projects_are_preserved_and_repeatable(self):
        projects = [self.root / "first-project", self.root / "second-project"]
        for project in projects:
            project.mkdir()
        first = INSTALL.configure("codex", self.home / "config.toml", self.graph, self.home / "setup",
                                  project=projects[0])
        first_path = Path(first["candidate"])
        original = first_path.read_bytes()
        second = INSTALL.configure("codex", self.home / "config.toml", self.graph, self.home / "setup",
                                   project=projects[1])
        repeated = INSTALL.configure("codex", self.home / "config.toml", self.graph, self.home / "setup",
                                     project=projects[0])
        self.assertNotEqual(first["candidate"], second["candidate"])
        self.assertEqual(first["candidate"], repeated["candidate"])
        self.assertEqual(first_path.read_bytes(), original)
        self.assertEqual(len(list((self.home / "setup/codex").glob("*.toml"))), 2)
        self.assertIn(str(projects[1]), Path(second["candidate"]).read_text())

    def test_user_candidate_and_project_candidate_do_not_conflict(self):
        user = INSTALL.configure("deepseek-harness", None, self.graph, self.home / "setup")
        project = self.root / "overlay-project"
        project.mkdir()
        scoped = INSTALL.configure("deepseek-harness", None, self.graph, self.home / "setup", project=project)
        self.assertNotEqual(user["candidate"], scoped["candidate"])
        self.assertNotIn(str(project), Path(user["candidate"]).read_text())
        self.assertIn(str(project), Path(scoped["candidate"]).read_text())

    def test_codebuddy_existing_fallback_is_selected_without_shadow_file(self):
        fallback = self.json_file(".codebuddy.json", {"mcpServers": {"synthetic": {"command": "synthetic"}}})
        _, chosen = INSTALL.paths_for("codebuddy", self.home, None, "user", {})
        self.assertEqual(chosen, fallback)
        self.configure("codebuddy", chosen)
        self.assertFalse((self.home / ".codebuddy/.mcp.json").exists())
        self.assertFalse((self.home / ".codebuddy/mcp.json").exists())

    def test_opencode_jsonc_is_not_shadowed_by_a_new_json_file(self):
        config = self.home / ".config/opencode/opencode.jsonc"
        config.parent.mkdir(parents=True)
        config.write_text('{ // Synthetic comment\n "mcp": {} }', encoding="utf-8")
        _, chosen = INSTALL.paths_for("opencode", self.home, None, "user", {})
        self.assertEqual(chosen, config)
        self.assertEqual(self.configure("opencode", chosen)["status"], "manual_required")
        self.assertFalse((config.parent / "opencode.json").exists())

    def test_plain_json_in_jsonc_file_still_requires_manual_candidate(self):
        config = self.home / "opencode.jsonc"
        config.write_text('{"mcp": {}}\n', encoding="utf-8")
        original = config.read_bytes()
        result = self.configure("opencode", config)
        self.assertEqual(result["status"], "manual_required")
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((self.home / "setup/backups").exists())
        self.assertTrue(Path(result["candidate"]).is_file())

    def test_configure_dry_run_does_not_write_original_backup_or_candidate(self):
        config = self.json_file("cursor.json", {"mcpServers": {}})
        before = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(self.configure("cursor", config, dry_run=True)["status"], "would_configure")
        self.assertEqual(self.configure("codex", config, dry_run=True)["status"], "manual_required")
        after = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_project_secret_backup_is_private_and_outside_the_project(self):
        project = self.root / "synthetic-project"
        project.mkdir()
        config = project / ".cursor/mcp.json"
        config.parent.mkdir()
        config.write_text('{"mcpServers":{"other":{"env":{"KEY":"SYNTHETIC_SECRET_MARKER"}}}}', encoding="utf-8")
        original = config.read_bytes()
        with mock.patch.object(INSTALL.codegraph_setup, "discover", return_value=self.graph):
            code, report, output = self.call_main("--agent", "cursor", "--mode", "enhanced",
                                                  "--scope", "project", "--project", str(project))
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["mcp"]["status"], "configured")
        backups = list((self.home / ".newbie-dev-buddy/setup/backups").glob("*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertFalse(list(project.rglob("*.bak")))
        self.assertNotIn("SYNTHETIC_SECRET_MARKER", output)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(backups[0].parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)

    def test_enhanced_home_inside_project_is_rejected_before_installation(self):
        project = self.root / "synthetic-project"
        project.mkdir()
        nested_home = project / "home"
        nested_home.mkdir()
        with mock.patch.object(INSTALL.codegraph_setup, "discover", side_effect=AssertionError("unexpected execution")):
            code, report, _ = self.call_main("--home", str(nested_home), "--agent", "cursor", "--mode", "enhanced",
                                             "--scope", "project", "--project", str(project))
        self.assertEqual(code, 1)
        self.assertFalse(report["ok"])
        self.assertFalse((project / ".cursor").exists())
        self.assertFalse((nested_home / ".newbie-dev-buddy").exists())

    def test_explicit_host_roots_are_used_without_creating_default_roots(self):
        codex_root = self.root / "portable-codex"
        skill, config = INSTALL.paths_for("codex", self.home, None, "user", {"CODEX_HOME": str(codex_root)})
        self.assertEqual(skill, codex_root / "skills/newbie-dev-buddy")
        self.assertEqual(config, codex_root / "config.toml")
        open_root = self.root / "portable-opencode"
        override = self.root / "selected-open-config.json"
        skill, config = INSTALL.paths_for("opencode", self.home, None, "user",
                                          {"OPENCODE_CONFIG_DIR": str(open_root), "OPENCODE_CONFIG": str(override)})
        self.assertEqual(skill, open_root / "skills/newbie-dev-buddy")
        self.assertEqual(config, override)
        self.assertFalse((self.home / ".config").exists())
        self.assertFalse((self.home / ".codex").exists())

    def test_relative_environment_roots_are_rejected_instead_of_writing_cwd(self):
        for host, variable in (("codex", "CODEX_HOME"), ("opencode", "OPENCODE_CONFIG_DIR"),
                               ("opencode", "OPENCODE_CONFIG"), ("windsurf", "XDG_CONFIG_HOME")):
            with self.subTest(host=host, variable=variable):
                with self.assertRaises(INSTALL.InstallError):
                    INSTALL.paths_for(host, self.home, None, "user", {variable: "relative-synthetic-root"})

    def test_isolated_home_does_not_follow_real_environment_override(self):
        injected = self.root / "other-host-root"
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(injected)}):
            code, report, _ = self.call_main("--agent", "codex")
        self.assertEqual(code, 0)
        self.assertEqual(Path(report["results"][0]["skill_path"]), self.home / ".codex/skills/newbie-dev-buddy")
        self.assertFalse(injected.exists())

    def test_selected_fallback_config_symlink_is_refused(self):
        outside = self.root / "outside-config.json"
        outside.write_text('{"token":"SYNTHETIC_SECRET_MARKER"}', encoding="utf-8")
        (self.home / ".codebuddy.json").symlink_to(outside)
        with self.assertRaises(INSTALL.InstallError):
            INSTALL.paths_for("codebuddy", self.home, None, "user", {})

    def test_basic_install_is_repeatable_and_has_no_graph_execution(self):
        with mock.patch.object(INSTALL.codegraph_setup, "discover", side_effect=AssertionError("unexpected dependency execution")), \
                mock.patch.object(INSTALL.codegraph_setup, "install", side_effect=AssertionError("unexpected dependency download")):
            first, report, _ = self.call_main("--agent", "cursor")
            second, repeat, _ = self.call_main("--agent", "cursor")
        self.assertEqual((first, second), (0, 0))
        self.assertEqual(report["results"][0]["skill"], "installed")
        self.assertEqual(repeat["results"][0]["skill"], "unchanged")
        self.assertFalse(report["project_indexed"])
        self.assertFalse(report["host_session_tested"])

    def test_main_dry_run_has_no_execution_download_or_filesystem_writes(self):
        before = list(self.home.rglob("*"))
        with mock.patch.object(INSTALL.codegraph_setup, "discover", side_effect=AssertionError("unexpected execution")), \
                mock.patch.object(INSTALL.codegraph_setup, "install", side_effect=AssertionError("unexpected download")):
            code, report, _ = self.call_main("--agent", "cursor", "--mode", "enhanced", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["skill"], "would_install")
        self.assertEqual(list(self.home.rglob("*")), before)

    def test_all_selected_skill_conflicts_are_preflighted_before_any_copy(self):
        conflict = self.home / ".zcode/skills/newbie-dev-buddy"
        conflict.mkdir(parents=True)
        (conflict / "SKILL.md").write_text("Synthetic other Skill", encoding="utf-8")
        code, report, _ = self.call_main("--agent", "cursor", "--agent", "zcode")
        self.assertEqual(code, 1)
        self.assertFalse(report["ok"])
        self.assertFalse((self.home / ".cursor/skills/newbie-dev-buddy").exists())

    def test_enhanced_dependency_failure_reports_the_basic_install_as_partial(self):
        with mock.patch.object(INSTALL.codegraph_setup, "discover", return_value=None), \
                mock.patch.object(INSTALL.codegraph_setup, "install", side_effect=INSTALL.codegraph_setup.SetupError("Synthetic download failure")):
            code, report, _ = self.call_main("--agent", "cursor", "--mode", "enhanced")
        self.assertEqual(code, 1)
        self.assertFalse(report["ok"])
        self.assertEqual(report["results"][0]["skill"], "installed")
        self.assertTrue(Path(report["results"][0]["skill_path"]).is_dir())
        self.assertFalse((self.home / ".cursor/mcp.json").exists())
        self.assertFalse(report["project_indexed"])
        self.assertEqual(report["results"][0]["mcp"]["status"], "not_attempted")

    def test_shared_dependency_failure_leaves_each_host_mcp_not_attempted(self):
        with mock.patch.object(INSTALL.codegraph_setup, "discover", side_effect=INSTALL.codegraph_setup.SetupError("Synthetic compatibility failure")):
            code, report, _ = self.call_main("--agent", "cursor", "--agent", "zcode", "--agent", "codex", "--mode", "enhanced")
        self.assertEqual(code, 1)
        self.assertEqual(len(report["results"]), 3)
        self.assertEqual([item["mcp"]["status"] for item in report["results"]], ["not_attempted"] * 3)
        self.assertTrue(all(item["skill"] == "installed" for item in report["results"]))
        self.assertFalse(list(self.home.rglob("*.bak")))
        self.assertFalse((self.home / ".cursor/mcp.json").exists())
        self.assertFalse((self.home / ".zcode/cli/config.json").exists())

    def test_one_host_configuration_failure_preserves_other_hosts_actual_results(self):
        configure = INSTALL.configure

        def selected_failure(host, *args, **kwargs):
            if host == "opencode":
                raise INSTALL.InstallError("Synthetic selected-host conflict")
            return configure(host, *args, **kwargs)

        with mock.patch.object(INSTALL.codegraph_setup, "discover", return_value=self.graph), \
                mock.patch.object(INSTALL, "configure", side_effect=selected_failure):
            code, report, _ = self.call_main("--agent", "cursor", "--agent", "opencode", "--agent", "codex", "--agent", "zcode", "--mode", "enhanced")
        self.assertEqual(code, 1)
        self.assertFalse(report["ok"])
        self.assertEqual([item["mcp"]["status"] for item in report["results"]],
                         ["configured", "failed", "manual_required", "configured"])
        self.assertTrue((self.home / ".cursor/mcp.json").exists())
        self.assertTrue((self.home / ".zcode/cli/config.json").exists())
        self.assertFalse((self.home / ".config/opencode/opencode.json").exists())
        self.assertTrue(all(item["skill"] == "installed" for item in report["results"]))
        self.assertFalse(report["project_indexed"])

    def test_existing_buddy_codegraph_cache_is_reused_without_redownload(self):
        cache = self.home / ".newbie-dev-buddy/tools/codegraph" / INSTALL.codegraph_setup.VERSION
        cache.mkdir(parents=True)
        node = cache / ("node.exe" if os.name == "nt" else "node")
        node.write_text("Synthetic bundled executable", encoding="utf-8")
        with mock.patch.object(INSTALL.codegraph_setup, "discover", side_effect=[None, self.graph]) as discover, \
                mock.patch.object(INSTALL.codegraph_setup, "install", side_effect=AssertionError("unexpected redownload")):
            code, report, _ = self.call_main("--agent", "cursor", "--mode", "enhanced")
        self.assertEqual(code, 0)
        self.assertEqual(discover.call_args_list, [mock.call(None), mock.call(str(node))])
        self.assertEqual(report["results"][0]["mcp"]["status"], "configured")


if __name__ == "__main__":
    unittest.main()
