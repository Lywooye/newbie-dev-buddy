"""Install a pinned official CodeGraph bundle without changing host configuration."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
import urllib.request
import zipfile


VERSION = "1.6.2"
BASE_URL = "https://github.com/colbymchenry/codegraph/releases/download/v1.6.2/"
SHA256 = {
    "darwin-arm64": "d74d1bfb4060db63ec3c2b72c4e17f76c31978af3bad6ace4370d1501ac0662e",
    "darwin-x64": "53d1a4d1a9af31d6cec11b346df2ae792087081e13f623f583e27783c1e7f9bc",
    "linux-arm64": "c8c6be292be21d00dea26bad8b28d434731cf612fb8cc475dc10f5b3038b5b64",
    "linux-x64": "ef0af416092128fb1ccc723786000b7edf4a6971fe604acd08bf966e4f37b828",
    "win32-arm64": "308f7bf92e7886f4d5f767a4755d703e92d5cae78ac042b8907f1e99db0fc071",
    "win32-x64": "7455e817ee8032666867a1badeb799b8a884c5f4fea9b444e088a02069b6deea",
}
ENV = {"DO_NOT_TRACK": "1", "CODEGRAPH_NO_UPDATE_CHECK": "1"}
MAX_DOWNLOAD = 250 * 1024 * 1024
MAX_UNPACKED = 1024 * 1024 * 1024
MAX_MEMBER = 250 * 1024 * 1024
MAX_MEMBERS = 20000
PROBE_TIMEOUT = 15


class SetupError(RuntimeError):
    """A dependency cannot be reused or safely installed."""


def _platform_key():
    machine = platform.machine().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64",
            "amd64": "x64", "x64": "x64"}.get(machine)
    key = sys.platform + "-" + str(arch)
    if key not in SHA256:
        raise SetupError("CodeGraph bundle unavailable for this platform and architecture")
    return key


def _run(arguments):
    environment = dict(os.environ, **ENV)
    try:
        with tempfile.TemporaryDirectory(prefix="newbie-dev-buddy-probe-") as working:
            result = subprocess.run(arguments, cwd=working, env=environment,
                                    capture_output=True, text=True, timeout=PROBE_TIMEOUT,
                                    shell=False)
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise SetupError("CodeGraph compatibility check could not run") from exc
    if result.returncode:
        raise SetupError("CodeGraph compatibility check failed; existing installation was not changed")
    return result.stdout + result.stderr


def _probe(command, prefix):
    output = _run([str(command), *map(str, prefix), "--version"])
    match = re.search(r"(?<![\d.])(\d+)\.(\d+)\.(\d+)(?![\d.])", output)
    if not match or tuple(map(int, match.groups())) < (0, 9, 6):
        raise SetupError("Existing CodeGraph version is unsupported; no automatic upgrade was performed")
    if "--mcp" not in _run([str(command), *map(str, prefix), "serve", "--help"]):
        raise SetupError("Existing CodeGraph lacks serve --mcp; no automatic upgrade was performed")
    return ".".join(match.groups())


def _result(command, prefix, version, origin):
    return {"command": str(command), "args": [*map(str, prefix), "serve", "--mcp"],
            "version": version, "origin": origin, "env": dict(ENV)}


def _invocation(executable):
    candidate = Path(executable).expanduser().absolute()
    if candidate.suffix.lower() in (".cmd", ".bat", ".ps1"):
        # Official Windows bundles keep Node at their root, beside lib/ and bin/.
        root = candidate.parent.parent if candidate.parent.name == "bin" else candidate.parent
        node = root / "node.exe"
        script = root / "lib/dist/bin/codegraph.js"
        if not node.is_file() or not script.is_file():
            raise SetupError("Existing Windows shell shim cannot be safely reused; configure the bundled Node executable")
        return node, [script]
    if candidate.name.lower() in ("node", "node.exe"):
        script = candidate.parent / "lib/dist/bin/codegraph.js"
        if not script.is_file():
            raise SetupError("Bundled CodeGraph JavaScript entrypoint is missing")
        return candidate, [script]
    return candidate, []


def discover(executable=None):
    """Return a compatible existing command; absence alone returns None."""
    if executable is None:
        executable = shutil.which("codegraph")
        if executable is None:
            for candidate in (Path.home() / ".local/bin/codegraph",
                              Path.home() / ".codegraph/bin/codegraph",
                              Path.home() / ".codegraph/bin/codegraph.cmd"):
                if os.path.lexists(candidate):
                    executable = candidate
                    break
        if executable is None:
            return None
    elif not Path(executable).expanduser().is_file():
        raise SetupError("Specified CodeGraph executable does not exist")
    command, prefix = _invocation(executable)
    return _result(command, prefix, _probe(command, prefix), "existing")


def _official_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in
            {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise SetupError("Download source is not an official HTTPS GitHub release host")


class _ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(key, output):
    suffix = ".zip" if key.startswith("win32-") else ".tar.gz"
    url = BASE_URL + "codegraph-" + key + suffix
    _official_url(url)
    digest = hashlib.sha256()
    count = 0
    opener = urllib.request.build_opener(_ReleaseRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "Newbie-Dev-Buddy"})
    try:
        with opener.open(request, timeout=30) as response, output.open("xb") as target:
            _official_url(response.geturl())
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_DOWNLOAD:
                    raise SetupError("CodeGraph download exceeds the size limit")
                digest.update(chunk)
                target.write(chunk)
    except SetupError:
        raise
    except (OSError, ValueError) as exc:
        raise SetupError("Could not download the official CodeGraph bundle") from exc
    if digest.hexdigest() != SHA256[key]:
        raise SetupError("CodeGraph bundle SHA-256 does not match the pinned official release")


def _member_path(name, root):
    if (not name or "\\" in name or "\x00" in name or ":" in name
            or name.startswith("/") or any(part in (".", "..") for part in name.split("/"))):
        raise SetupError("Unsafe path in CodeGraph archive")
    parts = PurePosixPath(name).parts
    if not parts or parts[0] != root:
        raise SetupError("Unexpected CodeGraph bundle root")
    for part in parts:
        if part.rstrip(" .") != part or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", part):
            raise SetupError("Nonportable path in CodeGraph archive")
    return Path(*parts[1:])


def _unpack(archive, target, key):
    root = "codegraph-" + key
    is_zip = key.startswith("win32-")
    package = zipfile.ZipFile(archive) if is_zip else tarfile.open(archive, "r:gz")
    with package:
        entries = []
        seen = {}
        size = 0
        for member in package.infolist() if is_zip else package:
            name = member.filename if is_zip else member.name
            path = _member_path(name.rstrip("/"), root)
            directory = member.is_dir() if is_zip else member.isdir()
            mode = (member.external_attr >> 16) if is_zip else member.mode
            kind = stat.S_IFMT(mode) if is_zip else None
            if (is_zip and kind not in (0, stat.S_IFREG, stat.S_IFDIR)) or (
                    not is_zip and not (member.isfile() or directory)):
                raise SetupError("Links and special files are forbidden in CodeGraph bundles")
            length = member.file_size if is_zip else member.size
            size += length
            identity = str(path).casefold()
            if identity in seen or (path == Path(".") and not directory):
                raise SetupError("Duplicate or invalid path in CodeGraph bundle")
            seen[identity] = directory
            if length < 0 or length > MAX_MEMBER or size > MAX_UNPACKED or len(entries) >= MAX_MEMBERS:
                raise SetupError("CodeGraph archive exceeds extraction limits")
            if directory and length:
                raise SetupError("Directory entry contains unexpected data")
            if is_zip and length > 1024 * 1024 and length > 200 * max(member.compress_size, 1):
                raise SetupError("Suspicious CodeGraph archive compression ratio")
            entries.append((member, path, directory, length, mode))
        required = {"node.exe" if is_zip else "node", "lib/dist/bin/codegraph.js", "lib/package.json"}
        if not required.issubset({str(path).replace(os.sep, "/") for _, path, directory, _, _ in entries if not directory}):
            raise SetupError("Official CodeGraph bundle layout is incomplete")
        for _, path, _, _, _ in entries:
            for parent in path.parents:
                if str(parent).casefold() in seen and not seen[str(parent).casefold()]:
                    raise SetupError("Archive file conflicts with a directory")
        for member, path, directory, length, mode in entries:
            destination = target / path
            if directory:
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = package.open(member) if is_zip else package.extractfile(member)
            with source, destination.open("xb") as output:
                remaining = length
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise SetupError("Truncated CodeGraph archive member")
                    output.write(chunk)
                    remaining -= len(chunk)
                if source.read(1):
                    raise SetupError("Archive member exceeds declared size")
            destination.chmod(0o755 if mode & 0o111 or path.name in ("node", "node.exe") else 0o644)


def install(destination):
    """Download, verify, stage and probe the pinned bundle; never replace a directory."""
    destination = Path(destination).expanduser().absolute()
    if os.path.lexists(destination):
        raise SetupError("CodeGraph destination already exists; it was not changed")
    key = _platform_key()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=".newbie-dev-buddy-codegraph-", dir=destination.parent) as working:
            working = Path(working)
            archive = working / "bundle"
            _download(key, archive)
            stage = working / "install"
            stage.mkdir()
            _unpack(archive, stage, key)
            node = "node.exe" if key.startswith("win32-") else "node"
            prefix = [stage / "lib/dist/bin/codegraph.js"]
            if _probe(stage / node, prefix) != VERSION:
                raise SetupError("Downloaded CodeGraph reports an unexpected version")
            # Reserve exclusively so a concurrent installation is never overwritten.
            destination.mkdir()
            try:
                for child in stage.iterdir():
                    shutil.move(str(child), str(destination / child.name))
            except Exception:
                shutil.rmtree(destination)
                raise
    except SetupError:
        raise
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise SetupError("Could not safely install the official CodeGraph bundle") from exc
    return _result(destination / node, [destination / "lib/dist/bin/codegraph.js"], VERSION, "download")
