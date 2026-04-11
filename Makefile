PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

.PHONY: install test demo demo-dry record web clean smoke

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

record:
	AGENTMES_AUTO_APPROVE=1 asciinema rec recordings/full-demo.cast \
		--command ".venv/bin/python -m agent_mes demo --dry-run --speed 1000" \
		--window-size 200x60 --overwrite --quiet
	cp recordings/full-demo.cast web/full-demo.cast

web:
	@cp recordings/full-demo.cast web/full-demo.cast 2>/dev/null || true
	@echo ""
	@echo "  AgentMES is live at: http://localhost:8080"
	@echo ""
	@echo "  Press Ctrl+C to stop the server."
	@echo ""
	@cd web && $(PY) -m http.server 8080

clean:
	rm -rf .demo/*.jsonl .demo/outputs/*.md __pycache__ */__pycache__ */*/__pycache__
	find . -name "*.pyc" -delete
