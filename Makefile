# Developer and release entry points for qluent-cli.
#
# Releasing is deliberately a single command: every step that used to be a
# remembered instruction in npm/RELEASING.md is now either a Make target here
# or a job in .github/workflows/qluent-cli-binaries.yml.

.PHONY: help test test-py test-npm version-check bump release binary smoke

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

test: test-py test-npm ## Run every test suite

test-py: ## Run the Python test suite
	uv run pytest -q

test-npm: ## Run the npm installer test suite
	cd npm && npm test

version-check: ## Verify every manifest agrees on one version
	python3 scripts/bump_version.py --check

binary: ## Build the standalone binary for this platform
	uv run --extra build python -m qluent_cli.build_binary

smoke: ## Build and smoke-test the binary end to end
	bash scripts/local_smoke_test.sh

bump: ## Bump every manifest to VERSION (make bump VERSION=0.1.19)
	@test -n "$(VERSION)" || (echo 'Error: VERSION is required, e.g. make bump VERSION=0.1.19'; exit 1)
	python3 scripts/bump_version.py $(VERSION)

release: ## Tag and push VERSION, triggering the build+release+npm workflow
	@test -n "$(VERSION)" || (echo 'Error: VERSION is required, e.g. make release VERSION=0.1.19'; exit 1)
	@test -z "$$(git status --porcelain)" || (echo 'Error: working tree is dirty; commit the version bump first'; exit 1)
	@test "$$(git rev-parse --abbrev-ref HEAD)" = main || (echo 'Error: release from main'; exit 1)
	@git fetch -q origin main && test -z "$$(git rev-list HEAD..origin/main)" \
		|| (echo 'Error: local main is behind origin/main; pull first'; exit 1)
	python3 scripts/bump_version.py --check $(VERSION)
	$(MAKE) test
	git tag -a v$(VERSION) -m 'Release $(VERSION)'
	git push origin v$(VERSION)
	@echo
	@echo 'Pushed v$(VERSION). CI now builds 5 binaries, signs them, cuts the'
	@echo 'GitHub release, then publishes @qluent/cli to npm. Watch it with:'
	@echo '  gh run watch $$(gh run list --workflow=qluent-cli-binaries.yml --limit 1 --json databaseId -q ".[0].databaseId")'

