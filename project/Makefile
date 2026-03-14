.PHONY: install test run clean bootstrap

install:
	pip install -r requirements.txt

test:
	python3 -m pytest tests/ -v

run:
	python3 -m src.cli run-all --team-id hackculture

bootstrap:
	python3 -m src.cli bootstrap

clean:
	rm -rf data/cache/* data/outputs/*
	rm -f data/parsed/*.json data/parsed/*.db

lint:
	python3 -m py_compile src/cli.py
	python3 -m py_compile src/pipelines/run_all.py
