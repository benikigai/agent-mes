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
	$(PY) -m agent_mes web

web-smoke:
	@$(PY) -m agent_mes web --port 8765 & \
		PID=$$!; \
		sleep 1.5; \
		curl -sf http://localhost:8765/api/state > /dev/null && echo "✓ /api/state OK" || (echo "✗ /api/state FAILED"; kill $$PID; exit 1); \
		curl -sf http://localhost:8765/ > /dev/null && echo "✓ / OK" || (echo "✗ / FAILED"; kill $$PID; exit 1); \
		curl -sf http://localhost:8765/replay > /dev/null && echo "✓ /replay OK" || (echo "✗ /replay FAILED"; kill $$PID; exit 1); \
		kill $$PID; \
		echo "✓ web-smoke passed"

clean:
	rm -rf .demo/*.jsonl .demo/outputs/*.md __pycache__ */__pycache__ */*/__pycache__
	find . -name "*.pyc" -delete
