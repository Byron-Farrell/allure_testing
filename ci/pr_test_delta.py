"""Classify pytest tests created, changed, or removed between two commits."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


def classify_sources(
    base: Mapping[str, str],
    head: Mapping[str, str],
    renames: Sequence[tuple[str, str]] = (),
) -> dict[str, list[str]]:
    """Compare pytest modules supplied as path-to-source maps.

    ``renames`` pairs a merge-base path with its head path, matching
    ``git diff -M``. The same function or method name keeps one identity and
    is changed because the path changed. A name that exists on only one side
    is removed or created.
    """
    created: list[str] = []
    changed: list[str] = []
    removed: list[str] = []
    consumed: set[str] = set()

    for old, new in renames:
        consumed.add(old)
        consumed.add(new)
        old_tests = _tests_at(old, base)
        new_tests = _tests_at(new, head)
        old_by_suffix = {_suffix(nodeid): nodeid for nodeid in old_tests}
        new_by_suffix = {_suffix(nodeid): nodeid for nodeid in new_tests}
        for suffix, nodeid in new_by_suffix.items():
            if suffix in old_by_suffix:
                changed.append(nodeid)
            else:
                created.append(nodeid)
        for suffix, nodeid in old_by_suffix.items():
            if suffix not in new_by_suffix:
                removed.append(nodeid)

    for path in sorted(set(base) | set(head)):
        if path in consumed or not _is_test_module(path):
            continue
        old_tests = _tests_at(path, base)
        new_tests = _tests_at(path, head)
        for nodeid, fingerprint in new_tests.items():
            if nodeid not in old_tests:
                created.append(nodeid)
            elif old_tests[nodeid] != fingerprint:
                changed.append(nodeid)
        for nodeid in old_tests:
            if nodeid not in new_tests:
                removed.append(nodeid)

    return {
        "created": sorted(created),
        "changed": sorted(changed),
        "removed": sorted(removed),
    }


def classify_commits(repo: Path, base: str, head: str) -> dict[str, list[str]]:
    """Classify tests changed between ``base`` and ``head`` using git."""
    merge_base = _git(repo, "merge-base", base, head).strip()
    if not merge_base:
        raise RuntimeError(f"git merge-base returned no commit for {base} and {head}")
    diff = _git(repo, "diff", "-M", "--name-status", merge_base, head)
    added, modified, deleted, renames = _parse_name_status(diff)

    base_sources: dict[str, str] = {}
    head_sources: dict[str, str] = {}
    for path in added:
        if _is_test_module(path):
            head_sources[path] = _git_show(repo, head, path)
    for path in deleted:
        if _is_test_module(path):
            base_sources[path] = _git_show(repo, merge_base, path)
    for path in modified:
        if _is_test_module(path):
            base_sources[path] = _git_show(repo, merge_base, path)
            head_sources[path] = _git_show(repo, head, path)
    kept_renames: list[tuple[str, str]] = []
    for old, new in renames:
        if not (_is_test_module(old) or _is_test_module(new)):
            continue
        kept_renames.append((old, new))
        if _is_test_module(old):
            base_sources[old] = _git_show(repo, merge_base, old)
        if _is_test_module(new):
            head_sources[new] = _git_show(repo, head, new)
    return classify_sources(base_sources, head_sources, kept_renames)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", required=True, help="Head commit SHA")
    parser.add_argument("--output", default="pr-test-delta.json", help="Delta JSON path")
    parser.add_argument("--repo", default=".", help="Git repository path")
    args = parser.parse_args(argv)
    try:
        delta = classify_commits(Path(args.repo), args.base, args.head)
    except (OSError, RuntimeError, SyntaxError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    Path(args.output).write_text(json.dumps(delta, indent=2) + "\n", encoding="utf-8")
    return 0


def _tests_at(path: str, sources: Mapping[str, str]) -> dict[str, str]:
    if not _is_test_module(path) or path not in sources:
        return {}
    return extract_tests(path, sources[path])


def extract_tests(path: str, source: str) -> dict[str, str]:
    tree = _parse(path, source)
    pytestmark = _module_pytestmark(tree)
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            found[f"{path}::{node.name}"] = _fingerprint(node, [], pytestmark)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            decorators = list(node.decorator_list)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                    found[f"{path}::{node.name}::{child.name}"] = _fingerprint(child, decorators, pytestmark)
    return found


def _parse(path: str, source: str) -> ast.Module:
    try:
        return ast.parse(source, filename=path)
    except SyntaxError as exc:
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        raise SyntaxError(f"cannot parse {path}: {exc.msg} ({location})") from exc


def _module_pytestmark(tree: ast.Module) -> list[ast.AST]:
    marks: list[ast.AST] = []
    for node in tree.body:
        value = _assigned_name(node, "pytestmark")
        if value is not None:
            marks.append(value)
    return marks


def _assigned_name(node: ast.AST, name: str) -> ast.AST | None:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return node.value
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
        and node.value is not None
    ):
        return node.value
    return None


def _fingerprint(
    function: ast.AST,
    class_decorators: list[ast.expr],
    pytestmark: list[ast.AST],
) -> str:
    return "\n".join(
        [
            ast.dump(function),
            "[" + ",".join(ast.dump(item) for item in class_decorators) + "]",
            "[" + ",".join(ast.dump(item) for item in pytestmark) + "]",
        ]
    )


def _suffix(nodeid: str) -> str:
    return nodeid.split("::", 1)[1]


def _is_test_module(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def _parse_name_status(
    diff: str,
) -> tuple[list[str], list[str], list[str], list[tuple[str, str]]]:
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    renames: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        code = parts[0][:1]
        if code == "R" and len(parts) >= 3:
            renames.append((parts[1], parts[2]))
        elif code == "A" and len(parts) >= 2:
            added.append(parts[1])
        elif code == "D" and len(parts) >= 2:
            deleted.append(parts[1])
        elif code in {"M", "T"} and len(parts) >= 2:
            modified.append(parts[1])
    return added, modified, deleted, renames


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git command failed").strip()
        raise RuntimeError(detail)
    return completed.stdout


def _git_show(repo: Path, sha: str, path: str) -> str:
    return _git(repo, "show", f"{sha}:{path}")


if __name__ == "__main__":
    raise SystemExit(main())
