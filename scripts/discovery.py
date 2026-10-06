"""Read-only text inventory; Python syntax observations are not module boundaries."""
import ast
from collections import Counter
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat


SKIP_NAMES = {".git", ".handoff", ".acceptance", "node_modules", ".venv", "venv",
              "dist", "build", "__pycache__", ".DS_Store", ".ssh", ".aws", ".credentials"}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".pkcs12", ".crt", ".cert", ".cer", ".der",
                    ".csr", ".p7b", ".p7c", ".jks", ".keystore", ".pub"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip",
                   ".gz", ".bz2", ".xz", ".tar", ".woff", ".woff2", ".ttf",
                   ".sqlite", ".sqlite3", ".db", ".dylib", ".so", ".exe", ".o",
                   ".class", ".pyc"}
LANGUAGES = {".py": "python", ".pyi": "python", ".js": "javascript", ".mjs": "javascript",
             ".cjs": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
             ".go": "go", ".rs": "rust", ".java": "java", ".c": "c", ".h": "c",
             ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp", ".rb": "ruby", ".sh": "shell",
             ".sql": "sql", ".html": "html", ".css": "css", ".md": "markdown",
             ".json": "json", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml"}
SOURCE_LANGUAGES = {"python", "javascript", "typescript", "go", "rust", "java", "c", "cpp",
                    "ruby", "shell", "sql", "html", "css"}
MAX_ENTRIES = 100000
MAX_DEPTH = 128


def _excluded_reason(relative, patterns):
    path = PurePosixPath(relative)
    name = path.name
    if name in SKIP_NAMES or relative == "docs/module-change":
        return "default_exclusion"
    if name.lower().startswith(".env") or name.lower().startswith(("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")):
        return "sensitive_name"
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        return "private_key_or_certificate"
    if any(relative == pattern or relative.startswith(pattern + "/") or
           fnmatch.fnmatchcase(relative, pattern) for pattern in patterns):
        return "user_exclusion"
    return None


def _category(relative, language):
    path = PurePosixPath(relative)
    if any(part in {"test", "tests"} for part in path.parts) or path.name.startswith("test_") or \
            path.name.endswith("_test.py") or ".test." in path.name or ".spec." in path.name:
        return "test"
    if language == "markdown" or "docs" in path.parts:
        return "documentation"
    if language in {"json", "toml", "yaml", "xml"} or path.name in {"Dockerfile", "Makefile"} or \
            path.name.startswith("requirements"):
        return "configuration"
    return "source" if language in SOURCE_LANGUAGES else "other"


class _PythonFacts(ast.NodeVisitor):
    def __init__(self):
        self.scope = []
        self.symbols = []
        self.imports = []

    def _symbol(self, node, kind):
        name = ".".join(self.scope + [node.name])
        self.symbols.append({"name": name, "kind": kind, "line": node.lineno,
                             "end_line": getattr(node, "end_lineno", node.lineno)})
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node):
        self._symbol(node, "class")

    def visit_FunctionDef(self, node):
        self._symbol(node, "function")

    def visit_AsyncFunctionDef(self, node):
        self._symbol(node, "async_function")

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({"kind": "import", "module": alias.name, "level": 0,
                                 "names": [], "line": node.lineno, "scope": ".".join(self.scope)})

    def visit_ImportFrom(self, node):
        self.imports.append({"kind": "from", "module": node.module or "", "level": node.level,
                             "names": [alias.name for alias in node.names],
                             "line": node.lineno, "scope": ".".join(self.scope)})


def _read_file(directory_fd, name, observed, limit):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(name, flags, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "special_file"
        if before.st_nlink != 1:
            return None, "hard_link"
        if (before.st_dev, before.st_ino) != (observed.st_dev, observed.st_ino):
            return None, "changed_during_scan"
        if before.st_size > limit:
            return None, "too_large"
        chunks = []
        size = 0
        while size <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        if size > limit:
            return None, "too_large"
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != \
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            return None, "changed_during_scan"
        return b"".join(chunks), None
    finally:
        os.close(descriptor)


def collect(root, excludes=(), max_bytes=262144):
    """Return relative file fingerprints and syntax facts without executing project code.

    Excludes are project-relative paths or fnmatch patterns; default exclusions
    always apply. Only included text contents are fingerprinted. Omitted entries
    are outside coverage, including future changes under excluded directories.
    Safe directory-relative opens require macOS/Linux (or equivalent Unix APIs).
    """
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    if isinstance(excludes, str):
        raise ValueError("excludes must be a sequence of project-relative paths or patterns")
    patterns = []
    for value in excludes:
        if not isinstance(value, str) or not value or PurePosixPath(value).is_absolute() or \
                ".." in PurePosixPath(value).parts or "\\" in value:
            raise ValueError("exclusions must be project-relative paths or patterns without '..'")
        patterns.append(value.rstrip("/"))
    if os.open not in os.supports_dir_fd or os.scandir not in os.supports_fd or \
            not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("discovery requires safe Unix directory-relative opens")
    root = Path(root)
    if root.is_symlink():
        raise ValueError("project root must not be a symlink")
    files, excluded, warnings = [], [], []
    visited = set()
    entries_seen = 0
    included_bytes = 0

    def omit(relative, reason):
        excluded.append({"path": relative, "reason": reason})

    def walk(descriptor, prefix, depth):
        nonlocal entries_seen, included_bytes
        identity = os.fstat(descriptor)
        key = (identity.st_dev, identity.st_ino)
        if key in visited:
            omit(prefix or ".", "repeated_directory")
            return
        visited.add(key)
        if depth > MAX_DEPTH:
            omit(prefix or ".", "depth_limit")
            return
        try:
            with os.scandir(descriptor) as iterator:
                for entry in iterator:
                    if entries_seen >= MAX_ENTRIES:
                        omit(prefix or ".", "entry_limit")
                        return
                    entries_seen += 1
                    relative = prefix + "/" + entry.name if prefix else entry.name
                    reason = _excluded_reason(relative, patterns)
                    if reason:
                        omit(relative, reason)
                        continue
                    try:
                        observed = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(observed.st_mode):
                            omit(relative, "symlink")
                        elif stat.S_ISDIR(observed.st_mode):
                            child = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
                                            dir_fd=descriptor)
                            try:
                                current = os.fstat(child)
                                if (current.st_dev, current.st_ino) != (observed.st_dev, observed.st_ino):
                                    omit(relative, "changed_during_scan")
                                else:
                                    walk(child, relative, depth + 1)
                            finally:
                                os.close(child)
                        elif not stat.S_ISREG(observed.st_mode):
                            omit(relative, "special_file")
                        elif observed.st_nlink != 1:
                            omit(relative, "hard_link")
                        elif observed.st_size > max_bytes:
                            omit(relative, "too_large")
                        elif PurePosixPath(relative).suffix.lower() in BINARY_SUFFIXES:
                            omit(relative, "binary")
                        else:
                            data, reason = _read_file(descriptor, entry.name, observed, max_bytes)
                            if reason:
                                omit(relative, reason)
                                continue
                            try:
                                if b"\x00" in data:
                                    raise UnicodeError()
                                content = data.decode("utf-8-sig")
                            except UnicodeError:
                                omit(relative, "binary_or_non_utf8")
                                continue
                            language = LANGUAGES.get(PurePosixPath(relative).suffix.lower(), "text")
                            item = {"path": relative, "sha256": hashlib.sha256(data).hexdigest(),
                                    "language": language, "category": _category(relative, language)}
                            if language == "python":
                                try:
                                    facts = _PythonFacts()
                                    facts.visit(ast.parse(content, filename=relative))
                                    item.update(symbols=facts.symbols, imports=facts.imports)
                                except (SyntaxError, ValueError, RecursionError):
                                    warnings.append(relative + ": Python AST unavailable; symbols and imports were not extracted.")
                            files.append(item)
                            included_bytes += len(data)
                    except OSError:
                        omit(relative, "io_error")
        except OSError:
            omit(prefix or ".", "directory_io_error")

    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
    except OSError:
        raise ValueError("project root must be a readable directory") from None
    try:
        walk(descriptor, "", 0)
    finally:
        os.close(descriptor)
    files.sort(key=lambda item: item["path"])
    excluded.sort(key=lambda item: (item["path"], item["reason"]))
    if any(item["language"] == "python" for item in files):
        warnings.append("Python imports are syntax observations; dynamic imports and runtime calls are not resolved.")
    if any(item["language"] in SOURCE_LANGUAGES - {"python"} for item in files):
        warnings.append("Non-Python source files are inventoried without a deterministic import or call graph.")
    if excluded:
        warnings.append("Excluded entries are outside content coverage; their contents and descendants are not fingerprinted.")
    inventory = {item["path"]: item["sha256"] for item in files}
    fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"schema": 1, "files": files, "excluded": excluded, "warnings": sorted(warnings),
            "summary": {"inventory_sha256": fingerprint, "included_files": len(files),
                        "included_bytes": included_bytes, "excluded_entries": len(excluded),
                        "entries_seen": entries_seen,
                        "languages": dict(sorted(Counter(item["language"] for item in files).items())),
                        "coverage": "included_text_files_only"}}
