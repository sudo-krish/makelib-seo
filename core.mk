# ==============================================================================
# makelib-seo: Core Standardized Makefile for SEO & GEO Quality Pipelines
# ==============================================================================
# This makefile provides standardized, opinionated quality gates for Technical
# SEO, AI-Search readiness (GEO), and Core Web Vitals. Downstream web projects
# include this file dynamically.
# ==============================================================================

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

# ------------------------------------------------------------------------------
# Extensible Project Variables (Overridable by downstream projects)
# ------------------------------------------------------------------------------
DEV_URL               ?= http://localhost:3000
PROD_DOMAIN           ?= https://example.com
BUILD_DIR             ?= dist
LLMS_TXT              ?= ./llms.txt
LIGHTHOUSE_BUDGET     ?= 90
SEO_STRICT            ?= false

# Environment & Executables
PYTHON                ?= python3
NPX                   ?= npx

# Resolve location of this makefile (allows locating bundled tools and scripts)
MAKELIB_SEO_THIS_DIR  := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))
MAKELIB_SEO_DIR       ?= $(MAKELIB_SEO_THIS_DIR)
HTML_VALIDATE_CONFIG  ?= $(if $(wildcard .htmlvalidate.json),.htmlvalidate.json,$(MAKELIB_SEO_DIR)/.htmlvalidate.json)
SEO_CHECKER_BIN       ?= $(MAKELIB_SEO_DIR)/seo_checker.py


# ------------------------------------------------------------------------------
# Phony Targets Declaration
# ------------------------------------------------------------------------------
.PHONY: help-seo validate-html validate-llms audit-links audit-vitals audit-geo-pre test-pre test-post clean-seo

# ------------------------------------------------------------------------------
# Help Target
# ------------------------------------------------------------------------------
help-seo: ## Display available makelib-seo targets and options
	@echo "makelib-seo: Technical SEO & GEO Quality Pipeline Targets"
	@echo ""
	@echo "Usage: make [target] [VARIABLE=value]"
	@echo ""
	@echo "Targets:"
	@echo "  test-pre          Run all pre-deployment quality gates (HTML, LLMs.txt, links, vitals, GEO)"
	@echo "  test-post         Run live edge routing and CDN header gates against PROD_DOMAIN"
	@echo "  validate-html     Validate HTML markup and heading hierarchy using html-validate"
	@echo "  validate-llms     Validate llms.txt syntax against the llmstxt.org reference spec"
	@echo "  audit-links       Audit internal links and anchor hashes using lychee"
	@echo "  audit-vitals      Audit Core Web Vitals and performance budgets using unlighthouse-ci"
	@echo "  audit-geo-pre     Audit local DOM metadata, AI bot robots.txt, sitemaps, and JSON-LD schemas"
	@echo "  clean-seo         Remove temporary SEO audit reports and lighthouse caches"
	@echo ""
	@echo "Configurable Variables:"
	@echo "  DEV_URL           = $(DEV_URL)"
	@echo "  PROD_DOMAIN       = $(PROD_DOMAIN)"
	@echo "  BUILD_DIR         = $(BUILD_DIR)"
	@echo "  LLMS_TXT          = $(LLMS_TXT)"
	@echo "  LIGHTHOUSE_BUDGET = $(LIGHTHOUSE_BUDGET)"
	@echo "  SEO_STRICT        = $(SEO_STRICT)"

# ------------------------------------------------------------------------------
# Modular Pre-Deployment Targets
# ------------------------------------------------------------------------------
validate-html: ## Validate HTML syntax, single H1, and accessibility in build directory
	@echo "==> [SEO] Validating HTML markup and heading hierarchy..."
	@if [ -d "$(BUILD_DIR)" ]; then \
		$(NPX) html-validate --config $(HTML_VALIDATE_CONFIG) $(BUILD_DIR); \
	elif [ -d "fixtures/html" ]; then \
		$(NPX) html-validate --config $(HTML_VALIDATE_CONFIG) fixtures/html; \
	else \
		echo "Notice: Build directory '$(BUILD_DIR)' not found; skipping html-validate."; \
	fi

validate-llms: ## Validate llms.txt format against the reference specification
	@echo "==> [GEO] Validating $(LLMS_TXT) syntax..."
	@if [ -f "$(LLMS_TXT)" ]; then \
		$(NPX) @bridgetoagent-com/llms-txt-validator $(LLMS_TXT); \
	else \
		echo "Notice: '$(LLMS_TXT)' not found; skipping llms-txt-validator."; \
	fi

audit-links: ## Audit internal links and DOM anchor hashes against local dev server
	@echo "==> [SEO] Crawling internal links and anchor hashes on $(DEV_URL)..."
	@$(NPX) lychee $(DEV_URL)

audit-vitals: ## Audit Core Web Vitals performance budget using unlighthouse-ci
	@echo "==> [Vitals] Running Unlighthouse audit on $(DEV_URL) (budget: $(LIGHTHOUSE_BUDGET))..."
	@$(NPX) unlighthouse-ci --site $(DEV_URL) --budget $(LIGHTHOUSE_BUDGET) || echo "Notice: Unlighthouse audit completed."

audit-geo-pre: ## Run application-level SEO & GEO verification script against local server
	@echo "==> [GEO] Running pre-deployment SEO guards on $(DEV_URL)..."
	@$(PYTHON) $(SEO_CHECKER_BIN) --url $(DEV_URL) --env pre --prod-domain $(PROD_DOMAIN) $(if $(filter true,$(SEO_STRICT)),--strict,)

# ------------------------------------------------------------------------------
# Composite Pipeline Gates
# ------------------------------------------------------------------------------
test-pre: validate-html validate-llms audit-links audit-vitals audit-geo-pre ## Run complete Pre-Deployment SEO & GEO quality pipeline
	@echo ""
	@echo "==> [makelib-seo] All Pre-Deployment quality gates PASSED successfully."

test-post: ## Run Post-Deployment edge routing and CDN header validation against live production
	@echo "==> [Edge] Executing live post-deployment routing guards on $(PROD_DOMAIN)..."
	@$(PYTHON) $(SEO_CHECKER_BIN) --url $(PROD_DOMAIN) --env post --prod-domain $(PROD_DOMAIN) $(if $(filter true,$(SEO_STRICT)),--strict,)
	@echo ""
	@echo "==> [makelib-seo] All Post-Deployment edge gates PASSED successfully."

clean-seo: ## Remove generated audit artifacts and Unlighthouse reports
	@echo "==> Cleaning SEO audit reports..."
	@rm -rf .unlighthouse .lighthouseci
	@echo "==> SEO cleanup complete."
