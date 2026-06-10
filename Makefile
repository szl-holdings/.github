# SZL .github governance repo — local helper targets.
.PHONY: doctrine doctrine-hook

doctrine: ## Run the local doctrine pre-check (advisory mirror of CI doctrine-check.yml)
	bash .github/scripts/doctrine_precommit.sh

doctrine-hook: ## Install the doctrine pre-commit git hook in this repo
	bash .github/scripts/install-doctrine-hook.sh
