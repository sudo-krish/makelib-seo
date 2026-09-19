#!/usr/bin/env python3
"""
seo_checker.py: Root CLI entrypoint for makelib-seo engine.
"""

from __future__ import annotations

import os
import sys

# Ensure src/ is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import src.seo_checker as engine

AuditReport = engine.AuditReport
Color = engine.Color
PostDeployAuditor = engine.PostDeployAuditor
PreDeployAuditor = engine.PreDeployAuditor
build_cli_parser = engine.build_cli_parser
log_fail = engine.log_fail
log_info = engine.log_info
log_pass = engine.log_pass
log_warn = engine.log_warn
main = engine.main

if __name__ == "__main__":
    main()
