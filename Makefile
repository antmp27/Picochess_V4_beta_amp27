.PHONY: help install test lint format clean dev-install

help:
	@echo "Available commands:"
	@echo "  install     - Install dependencies"
	@echo "  dev-install - Install development dependencies"
	@echo "  test        - Run tests"
	@echo "  lint        - Run linting"
	@echo "  format      - Format code with black"
	@echo "  clean       - Clean build artifacts"
	@echo "  run         - Run PicoChess"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pip install -r test-requirements.txt

test:
	pytest tests/ -v

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

format:
	black .

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/

run:
	python picochess.py