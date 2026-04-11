"""Baseline sanity test — proves pytest collection + venv work end-to-end."""
import agent_mes


def test_package_imports():
    assert agent_mes.__name__ == "agent_mes"
    assert agent_mes.__version__ == "0.1.0"
