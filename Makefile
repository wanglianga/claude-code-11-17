.PHONY: install init-db seed run test demo clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

init-db:
	.venv/bin/python -m app.cli init-db

seed:
	.venv/bin/python -m app.cli seed

run:
	.venv/bin/python -m app.cli run --port 8000

test:
	.venv/bin/python -m pytest

demo:
	bash scripts/demo.sh

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache
