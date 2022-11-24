import pytest


@pytest.fixture
def gh_actions_env(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    yield
