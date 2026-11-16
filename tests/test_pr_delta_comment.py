import json

from ci.pr_delta_comment import build_comment, load_report_ids


def test_created_test_links_to_the_report_webapp(tmp_path):
    data = tmp_path / "data" / "test-results"
    data.mkdir(parents=True)
    (data / "abc123.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "name": "test_new",
                "fullName": "tests.test_b#test_new",
                "isRetry": False,
            }
        ),
        encoding="utf-8",
    )
    (data / "old.json").write_text(
        json.dumps(
            {
                "id": "old",
                "name": "test_new",
                "fullName": "tests.test_b#test_new",
                "isRetry": True,
            }
        ),
        encoding="utf-8",
    )

    body = build_comment(
        {"created": ["tests/test_b.py::test_new"], "changed": [], "removed": []},
        [
            {
                "name": "test_new",
                "fullName": "tests.test_b#test_new",
                "status": "passed",
                "start": 0,
                "stop": 10,
                "labels": [
                    {"name": "pr_delta", "value": "created"},
                    {"name": "feature", "value": "Health"},
                ],
            }
        ],
        "https://byron-farrell.github.io/allure_testing/pr-1",
        load_report_ids(tmp_path),
    )

    link = "[tests/test_b.py::test_new](https://byron-farrell.github.io/allure_testing/pr-1/#abc123)"
    assert link in body
    assert "old" not in body
    assert "artifact" not in body
