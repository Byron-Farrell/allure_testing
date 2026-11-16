"""Post a sticky pull-request comment for tests created or changed."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MARKER = "<!-- pr-test-delta -->"
TITLE = "Tests created or changed"


def build_comment(delta: dict, results: list[dict], artifact_url: str = "") -> str:
    created = _nodeids(delta, "created")
    changed = _nodeids(delta, "changed")
    removed = _nodeids(delta, "removed")
    if not created and not changed and not removed:
        return f"{MARKER}\n## {TITLE}\n\nNo tests were added or edited.\n"

    grouped = _group_results(results)
    created_rows = _rows(created, "created", grouped)
    changed_rows = _rows(changed, "changed", grouped)
    failed = sum(row["status"] in {"failed", "broken"} for row in [*created_rows, *changed_rows])
    parts = [
        MARKER,
        f"## {TITLE}",
        "",
        (
            f"Created {len(created)}, changed {len(changed)}, removed {len(removed)}. "
            f"Failed or broken: {failed}."
        ),
        "",
    ]
    if created_rows:
        parts.extend(["### Created", "", _table(created_rows, artifact_url), ""])
    if changed_rows:
        parts.extend(["### Changed", "", _table(changed_rows, artifact_url), ""])
    if removed:
        parts.extend(["### Removed", "", *(f"- `{nodeid}`" for nodeid in removed), ""])
    return "\n".join(parts).rstrip() + "\n"


def load_results(results_dir: Path) -> list[dict]:
    if not results_dir.is_dir():
        return []
    loaded: list[dict] = []
    for path in sorted(results_dir.glob("*-result.json")):
        loaded.append(json.loads(path.read_text(encoding="utf-8")))
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delta", required=True, help="Path to pr-test-delta.json")
    parser.add_argument("--results", required=True, help="Allure results directory")
    parser.add_argument("--artifact-url", default="", help="URL of the uploaded report artifact")
    parser.add_argument("--repo", required=True, help="GitHub repository, owner/name")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    args = parser.parse_args(argv)
    try:
        delta = json.loads(Path(args.delta).read_text(encoding="utf-8"))
        results = load_results(Path(args.results))
        body = build_comment(delta, results, args.artifact_url)
        _write_summary(body)
        _upsert_comment(args.repo, args.pr, body)
    except (OSError, json.JSONDecodeError, RuntimeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(detail or str(exc), file=sys.stderr)
        return 1
    return 0


def nodeid_to_fullname(nodeid: str) -> str:
    """Match allure-pytest 2.16 ``fullName`` for a parameter-free node id."""
    nodeid = nodeid.split("[", 1)[0]
    filepath, *class_names, test = nodeid.split("::")
    parent_dirs = filepath.split("/")[:-1]
    module = filepath.split("/")[-1].rsplit(".", 1)[0]
    package = ".".join([*parent_dirs, module])
    class_part = f".{'.'.join(class_names)}" if class_names else ""
    return f"{package}{class_part}#{test}"


def _nodeids(delta: dict, key: str) -> list[str]:
    return [str(nodeid) for nodeid in delta.get(key) or []]


def _group_results(results: list[dict]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for result in results:
        kind = _pr_delta(result)
        if kind is None:
            continue
        full_name = _strip_params(str(result.get("fullName") or ""))
        grouped.setdefault((kind, full_name), []).append(result)
    for matches in grouped.values():
        matches.sort(key=lambda item: str(item.get("name") or ""))
    return grouped


def _rows(nodeids: list[str], kind: str, grouped: dict[tuple[str, str], list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for nodeid in nodeids:
        matches = grouped.get((kind, nodeid_to_fullname(nodeid)), [])
        if not matches:
            rows.append({"name": nodeid, "status": "not run", "duration": "", "feature": ""})
            continue
        for result in matches:
            rows.append(
                {
                    "name": _display_name(nodeid, result),
                    "status": str(result.get("status") or "unknown"),
                    "duration": _duration(result),
                    "feature": _feature_or_suite(result),
                }
            )
    return rows


def _pr_delta(result: dict) -> str | None:
    for label in result.get("labels") or []:
        if label.get("name") == "pr_delta" and label.get("value") in {"created", "changed"}:
            return str(label["value"])
    return None


def _strip_params(value: str) -> str:
    return value.split("[", 1)[0]


def _display_name(nodeid: str, result: dict) -> str:
    result_name = str(result.get("name") or "")
    bracket = result_name.find("[")
    if bracket == -1:
        return nodeid
    return f"{nodeid}{result_name[bracket:]}"


def _duration(result: dict) -> str:
    start = result.get("start")
    stop = result.get("stop")
    if not isinstance(start, (int, float)) or not isinstance(stop, (int, float)):
        return ""
    milliseconds = max(0, int(stop - start))
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    return f"{milliseconds / 1000:.2f} s"


def _feature_or_suite(result: dict) -> str:
    feature = ""
    suite = ""
    for label in result.get("labels") or []:
        name = label.get("name")
        value = str(label.get("value") or "")
        if name == "feature" and value and not feature:
            feature = value
        elif name == "suite" and value and not suite:
            suite = value
    return feature or suite


def _table(rows: list[dict], artifact_url: str) -> str:
    lines = [
        "| Name | Status | Duration | Feature |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [
            _link(row["name"], artifact_url),
            _cell(row["status"]),
            _cell(row["duration"]),
            _cell(row["feature"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _link(name: str, url: str) -> str:
    safe_name = _cell(name).replace("]", "\\]")
    if not url:
        return f"`{safe_name}`"
    return f"[{safe_name}]({url})"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _write_summary(body: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(body)
        if not body.endswith("\n"):
            handle.write("\n")


def _upsert_comment(repo: str, pr: int, body: str) -> None:
    listed = _gh("api", "--paginate", f"repos/{repo}/issues/{pr}/comments")
    comments = json.loads(listed or "[]")
    existing = next((comment for comment in comments if MARKER in (comment.get("body") or "")), None)
    payload = json.dumps({"body": body})
    if existing is None:
        _gh(
            "api",
            "--method",
            "POST",
            f"repos/{repo}/issues/{pr}/comments",
            "--input",
            "-",
            input_text=payload,
        )
        return
    _gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/issues/comments/{existing['id']}",
        "--input",
        "-",
        input_text=payload,
    )


def _gh(*args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["gh", *args],
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "gh command failed").strip()
        raise RuntimeError(detail)
    return completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())
