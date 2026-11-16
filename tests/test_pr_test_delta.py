from ci.pr_test_delta import classify_sources


def test_new_test_is_created():
    base = {"tests/test_a.py": "def test_kept():\n    assert True\n"}
    head = {
        "tests/test_a.py": "def test_kept():\n    assert True\n",
        "tests/test_b.py": "def test_new():\n    assert True\n",
    }

    assert classify_sources(base, head) == {
        "created": ["tests/test_b.py::test_new"],
        "changed": [],
        "removed": [],
    }


def test_edited_body_is_changed_and_untouched_test_is_omitted():
    base = {
        "tests/test_a.py": (
            "def test_untouched():\n"
            "    assert True\n"
            "\n"
            "def test_edited():\n"
            "    assert 1 == 1\n"
        )
    }
    head = {
        "tests/test_a.py": (
            "def test_untouched():\n"
            "    assert True\n"
            "\n"
            "def test_edited():\n"
            "    x = 1\n"
            "    assert x == 2\n"
        )
    }

    delta = classify_sources(base, head)

    assert delta["changed"] == ["tests/test_a.py::test_edited"]
    assert delta["created"] == []
    assert delta["removed"] == []
    assert "tests/test_a.py::test_untouched" not in delta["changed"]


def test_deleted_test_is_removed():
    base = {
        "tests/test_a.py": (
            "def test_gone():\n"
            "    assert True\n"
            "\n"
            "def test_stays():\n"
            "    assert True\n"
        )
    }
    head = {"tests/test_a.py": "def test_stays():\n    assert True\n"}

    assert classify_sources(base, head) == {
        "created": [],
        "changed": [],
        "removed": ["tests/test_a.py::test_gone"],
    }


def test_parametrized_template_is_changed_once():
    base = {
        "tests/test_nums.py": (
            "import pytest\n"
            "\n"
            "@pytest.mark.parametrize('n', [1, 2])\n"
            "def test_nums(n):\n"
            "    assert n\n"
        )
    }
    head = {
        "tests/test_nums.py": (
            "import pytest\n"
            "\n"
            "@pytest.mark.parametrize('n', [1, 2, 3])\n"
            "def test_nums(n):\n"
            "    assert n\n"
        )
    }

    delta = classify_sources(base, head)

    assert delta["changed"] == ["tests/test_nums.py::test_nums"]
    assert delta["created"] == []
    assert delta["removed"] == []


def test_whitespace_and_comment_only_edit_is_omitted():
    base = {"tests/test_a.py": "def test_a():\n    assert True\n"}
    head = {"tests/test_a.py": "def test_a():   \n    # comment only\n    assert True\n\n"}

    assert classify_sources(base, head) == {
        "created": [],
        "changed": [],
        "removed": [],
    }


def test_rename_same_name_is_changed_and_different_name_is_removed_and_created():
    base = {
        "tests/test_old.py": (
            "def test_same():\n"
            "    assert True\n"
            "\n"
            "def test_removed_name():\n"
            "    assert True\n"
        )
    }
    head = {
        "tests/test_new.py": (
            "def test_same():\n"
            "    assert True\n"
            "\n"
            "def test_created_name():\n"
            "    assert True\n"
        )
    }

    delta = classify_sources(
        base,
        head,
        renames=[("tests/test_old.py", "tests/test_new.py")],
    )

    assert delta == {
        "created": ["tests/test_new.py::test_created_name"],
        "changed": ["tests/test_new.py::test_same"],
        "removed": ["tests/test_old.py::test_removed_name"],
    }
