.PHONY: all
.DEFAULT_GOAL := test

VERSION = $(shell grep "VERSION =" setup.py | cut -f3 -d" " | tr -d "'")
COMMIT = $(shell git rev-parse HEAD)

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

black: ## format the code
	black setup.py compose_dump tests

clean: clean-build clean-pyc clean-test  ## remove all artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

lint: ## check style with black and flake8
	black --check setup.py compose_dump tests
	flake8 deck_chores tests

test: ## run tests
	pytest tests

test-all: ## run tests against all supported versions
	tox

docs: ## generate Sphinx HTML documentation, including API docs
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	xdg-open docs/_build/html/index.html

release: lint test clean ## push to git repo 'origin' and release on PyPI
	git tag -f $(VERSION)
	git push origin master
	git push -f origin $(VERSION)
	python setup.py sdist bdist_wheel upload

dist: clean ## builds source and wheel package
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

install: clean ## install the package to the active Python's site-packages
	python setup.py install
