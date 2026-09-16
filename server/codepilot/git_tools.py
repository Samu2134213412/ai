"""Read-only git inspection for a project directory.

v1 never writes to a repository and never pushes. Every command is run with an
explicit ``cwd`` inside a registered project and with a fixed argument list, so
nothing from the phone reaches a shell.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT = 20.0


class GitUnavailable(Exception):
    pass


def _git(cwd: str | Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise GitUnavailable("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitUnavailable(f"git {' '.join(args)} timed out") from exc
    except NotADirectoryError as exc:
        raise GitUnavailable(f"project directory is gone: {cwd}") from exc
    if proc.returncode != 0:
        raise GitUnavailable((proc.stderr or proc.stdout).strip() or
                             f"git {' '.join(args)} failed with code {proc.returncode}")
    return proc.stdout


def is_repo(path: str | Path) -> bool:
    try:
        return _git(path, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except GitUnavailable:
        return False


def current_branch(path: str | Path) -> str | None:
    try:
        branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except GitUnavailable:
        return None
    if branch == "HEAD":  # detached
        try:
            return "detached@" + _git(path, "rev-parse", "--short", "HEAD").strip()
        except GitUnavailable:
            return "detached"
    return branch


def head_commit(path: str | Path) -> str | None:
    try:
        return _git(path, "rev-parse", "HEAD").strip()
    except GitUnavailable:
        return None


#: git status --porcelain XY codes -> our categories
_STATUS_LABELS = {
    "??": "untracked", "A": "added", "M": "modified", "D": "deleted",
    "R": "renamed", "C": "copied", "U": "conflicted", "T": "typechange",
}


def status(path: str | Path) -> dict:
    """Parse ``git status --porcelain=v1 -z`` into a structured summary."""
    if not Path(path).exists():
        raise GitUnavailable(f"project directory no longer exists: {path}")
    if not is_repo(path):
        return {"is_repo": False, "branch": None, "files": [], "clean": True,
                "counts": {}}

    raw = _git(path, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    files: list[dict] = []
    parts = raw.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if code[0] in ("R", "C"):
            # rename/copy entries are followed by the original path
            original = parts[i] if i < len(parts) else None
            i += 1
            files.append({"path": name, "code": code, "original": original,
                          "status": _STATUS_LABELS.get(code[0], "changed"),
                          "staged": code[0] != " ", "unstaged": code[1] != " "})
            continue
        if code == "??":
            label = "untracked"
        else:
            label = _STATUS_LABELS.get(code[1].strip() or code[0].strip(), "changed")
        files.append({"path": name, "code": code, "original": None, "status": label,
                      "staged": code[0] not in (" ", "?"),
                      "unstaged": code[1] not in (" ", "?")})

    counts: dict[str, int] = {}
    for f in files:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    return {"is_repo": True, "branch": current_branch(path), "files": files,
            "clean": not files, "counts": counts,
            "head": head_commit(path)}


def changed_files(path: str | Path, base_commit: str | None = None) -> list[dict]:
    """Per-file added/removed line counts, optionally against a base commit."""
    if not is_repo(path):
        return []
    entries: dict[str, dict] = {}

    def absorb(raw: str, kind: str) -> None:
        for line in raw.splitlines():
            if not line.strip():
                continue
            added, removed, name = (line.split("\t") + ["", "", ""])[:3]
            rec = entries.setdefault(name, {"path": name, "added": 0, "removed": 0,
                                            "binary": False, "kind": kind})
            if added == "-" or removed == "-":
                rec["binary"] = True
            else:
                rec["added"] += int(added or 0)
                rec["removed"] += int(removed or 0)

    try:
        if base_commit:
            absorb(_git(path, "diff", "--numstat", base_commit), "since-task-start")
        else:
            absorb(_git(path, "diff", "--numstat", "HEAD"), "working-tree")
    except GitUnavailable:
        # No HEAD yet (fresh repo) — fall back to the index.
        try:
            absorb(_git(path, "diff", "--numstat", "--cached"), "staged")
        except GitUnavailable:
            return []

    # Untracked files have no numstat entry; count their lines directly.
    try:
        untracked = _git(path, "ls-files", "--others", "--exclude-standard", "-z")
    except GitUnavailable:
        untracked = ""
    for name in filter(None, untracked.split("\0")):
        target = Path(path) / name
        rec = entries.setdefault(name, {"path": name, "added": 0, "removed": 0,
                                        "binary": False, "kind": "untracked"})
        rec["kind"] = "untracked"
        try:
            content = target.read_bytes()
            if b"\0" in content[:8000]:
                rec["binary"] = True
            else:
                rec["added"] = content.decode("utf-8", "replace").count("\n") + 1
        except OSError:
            pass
    return sorted(entries.values(), key=lambda e: e["path"])


def file_diff(path: str | Path, relative: str, base_commit: str | None = None) -> str:
    """Unified diff for one file. Untracked files render as an all-added diff."""
    root = Path(path)
    if not is_repo(root):
        raise GitUnavailable("not a git repository")
    args = ["diff", "--no-color", "--no-ext-diff"]
    if base_commit:
        args.append(base_commit)
    else:
        args.append("HEAD")
    args += ["--", relative]
    try:
        out = _git(root, *args)
    except GitUnavailable:
        out = ""
    if out.strip():
        return out

    target = root / relative
    if target.exists() and target.is_file():
        try:
            content = target.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            return f"--- /dev/null\n+++ b/{relative}\n(binary or unreadable file)\n"
        lines = content.splitlines()
        body = "\n".join("+" + ln for ln in lines)
        return (f"--- /dev/null\n+++ b/{relative}\n"
                f"@@ -0,0 +1,{len(lines)} @@\n{body}\n")
    return ""
