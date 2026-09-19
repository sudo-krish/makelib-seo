# ==============================================================================
# makelib-seo: Downstream Makefile Integration Template
# ==============================================================================
# Paste this snippet into your downstream project's Makefile to bootstrap
# makelib-seo and enforce Technical SEO, GEO, and Web Vitals in your CI/CD pipeline.
# ==============================================================================

# Repository location and local target directory
MAKELIB_SEO_REPO ?= https://github.com/sudo-krish/makelib-seo.git
MAKELIB_SEO_DIR  ?= .makelib-seo
MAKELIB_SEO_REF  ?= main

# Project-specific overrides (uncomment and adjust as needed)
# DEV_URL           ?= http://localhost:3000
# PROD_DOMAIN       ?= https://example.com
# BUILD_DIR         ?= dist
# LLMS_TXT          ?= ./llms.txt
# LIGHTHOUSE_BUDGET ?= 90
# SEO_STRICT        ?= false

.PHONY: init-makelib-seo update-makelib-seo

# Target to clone makelib-seo into .makelib-seo/
$(MAKELIB_SEO_DIR):
	@echo "==> Cloning makelib-seo ($(MAKELIB_SEO_REF)) into $(MAKELIB_SEO_DIR)..."
	@git clone --depth 1 --branch $(MAKELIB_SEO_REF) $(MAKELIB_SEO_REPO) $(MAKELIB_SEO_DIR)

# Initialize makelib-seo and sync default validator configurations
init-makelib-seo: $(MAKELIB_SEO_DIR) ## Clone makelib-seo and sync validator configs into project root
	@echo "==> Initializing makelib-seo..."
	@if [ ! -f ".htmlvalidate.json" ]; then \
		cp $(MAKELIB_SEO_DIR)/.htmlvalidate.json .htmlvalidate.json; \
		echo "==> Copied default .htmlvalidate.json into project root."; \
	fi
	@echo "==> makelib-seo initialized! Run 'make help-seo' to inspect available SEO targets."

# Pull latest changes from makelib-seo repository
update-makelib-seo: $(MAKELIB_SEO_DIR) ## Fetch and fast-forward latest makelib-seo changes
	@echo "==> Updating $(MAKELIB_SEO_DIR)..."
	@cd $(MAKELIB_SEO_DIR) && git fetch origin $(MAKELIB_SEO_REF) && git checkout $(MAKELIB_SEO_REF) && git pull origin $(MAKELIB_SEO_REF)
	@echo "==> makelib-seo updated successfully."

# Inherit all standardized SEO targets (-include suppresses errors if not yet cloned)
-include $(MAKELIB_SEO_DIR)/core.mk

# Friendly guidance when make is run before initializing makelib-seo
ifeq ($(wildcard $(MAKELIB_SEO_DIR)/core.mk),)
help-seo:
	@echo "makelib-seo is not initialized in this project."
	@echo "Run 'make init-makelib-seo' to clone the toolchain and sync configuration."
endif

# ==============================================================================
# Downstream CI/CD Pipeline Steps (GitHub Actions Reference)
# ==============================================================================
# Add these steps into your downstream repository workflows:
#
# 1. Pre-Deployment Step (Run against preview server on Pull Requests):
#    - name: Bootstrap makelib-seo
#      run: make init-makelib-seo
#    - name: Run Pre-Deployment SEO & GEO Gates
#      run: make test-pre DEV_URL=http://localhost:3000 PROD_DOMAIN=https://example.com
#
# 2. Post-Deployment Step (Run against live production after deployment):
#    - name: Bootstrap makelib-seo
#      run: make init-makelib-seo
#    - name: Run Live Edge Routing & CDN Header Guards
#      run: make test-post PROD_DOMAIN=https://example.com
# ==============================================================================
