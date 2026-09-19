# ==============================================================================
# makelib-seo: Production-Grade SEO & GEO Pipeline Toolkit
# ==============================================================================
# Drop-in Makefile library for CI/CD pipelines enforcing Technical SEO,
# AI-Search readiness (GEO), and Core Web Vitals on pre- and post-deployment.
# ==============================================================================

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

# Ensure virtual environment and local user binaries are in PATH
export PATH := $(PWD)/.venv/bin:$(HOME)/.local/bin:$(PATH)

# ------------------------------------------------------------------------------
# Project Configuration Variables
# ------------------------------------------------------------------------------
DEV_URL     ?= http://localhost:3000
PROD_DOMAIN ?= https://example.com
BUILD_DIR   ?= dist
SRC_DIR     ?= src
TEST_DIR    ?= tests

# ------------------------------------------------------------------------------
# makelib-py Integration (Inherits format, lint, type-check, smell, audit, test, check-all)
# ------------------------------------------------------------------------------
MAKELIB_REPO ?= https://github.com/sudo-krish/makelib-py.git
MAKELIB_DIR  ?= .makelib
MAKELIB_REF  ?= main

.PHONY: init-makelib update-makelib install

# Target to clone makelib-py into .makelib/
$(MAKELIB_DIR):
	@echo "==> Cloning makelib-py ($(MAKELIB_REF)) into $(MAKELIB_DIR)..."
	@git clone --depth 1 --branch $(MAKELIB_REF) $(MAKELIB_REPO) $(MAKELIB_DIR)

# Initialize makelib-py and bootstrap pyproject.toml if not already present
init-makelib: $(MAKELIB_DIR) ## Clone makelib and bootstrap pyproject.toml if not present
	@echo "==> Initializing makelib-py..."
	@if [ ! -f "pyproject.toml" ]; then \
		cp $(MAKELIB_DIR)/pyproject.toml pyproject.toml; \
		echo "==> Installed golden pyproject.toml into project root."; \
	else \
		echo "==> Existing pyproject.toml detected; preserving project metadata."; \
	fi
	@echo "==> makelib-py initialized! Run 'make help' to inspect available targets."

# Pull latest changes from makelib-py repository
update-makelib: $(MAKELIB_DIR) ## Fetch and fast-forward latest makelib-py changes
	@echo "==> Updating $(MAKELIB_DIR)..."
	@cd $(MAKELIB_DIR) && git fetch origin $(MAKELIB_REF) && git checkout $(MAKELIB_REF) && git pull origin $(MAKELIB_REF)
	@echo "==> makelib-py updated. Run 'make sync-config' to refresh pyproject.toml if desired."

# Use makelib-py golden pyproject.toml for all linting, type-checking, and AST scanning
CONFIG_FILE ?= $(MAKELIB_DIR)/pyproject.toml
RUFF        ?= ruff --config $(CONFIG_FILE)
MYPY        ?= mypy $(if $(wildcard .venv/bin/python),--python-executable .venv/bin/python,)
PIP_AUDIT_FLAGS ?= $(if $(wildcard requirements.txt),-r requirements.txt,.) --ignore-vuln PYSEC-2026-3740


# Include makelib-seo Core Standardized SEO Targets
include core.mk

# Inherit all standardized Python targets from makelib-py (-include suppresses errors if not yet cloned)
-include $(MAKELIB_DIR)/core.mk

# Friendly guidance when make is run before initializing makelib
ifeq ($(wildcard $(MAKELIB_DIR)/core.mk),)
help: help-seo
	@echo ""
	@echo "makelib-py toolchain is not yet cloned in $(MAKELIB_DIR)."
	@echo "Run 'make init-makelib' to inherit lint, type-check, test, and quality gates."
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
	@uv pip install -r requirements.txt $(if $(wildcard requirements-dev.txt),-r requirements-dev.txt,) \
		$(if $(wildcard $(MAKELIB_DIR)/requirements-dev.txt),-r $(MAKELIB_DIR)/requirements-dev.txt,)
	@echo "==> Dependencies installed successfully."
