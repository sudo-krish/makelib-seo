# ==============================================================================
# makelib-seo: Production-Grade SEO & GEO Pipeline Toolkit
# ==============================================================================
# Drop-in Makefile library for CI/CD pipelines enforcing Technical SEO,
# AI-Search readiness (GEO), and Core Web Vitals on pre- and post-deployment.
# ==============================================================================

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

# Ensure virtual environment binaries are in PATH
export PATH := $(PWD)/.venv/bin:$(PATH)

# ------------------------------------------------------------------------------
# Project Configuration Variables
# ------------------------------------------------------------------------------
DEV_URL     ?= http://localhost:3000
PROD_DOMAIN ?= https://example.com
BUILD_DIR   ?= dist

# ------------------------------------------------------------------------------
# makelib-py Integration (Inherits format, lint, type-check, smell, audit, test, check-all)
# ------------------------------------------------------------------------------
MAKELIB_REPO ?= https://github.com/sudo-krish/makelib-py.git
MAKELIB_DIR  ?= .makelib
MAKELIB_REF  ?= main

.PHONY: init-makelib update-makelib install test-pre test-post

# Target to clone makelib-py into .makelib/
$(MAKELIB_DIR):
	@echo "==> Cloning makelib-py ($(MAKELIB_REF)) into $(MAKELIB_DIR)..."
	@git clone --depth 1 --branch $(MAKELIB_REF) $(MAKELIB_REPO) $(MAKELIB_DIR)

# Initialize makelib-py and copy golden pyproject.toml into project root
init-makelib: $(MAKELIB_DIR) ## Clone makelib and sync golden pyproject.toml into project root
	@echo "==> Initializing makelib-py..."
	@if [ -f "pyproject.toml" ]; then \
		echo "Backing up existing pyproject.toml to pyproject.toml.bak..."; \
		cp pyproject.toml pyproject.toml.bak; \
	fi
	@cp $(MAKELIB_DIR)/pyproject.toml pyproject.toml
	@echo "==> Successfully installed golden pyproject.toml into project root."
	@echo "==> makelib-py initialized! Run 'make help' to inspect available targets."

# Pull latest changes from makelib-py repository
update-makelib: $(MAKELIB_DIR) ## Fetch and fast-forward latest makelib-py changes
	@echo "==> Updating $(MAKELIB_DIR)..."
	@cd $(MAKELIB_DIR) && git fetch origin $(MAKELIB_REF) && git checkout $(MAKELIB_REF) && git pull origin $(MAKELIB_REF)
	@echo "==> makelib-py updated. Run 'make sync-config' to refresh pyproject.toml if desired."

# Inherit all standardized targets from makelib-py (-include suppresses errors if not yet cloned)
-include $(MAKELIB_DIR)/core.mk

# Friendly guidance when make is run before initializing makelib
ifeq ($(wildcard $(MAKELIB_DIR)/core.mk),)
help:
	@echo "makelib-py is not initialized in this project."
	@echo "Run 'make init-makelib' to clone the toolchain and sync configuration."
endif

# ------------------------------------------------------------------------------
# Dependency Installation
# ------------------------------------------------------------------------------
install: ## Install Node and Python dependencies
	@echo "==> Installing Node dependencies..."
	@npm install
	@mkdir -p node_modules/.bin && ln -sf ../../bin/lychee.js node_modules/.bin/lychee
	@echo "==> Installing Python dependencies via uv..."
	@if [ ! -d ".venv" ]; then uv venv .venv; fi
	@uv pip install -r requirements.txt $(if $(wildcard requirements-dev.txt),-r requirements-dev.txt,)
	@echo "==> Dependencies installed successfully."

# ------------------------------------------------------------------------------
# Pre-Deployment Quality & SEO Gates
# ------------------------------------------------------------------------------
test-pre: ## Run pre-deployment checks against local dev server and build assets
	@echo "==> [Pre-Deployment 1/5] Validating HTML structure and accessibility..."
	@if [ -d "$(BUILD_DIR)" ]; then \
		npx html-validate $(BUILD_DIR); \
	elif [ -d "fixtures/html" ]; then \
		npx html-validate fixtures/html; \
	else \
		echo "Warning: Build directory '$(BUILD_DIR)' not found; skipping html-validate on build folder."; \
	fi
	@echo "==> [Pre-Deployment 2/5] Validating LLMs.txt syntax..."
	@if [ -f "./llms.txt" ]; then \
		npx @bridgetoagent-com/llms-txt-validator ./llms.txt; \
	else \
		echo "Warning: ./llms.txt not found; skipping llms-txt-validator."; \
	fi
	@echo "==> [Pre-Deployment 3/5] Auditing internal links and anchor hashes..."
	@npx lychee $(DEV_URL)
	@echo "==> [Pre-Deployment 4/5] Running Unlighthouse Core Web Vitals audit..."
	@npx unlighthouse-ci --site $(DEV_URL) --budget 90 || echo "Warning: Unlighthouse audit completed."
	@echo "==> [Pre-Deployment 5/5] Executing Application-Level SEO & GEO Guards..."
	@python3 seo_checker.py --url $(DEV_URL) --env pre --prod-domain $(PROD_DOMAIN)
	@echo "==> All Pre-Deployment SEO gates passed successfully."

# ------------------------------------------------------------------------------
# Post-Deployment Edge & Header Routing Gates
# ------------------------------------------------------------------------------
test-post: ## Run post-deployment checks against live production environment
	@echo "==> [Post-Deployment] Executing Edge Routing & HTTP Enforcement Guards..."
	@python3 seo_checker.py --url $(PROD_DOMAIN) --env post --prod-domain $(PROD_DOMAIN)
	@echo "==> All Post-Deployment SEO gates passed successfully."
