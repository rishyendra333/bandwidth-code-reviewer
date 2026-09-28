export PYTHONPATH := $(CURDIR)/src:$(CURDIR)

UV ?= uv
export TERRAFORM ?= terraform
MODE ?= local

.PHONY: setup setup-local test lint lint-python infra-check dev build plan deploy bootstrap bootstrap-apply outputs e2e bedrock-smoke
setup:
	$(UV) run python -m scripts.setup
setup-local:
	$(UV) run python -m scripts.setup --local-only
test:
	$(UV) run python -m pytest
lint: lint-python infra-check
lint-python:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy
infra-check:
	$(TERRAFORM) fmt -check -recursive infra
	$(TERRAFORM) -chdir=infra/bootstrap init -backend=false -input=false -lockfile=readonly
	$(TERRAFORM) -chdir=infra/bootstrap validate
	$(TERRAFORM) -chdir=infra/dev init -backend=false -input=false -lockfile=readonly
	$(TERRAFORM) -chdir=infra/dev validate
dev:
	$(UV) run python -m reviewer.local
build:
	$(UV) run python -m scripts.build_lambda
bootstrap:
	$(UV) run python -m scripts.deploy bootstrap-plan
bootstrap-apply:
	$(UV) run python -m scripts.deploy bootstrap-apply
plan:
	$(UV) run python -m scripts.deploy plan
deploy:
	$(UV) run python -m scripts.deploy apply
outputs:
	$(UV) run python -m scripts.deploy outputs
e2e:
	$(UV) run python -m scripts.e2e --mode $(MODE)
bedrock-smoke:
	$(UV) run python -m scripts.bedrock_smoke

infra-test:
	$(UV) run python -m scripts.test_infra
