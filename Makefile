PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

.PHONY: install test demo clean smoke

install:
	$(PIP) install -e ".[dev]"

test:
	AGENTMES_AUTO_APPROVE=1 $(PYTEST) -x

smoke:
	AGENTMES_AUTO_APPROVE=1 $(PYTEST) tests/test_smoke.py -x

demo:
	$(PY) -m agent_mes demo

demo-dry:
	AGENTMES_AUTO_APPROVE=1 $(PY) -m agent_mes demo --dry-run

clean:
	rm -rf .demo/*.jsonl .demo/outputs/*.md __pycache__ */__pycache__ */*/__pycache__
	find . -name "*.pyc" -delete
