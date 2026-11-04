# SZL .github governance repo — local helper targets.
.PHONY: verify doctrine doctrine-hook

PYTHON ?= python3

verify: ## Validate the pinned toolchain, dependency declarations, and test-to-workflow coverage
	$(PYTHON) -I -P .github/scripts/verify_repository_contract.py

doctrine: ## Run the local doctrine pre-check (advisory mirror of CI doctrine-check.yml)
	bash .github/scripts/doctrine_precommit.sh

doctrine-hook: ## Install the doctrine pre-commit git hook in this repo
	bash .github/scripts/install-doctrine-hook.sh
