"""Apply pull-request test delta labels when CI sets PR_TEST_DELTA_PATH."""

from __future__ import annotations

import json
import os
from pathlib import Path

import allure
import pytest


class PrDeltaPlugin:
    def __init__(self, labels: dict[str, str]):
        self.labels = labels

    @pytest.fixture(autouse=True)
    def pr_delta_label(self, request: pytest.FixtureRequest) -> None:
        kind = self.labels.get(_template_nodeid(request.node.nodeid))
        if kind is None:
            return
        listener = request.config.pluginmanager.get_plugin("allure_listener")
        if listener is None:
            return
        test_result = listener.allure_logger.get_test(None)
        if test_result is None:
            return
        allure.dynamic.label("pr_delta", kind)


def pytest_configure(config: pytest.Config) -> None:
    path = os.environ.get("PR_TEST_DELTA_PATH")
    if not path:
        return
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    config.pluginmanager.register(PrDeltaPlugin(_labels(payload)), "pr_delta")


def _labels(payload: dict) -> dict[str, str]:
    labels: dict[str, str] = {}
    for nodeid in payload.get("created") or []:
        labels[str(nodeid)] = "created"
    for nodeid in payload.get("changed") or []:
        labels[str(nodeid)] = "changed"
    return labels


def _template_nodeid(nodeid: str) -> str:
    return nodeid.split("[", 1)[0]
