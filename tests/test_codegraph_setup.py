"""Dependency installation tests use synthetic bundles and isolated directories."""
import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile


MODULE = Path(__file__).resolve().parents[1] / "scripts/codegraph_setup.py"
SPEC = importlib.util.spec_from_file_location("codegraph_setup", MODULE)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class CodeGraphSetup(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="newbie-dev-buddy-dependency-")
        self.base = Path(self.temporary.name)
        self.destination = self.base / "dependency/1.6.2"

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, key="linux-x64", extra=(), zip_mode=None):
        data = io.BytesIO()
        root = "codegraph-" + key
        node = "node.exe" if key.startswith("win32-") else "node"
        entries = [(root + "/" + node, b"synthetic node", "file"),
                   (root + "/lib/dist/bin/codegraph.js", b"synthetic script", "file"),
                   (root + "/lib/package.json", b'{"version":"1.6.2"}', "file")]
        entries.extend(extra)
        if key.startswith("win32-"):
            with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content, kind in entries:
                    member = zipfile.ZipInfo(name)
                    member.create_system = 3
                    member.external_attr = ((zip_mode or stat.S_IFREG) | 0o644) << 16
                    if kind == "symlink":
                        member.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(member, content, compress_type=zipfile.ZIP_DEFLATED)
        else:
            with tarfile.open(fileobj=data, mode="w:gz") as archive:
                for name, content, kind in entries:
                    member = tarfile.TarInfo(name)
                    member.mode = 0o755 if name.endswith("/node") else 0o644
                    if kind == "file":
                        member.size = len(content)
                        archive.addfile(member, io.BytesIO(content))
                    else:
                        member.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE,
                                       "fifo": tarfile.FIFOTYPE, "char": tarfile.CHRTYPE}[kind]
                        member.linkname = "../../outside.txt"
                        archive.addfile(member)
        return data.getvalue()

    def install_synthetic(self, data=None, key="linux-x64", probe_version="1.6.2"):
        data = data if data is not None else self.archive(key)

        def download(platform_key, output):
            self.assertEqual(platform_key, key)
            output.write_bytes(data)

        with mock.patch.object(setup, "_platform_key", return_value=key), \
                mock.patch.object(setup, "_download", side_effect=download), \
                mock.patch.object(setup, "_probe", return_value=probe_version):
            return setup.install(self.destination)

    def test_all_six_official_platforms_have_fixed_hashes(self):
        self.assertEqual(len(setup.SHA256), 6)
        for system, machine, key in [("darwin", "arm64", "darwin-arm64"),
                                     ("darwin", "x86_64", "darwin-x64"),
                                     ("linux", "aarch64", "linux-arm64"),
                                     ("linux", "x86_64", "linux-x64"),
                                     ("win32", "ARM64", "win32-arm64"),
                                     ("win32", "AMD64", "win32-x64")]:
            with self.subTest(key=key), mock.patch.object(setup.sys, "platform", system), \
                    mock.patch.object(setup.platform, "machine", return_value=machine):
                self.assertEqual(setup._platform_key(), key)
                self.assertRegex(setup.SHA256[key], r"^[a-f0-9]{64}$")
        with mock.patch.object(setup.platform, "machine", return_value="riscv64"):
            with self.assertRaises(setup.SetupError):
                setup._platform_key()

    def test_install_returns_bundled_node_and_explicit_mcp_arguments(self):
        result = self.install_synthetic()
        self.assertEqual(result["command"], str(self.destination / "node"))
        self.assertEqual(result["args"], [str(self.destination / "lib/dist/bin/codegraph.js"), "serve", "--mcp"])
        self.assertEqual(result["env"], setup.ENV)
        self.assertEqual(result["origin"], "download")
        self.assertEqual(result["version"], "1.6.2")
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), ["lib", "node"])

    def test_windows_bundle_never_requires_a_shell_shim(self):
        result = self.install_synthetic(key="win32-arm64")
        self.assertEqual(result["command"], str(self.destination / "node.exe"))
        self.assertTrue(result["args"][0].endswith("codegraph.js"))

    def test_existing_destination_is_not_changed(self):
        self.destination.mkdir(parents=True)
        marker = self.destination / "keep.txt"
        marker.write_text("preserve", encoding="utf-8")
        with mock.patch.object(setup, "_download") as download:
            with self.assertRaises(setup.SetupError):
                setup.install(self.destination)
            download.assert_not_called()
        self.assertEqual(marker.read_text(), "preserve")

    def test_wrong_version_is_not_published(self):
        with self.assertRaises(setup.SetupError):
            self.install_synthetic(probe_version="9.9.9")
        self.assertFalse(self.destination.exists())

    def test_concurrent_destination_creation_is_preserved(self):
        def reserve(command, prefix):
            self.destination.mkdir()
            (self.destination / "other-install.txt").write_text("preserve", encoding="utf-8")
            return "1.6.2"

        with mock.patch.object(setup, "_platform_key", return_value="linux-x64"), \
                mock.patch.object(setup, "_download", side_effect=lambda key, path: path.write_bytes(self.archive())), \
                mock.patch.object(setup, "_probe", side_effect=reserve):
            with self.assertRaises(setup.SetupError):
                setup.install(self.destination)
        self.assertEqual((self.destination / "other-install.txt").read_text(), "preserve")

    def test_path_escape_absolute_windows_drive_and_wrong_root_are_rejected(self):
        for name in ["../outside.txt", "/outside.txt", "codegraph-linux-x64/../outside.txt",
                     "codegraph-linux-x64/./outside.txt", "C:/outside.txt",
                     "codegraph-linux-x64/lib\\outside.txt", "other-root/outside.txt"]:
            with self.subTest(name=name):
                with self.assertRaises(setup.SetupError):
                    self.install_synthetic(self.archive(extra=[(name, b"outside", "file")]))
                self.assertFalse(self.destination.exists())
                self.assertFalse((self.base / "outside.txt").exists())

    def test_tar_links_fifo_and_device_are_rejected(self):
        for kind in ["symlink", "hardlink", "fifo", "char"]:
            with self.subTest(kind=kind), self.assertRaises(setup.SetupError):
                self.install_synthetic(self.archive(extra=[("codegraph-linux-x64/lib/unsafe", b"", kind)]))
        self.assertFalse(self.destination.exists())

    def test_zip_symlink_and_special_mode_are_rejected(self):
        with self.assertRaises(setup.SetupError):
            self.install_synthetic(self.archive("win32-x64", [("codegraph-win32-x64/unsafe", b"target", "symlink")]), "win32-x64")
        with self.assertRaises(setup.SetupError):
            self.install_synthetic(self.archive("win32-x64", zip_mode=stat.S_IFIFO), "win32-x64")

    def test_duplicate_and_case_colliding_entries_are_rejected(self):
        for name in ["codegraph-linux-x64/node", "codegraph-linux-x64/NODE"]:
            with self.subTest(name=name), self.assertRaises(setup.SetupError):
                self.install_synthetic(self.archive(extra=[(name, b"different", "file")]))

    def test_parent_file_conflict_and_missing_layout_are_rejected(self):
        with self.assertRaises(setup.SetupError):
            self.install_synthetic(self.archive(extra=[("codegraph-linux-x64/lib", b"file", "file")]))
        incomplete = io.BytesIO()
        with tarfile.open(fileobj=incomplete, mode="w:gz") as archive:
            member = tarfile.TarInfo("codegraph-linux-x64/node")
            member.size = 4
            archive.addfile(member, io.BytesIO(b"node"))
        with self.assertRaisesRegex(setup.SetupError, "layout is incomplete"):
            self.install_synthetic(incomplete.getvalue())
        self.assertFalse(self.destination.exists())

    def test_extraction_total_member_size_and_count_limits(self):
        for setting, limit in [("MAX_UNPACKED", 5), ("MAX_MEMBER", 5), ("MAX_MEMBERS", 2)]:
            with self.subTest(setting=setting), mock.patch.object(setup, setting, limit):
                with self.assertRaises(setup.SetupError):
                    self.install_synthetic()
                self.assertFalse(self.destination.exists())

    def test_zip_bomb_ratio_is_rejected_before_extraction(self):
        data = self.archive("win32-x64", [("codegraph-win32-x64/bomb", b"0" * (2 * 1024 * 1024), "file")])
        with self.assertRaises(setup.SetupError):
            self.install_synthetic(data, "win32-x64")
        self.assertFalse(self.destination.exists())

    def download_response(self, data, url=None):
        response = io.BytesIO(data)
        response.geturl = lambda: url or setup.BASE_URL + "codegraph-linux-x64.tar.gz"
        opener = mock.Mock()
        opener.open.return_value = response
        return opener

    def test_download_hash_failure_is_rejected(self):
        with mock.patch.object(setup.urllib.request, "build_opener", return_value=self.download_response(b"corrupt")):
            with self.assertRaisesRegex(setup.SetupError, "SHA-256"):
                setup._download("linux-x64", self.base / "download")

    def test_download_hash_is_verified_and_streaming_size_limited(self):
        data = b"valid synthetic archive"
        with mock.patch.object(setup.urllib.request, "build_opener", return_value=self.download_response(data)), \
                mock.patch.dict(setup.SHA256, {"linux-x64": hashlib.sha256(data).hexdigest()}):
            setup._download("linux-x64", self.base / "download")
        self.assertEqual((self.base / "download").read_bytes(), data)
        with mock.patch.object(setup.urllib.request, "build_opener", return_value=self.download_response(data)), \
                mock.patch.object(setup, "MAX_DOWNLOAD", 4):
            with self.assertRaisesRegex(setup.SetupError, "size limit"):
                setup._download("linux-x64", self.base / "large")

    def test_download_refuses_unofficial_redirect_and_wraps_network_failure(self):
        with mock.patch.object(setup.urllib.request, "build_opener", return_value=self.download_response(b"x", "https://example.com/bundle")):
            with self.assertRaisesRegex(setup.SetupError, "official HTTPS"):
                setup._download("linux-x64", self.base / "download")
        opener = mock.Mock()
        opener.open.side_effect = OSError("synthetic network failure")
        with mock.patch.object(setup.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(setup.SetupError):
                setup._download("linux-x64", self.base / "failure")

    def test_redirect_handler_refuses_other_host_http_and_credentials(self):
        for url in ["http://github.com/bundle", "https://example.com/bundle",
                    "https://user@github.com/bundle", "https://github.com:444/bundle"]:
            with self.subTest(url=url), self.assertRaises(setup.SetupError):
                setup._official_url(url)
        with mock.patch.object(setup, "BASE_URL", "https://example.com/"), \
                mock.patch.object(setup.urllib.request, "build_opener") as opener:
            with self.assertRaises(setup.SetupError):
                setup._download("linux-x64", self.base / "other-origin")
            opener.assert_not_called()

    def test_discover_reuses_supported_versions_and_never_installs(self):
        executable = self.base / "codegraph"
        executable.write_bytes(b"synthetic executable")
        for version in ["0.9.6", "1.6.2"]:
            with self.subTest(version=version), mock.patch.object(setup, "_run", side_effect=[version, "--mcp"]), \
                    mock.patch.object(setup, "install") as install:
                result = setup.discover(executable)
                self.assertEqual(result["version"], version)
                self.assertEqual(result["args"], ["serve", "--mcp"])
                self.assertEqual(result["origin"], "existing")
                install.assert_not_called()

    def test_discover_incompatible_existing_installation_does_not_report_absence(self):
        executable = self.base / "codegraph"
        executable.write_bytes(b"synthetic executable")
        for outputs in [["0.8.0"], ["1.6.2", "serve without MCP option"]]:
            with mock.patch.object(setup, "_run", side_effect=outputs):
                with self.assertRaises(setup.SetupError):
                    setup.discover(executable)

    def test_discover_absent_and_local_bin_fallback(self):
        with mock.patch.object(setup.shutil, "which", return_value=None), \
                mock.patch.object(setup.Path, "home", return_value=self.base):
            self.assertIsNone(setup.discover())
            executable = self.base / ".local/bin/codegraph"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"synthetic executable")
            with mock.patch.object(setup, "_run", side_effect=["0.9.6", "--mcp"]):
                self.assertEqual(setup.discover()["command"], str(executable))

    def test_windows_existing_cmd_resolves_node_without_running_cmd(self):
        root = self.base / "bundle"
        (root / "bin").mkdir(parents=True)
        (root / "lib/dist/bin").mkdir(parents=True)
        (root / "bin/codegraph.cmd").write_bytes(b"synthetic cmd")
        (root / "node.exe").write_bytes(b"synthetic node")
        (root / "lib/dist/bin/codegraph.js").write_bytes(b"synthetic js")
        with mock.patch.object(setup, "_run", side_effect=["1.6.2", "--mcp"]) as run:
            result = setup.discover(root / "bin/codegraph.cmd")
            self.assertEqual(result["command"], str(root / "node.exe"))
            self.assertEqual(run.call_args_list[0].args[0][0], str(root / "node.exe"))
        (root / "node.exe").unlink()
        with self.assertRaises(setup.SetupError):
            setup.discover(root / "bin/codegraph.cmd")

    def test_probe_has_timeout_disabled_telemetry_and_no_shell(self):
        result = subprocess.CompletedProcess(["codegraph"], 0, stdout="1.6.2", stderr="")
        with mock.patch.object(setup.subprocess, "run", return_value=result) as run:
            setup._run(["codegraph", "--version"])
            options = run.call_args.kwargs
            self.assertEqual(options["timeout"], setup.PROBE_TIMEOUT)
            self.assertFalse(options["shell"])
            self.assertEqual({key: options["env"][key] for key in setup.ENV}, setup.ENV)
        with mock.patch.object(setup.subprocess, "run", side_effect=subprocess.TimeoutExpired("codegraph", 1)):
            with self.assertRaises(setup.SetupError):
                setup._run(["codegraph", "--version"])


if __name__ == "__main__":
    unittest.main()
