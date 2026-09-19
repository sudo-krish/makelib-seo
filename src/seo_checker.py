#!/usr/bin/env python3
"""
seo_checker.py: Production-Grade SEO & GEO Pipeline Validation Toolkit.

Enforces Technical SEO, AI-Search Readiness (GEO), and HTTP/Edge integrity
across Pre-Deployment (local dev server) and Post-Deployment (live edge CDN)
environments. Halts CI/CD pipelines with exit code 1 upon critical failures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import textstat
from bs4 import BeautifulSoup, Tag
from lxml import etree

__all__ = [
    "AuditReport",
    "Color",
    "PostDeployAuditor",
    "PreDeployAuditor",
    "build_cli_parser",
    "log_fail",
    "log_info",
    "log_pass",
    "log_warn",
    "main",
]


# ------------------------------------------------------------------------------
# Terminal Coloring & Formatting
# ------------------------------------------------------------------------------
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


def log_pass(msg: str) -> None:
    print(f"{Color.GREEN}[PASS]{Color.RESET} {msg}")


def log_fail(msg: str) -> None:
    print(f"{Color.RED}[FAIL]{Color.RESET} {msg}", file=sys.stderr)


def log_warn(msg: str) -> None:
    print(f"{Color.YELLOW}[WARN]{Color.RESET} {msg}")


def log_info(msg: str) -> None:
    print(f"{Color.CYAN}[INFO]{Color.RESET} {msg}")


# ------------------------------------------------------------------------------
# Audit Result Tracking
# ------------------------------------------------------------------------------
@dataclass
class AuditReport:
    env: str
    target_url: str
    prod_domain: str
    strict: bool = False
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_pass(self, check_name: str, detail: str = "") -> None:
        msg = f"{check_name}: {detail}" if detail else check_name
        self.passed.append(msg)
        log_pass(msg)

    def add_fail(self, check_name: str, reason: str) -> None:
        msg = f"{check_name} -> {reason}"
        self.failed.append(msg)
        log_fail(msg)

    def add_warn(self, check_name: str, reason: str) -> None:
        msg = f"{check_name} -> {reason}"
        self.warnings.append(msg)
        log_warn(msg)

    @property
    def has_failed(self) -> bool:
        if self.failed:
            return True
        if self.strict and self.warnings:
            return True
        return False

    def print_summary(self) -> None:
        print("\n" + "=" * 78)
        print(f"{Color.BOLD}SEO & GEO AUDIT SUMMARY [{self.env.upper()}]{Color.RESET}")
        print(f"Target: {self.target_url} | Expected Prod: {self.prod_domain}")
        print("=" * 78)
        print(f"  Passed:   {Color.GREEN}{len(self.passed)}{Color.RESET}")
        print(f"  Failed:   {Color.RED}{len(self.failed)}{Color.RESET}")
        print(f"  Warnings: {Color.YELLOW}{len(self.warnings)}{Color.RESET}")
        print("=" * 78)

        if self.failed:
            print(f"\n{Color.RED}{Color.BOLD}CRITICAL FAILURES DETECTED:{Color.RESET}")
            for f in self.failed:
                print(f"  ❌ {f}")

        if self.warnings:
            print(f"\n{Color.YELLOW}{Color.BOLD}WARNINGS (GEO / Content Optimization):{Color.RESET}")
            for w in self.warnings:
                print(f"  ⚠️ {w}")

        if not self.has_failed:
            print(f"\n{Color.GREEN}{Color.BOLD}SUCCESS: All SEO & GEO pipeline gates passed!{Color.RESET}\n")
        else:
            print(
                f"\n{Color.RED}{Color.BOLD}FAILURE: CI/CD pipeline halted due to SEO policy violations.{Color.RESET}\n"
            )


# ------------------------------------------------------------------------------
# Pre-Deployment Audit Engine (Tested against localhost dev server)
# ------------------------------------------------------------------------------
class PreDeployAuditor:
    """Audits local application DOM, metadata, sitemaps, robots, and content."""

    def __init__(
        self,
        url: str,
        prod_domain: str,
        report: AuditReport,
        timeout: int = 10,
        session: requests.Session | None = None,
    ) -> None:
        self.url = url
        self.prod_domain = prod_domain.rstrip("/")
        self.report = report
        self.timeout = timeout
        self.session = session or requests.Session()

    def run_all(self) -> None:
        log_info(f"Starting Pre-Deployment SEO Audit on: {self.url}")

        # 1. Fetch main DOM
        html_content, status_code = self._fetch_dom()
        if html_content is None:
            self.report.add_fail("DOM Fetch", f"Unable to fetch {self.url} (Status: {status_code})")
            return

        soup = BeautifulSoup(html_content, "html.parser")

        # 2. DOM & Meta Checks
        self.check_accidental_noindex(soup)
        self.check_canonical_url(soup)
        self.check_html_meta_integrity(soup)

        # 3. Server-level files: robots.txt and sitemap.xml
        self.check_robots_txt_ai_bots()
        self.check_sitemap_xml()

        # 4. E-E-A-T & JSON-LD Structure
        self.check_json_ld_schemas(soup)

        # 5. Content Readability & Experience Markers
        self.check_content_readability(soup)
        self.check_experience_markers(soup)

    def _fetch_dom(self) -> tuple[str | None, int]:
        try:
            resp = self.session.get(self.url, timeout=self.timeout)
            if resp.status_code >= 400:
                return None, resp.status_code
            return resp.text, resp.status_code
        except Exception as e:
            log_fail(f"Network error connecting to {self.url}: {e}")
            return None, 0

    def check_accidental_noindex(self, soup: BeautifulSoup) -> None:
        """Fails if <meta name="robots" content="noindex"> is present in head."""
        check = "Accidental Noindex Guard"
        meta_robots = soup.find_all("meta", attrs={"name": re.compile(r"^robots$", re.I)})
        for meta in meta_robots:
            content = meta.get("content", "")
            if "noindex" in content.lower():
                self.report.add_fail(
                    check,
                    f'Discovered <meta name="robots" content="{content}"> in <head>. '
                    "Staging noindex must NOT merge into production.",
                )
                return

        self.report.add_pass(check, "No accidental noindex meta tags detected in DOM.")

    def check_canonical_url(self, soup: BeautifulSoup) -> None:
        """Extracts <link rel="canonical"> and asserts href starts with prod-domain."""
        check = "Canonical URL Generation"
        canonical_link = soup.find("link", attrs={"rel": lambda r: r and "canonical" in r.lower()})
        if not isinstance(canonical_link, Tag) or not canonical_link.get("href"):
            self.report.add_fail(check, 'Missing <link rel="canonical"> element in <head>.')
            return

        raw_href = canonical_link.get("href", "")
        href = str(raw_href[0] if isinstance(raw_href, list) else raw_href).strip()
        if not href.startswith(self.prod_domain):
            self.report.add_fail(
                check,
                f'Canonical href "{href}" does not start with production domain "{self.prod_domain}". '
                "Staging/dev URLs must not leak into canonical tags.",
            )
            return

        self.report.add_pass(check, f'Valid production canonical detected: "{href}"')

    def check_html_meta_integrity(self, soup: BeautifulSoup) -> None:
        """Validates Title, Meta Description, Headings, Viewport, and Alt tags."""
        check_base = "HTML & Meta Integrity"

        # Title (30 - 60 chars)
        title_tag = soup.find("title")
        if not isinstance(title_tag, Tag) or not title_tag.string:
            self.report.add_fail(f"{check_base}: Title", "Page is missing a <title> tag.")
        else:
            title_text = str(title_tag.string).strip()
            title_len = len(title_text)
            if 30 <= title_len <= 60:
                self.report.add_pass(
                    f"{check_base}: Title", f'Title length optimal ({title_len} chars): "{title_text}"'
                )
            else:
                self.report.add_fail(
                    f"{check_base}: Title",
                    f'Title length is {title_len} chars (expected 30-60 chars): "{title_text}"',
                )

        # Meta Description (120 - 160 chars)
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if not isinstance(meta_desc, Tag) or not meta_desc.get("content"):
            self.report.add_fail(f"{check_base}: Meta Description", 'Page is missing <meta name="description">.')
        else:
            raw_desc = meta_desc.get("content", "")
            desc_text = str(raw_desc[0] if isinstance(raw_desc, list) else raw_desc).strip()
            desc_len = len(desc_text)
            if 120 <= desc_len <= 160:
                self.report.add_pass(f"{check_base}: Meta Description", f"Length optimal ({desc_len} chars).")
            else:
                self.report.add_fail(
                    f"{check_base}: Meta Description",
                    f"Description length is {desc_len} chars (expected 120-160 chars).",
                )

        # Heading Structure: Exactly one <h1>, no skipped levels (e.g. h2 -> h4)
        h1_tags = soup.find_all("h1")
        if len(h1_tags) == 0:
            self.report.add_fail(f"{check_base}: Headings", "Page is missing an <h1> heading.")
        elif len(h1_tags) > 1:
            self.report.add_fail(
                f"{check_base}: Headings", f"Page contains {len(h1_tags)} <h1> tags (expected exactly 1)."
            )
        else:
            self.report.add_pass(f"{check_base}: Headings", "Single <h1> present.")

        # Heading hierarchy skip check
        all_headings = soup.find_all(re.compile(r"^h[1-6]$", re.I))
        levels = [int(h.name[1]) for h in all_headings if isinstance(h, Tag)]
        hierarchy_ok = True
        for i in range(len(levels) - 1):
            curr_lvl = levels[i]
            next_lvl = levels[i + 1]
            if next_lvl > curr_lvl + 1:
                self.report.add_fail(
                    f"{check_base}: Headings",
                    f"Heading level skipped from <h{curr_lvl}> directly to <h{next_lvl}>.",
                )
                hierarchy_ok = False
                break
        if hierarchy_ok and all_headings:
            self.report.add_pass(f"{check_base}: Headings Hierarchy", "No heading levels skipped.")

        # Mobile Viewport
        viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
        if not isinstance(viewport, Tag) or not viewport.get("content"):
            self.report.add_fail(f"{check_base}: Viewport", 'Missing <meta name="viewport"> tag.')
        else:
            raw_vp = viewport.get("content", "")
            vp_content = str(raw_vp[0] if isinstance(raw_vp, list) else raw_vp).lower()
            if "width=device-width" in vp_content and "initial-scale=1" in vp_content:
                self.report.add_pass(f"{check_base}: Viewport", "Valid mobile viewport configured.")
            else:
                self.report.add_fail(
                    f"{check_base}: Viewport",
                    f'Invalid viewport content: "{vp_content}". Must include width=device-width and initial-scale=1.',
                )

        # Accessibility: <html lang="..."> and img alt tags
        html_tag = soup.find("html")
        if not isinstance(html_tag, Tag) or not html_tag.get("lang"):
            self.report.add_fail(f"{check_base}: Accessibility", '<html lang="..."> attribute is missing or empty.')
        else:
            lang_val = html_tag.get("lang")
            self.report.add_pass(f"{check_base}: Accessibility", f'Language set to: "{lang_val}".')

        images = soup.find_all("img")
        missing_alt = [img for img in images if img.get("alt") is None]
        if missing_alt:
            self.report.add_fail(
                f"{check_base}: Accessibility",
                f"{len(missing_alt)} of {len(images)} <img> elements lack an alt attribute.",
            )
        elif images:
            self.report.add_pass(f"{check_base}: Accessibility", f"All {len(images)} images contain alt attributes.")

    def check_robots_txt_ai_bots(self) -> None:
        """Fetches /robots.txt and verifies AI bots do not have Disallow rules."""
        check = "Robots.txt AI Bot Clearance"
        robots_url = urljoin(self.url, "/robots.txt")
        try:
            resp = self.session.get(robots_url, timeout=self.timeout)
            if resp.status_code == 404:
                self.report.add_pass(check, "robots.txt returns 404 (all bots permitted by default).")
                return
            if resp.status_code >= 400:
                self.report.add_fail(check, f"Failed fetching robots.txt (HTTP {resp.status_code}).")
                return
            content = resp.text
        except Exception as e:
            self.report.add_fail(check, f"Network error fetching robots.txt: {e}")
            return

        target_bots = {"gptbot", "claudebot", "perplexitybot", "google-extended"}
        current_agents: set[str] = set()
        disallowed_bots: set[str] = set()

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if ":" not in line:
                continue

            directive, val = [p.strip() for p in line.split(":", 1)]
            directive = directive.lower()
            val = val.strip()

            if directive == "user-agent":
                agent_val = val.lower()
                if not current_agents or directive == "user-agent":
                    # If this immediately follows another User-agent, group them
                    pass
                current_agents.add(agent_val)
            elif directive == "disallow":
                # If there's a non-empty disallow path (e.g. '/' or '/some-path')
                if val != "":
                    for agent in current_agents:
                        if agent in target_bots:
                            disallowed_bots.add(agent)
                        elif agent == "*":
                            # Note: wildcard disallow affects AI bots unless overridden
                            disallowed_bots.add(f"* (affects {', '.join(target_bots)})")
                current_agents = set()
            else:
                # Other directive resets current user-agents
                current_agents = set()

        if disallowed_bots:
            self.report.add_fail(
                check,
                f"Disallow directive detected for AI bot(s): {', '.join(sorted(disallowed_bots))}. "
                "AI search agents must be permitted.",
            )
        else:
            self.report.add_pass(check, "GPTBot, ClaudeBot, PerplexityBot, and Google-Extended are cleared.")

    def check_sitemap_xml(self) -> None:
        """Fetches /sitemap.xml and asserts all URLs start with --prod-domain."""
        check = "Sitemap XML Validity"
        sitemap_url = urljoin(self.url, "/sitemap.xml")
        try:
            resp = self.session.get(sitemap_url, timeout=self.timeout)
            if resp.status_code >= 400:
                self.report.add_fail(check, f"Failed fetching {sitemap_url} (HTTP {resp.status_code}).")
                return
            xml_bytes = resp.content
        except Exception as e:
            self.report.add_fail(check, f"Network error fetching sitemap.xml: {e}")
            return

        try:
            root = etree.fromstring(xml_bytes)
        except Exception as e:
            self.report.add_fail(check, f"XML Parsing error in sitemap.xml: {e}")
            return

        # Extract all <loc> text regardless of namespace
        locs = root.xpath("//*[local-name()='loc']")
        if not locs:
            self.report.add_fail(check, "sitemap.xml contains 0 <loc> URLs.")
            return

        invalid_urls: list[str] = []
        for loc in locs:
            url_text = (loc.text or "").strip()
            if not url_text.startswith(self.prod_domain):
                invalid_urls.append(url_text)

        if invalid_urls:
            sample = invalid_urls[:3]
            self.report.add_fail(
                check,
                f"{len(invalid_urls)} URL(s) in sitemap.xml do not start with {self.prod_domain}. Sample: {sample}",
            )
        else:
            self.report.add_pass(check, f"All {len(locs)} URLs in sitemap use the production domain prefix.")

    def _parse_json_ld_scripts(self, soup: BeautifulSoup) -> list[dict[str, Any]] | None:
        check = "Schema.org JSON-LD"
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        if not scripts:
            self.report.add_fail(check, 'No <script type="application/ld+json"> blocks found in DOM.')
            return None

        schemas: list[dict[str, Any]] = []
        for s in scripts:
            try:
                data = json.loads(s.string or "{}")
                if isinstance(data, list):
                    schemas.extend(data)
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        schemas.extend(data["@graph"])
                    else:
                        schemas.append(data)
            except Exception as e:
                self.report.add_fail(check, f"Invalid JSON syntax in application/ld+json script: {e}")
                return None
        return schemas

    @staticmethod
    def _extract_nodes(node: Any, found_types: set[str], person_objects: list[dict[str, Any]]) -> None:
        if isinstance(node, dict):
            node_type = node.get("@type")
            if isinstance(node_type, str):
                found_types.add(node_type)
                if node_type == "Person":
                    person_objects.append(node)
            elif isinstance(node_type, list):
                for t in node_type:
                    if isinstance(t, str):
                        found_types.add(t)
                        if t == "Person":
                            person_objects.append(node)
            for v in node.values():
                PreDeployAuditor._extract_nodes(v, found_types, person_objects)
        elif isinstance(node, list):
            for item in node:
                PreDeployAuditor._extract_nodes(item, found_types, person_objects)

    @staticmethod
    def _is_valid_person_sameas(person_objects: list[dict[str, Any]]) -> bool:
        for p in person_objects:
            same_as = p.get("sameAs")
            if isinstance(same_as, list) and len(same_as) > 0:
                if all(isinstance(u, str) and (u.startswith("http://") or u.startswith("https://")) for u in same_as):
                    return True
        return False

    def check_json_ld_schemas(self, soup: BeautifulSoup) -> None:
        """Validates Article, Organization, and Person (with sameAs) JSON-LD schemas."""
        check = "Schema.org JSON-LD"
        schemas = self._parse_json_ld_scripts(soup)
        if schemas is None:
            return

        found_types: set[str] = set()
        person_objects: list[dict[str, Any]] = []
        for sc in schemas:
            self._extract_nodes(sc, found_types, person_objects)

        required_types = {"Article", "Organization", "Person"}
        missing = required_types - found_types
        if missing:
            self.report.add_fail(
                check,
                f"Missing required Schema.org types: {', '.join(sorted(missing))}. "
                f"Found: {', '.join(sorted(found_types)) if found_types else 'None'}",
            )
            return

        if not self._is_valid_person_sameas(person_objects):
            self.report.add_fail(
                check,
                "Person schema exists but lacks a valid, populated 'sameAs' array of social proof URLs (LinkedIn, X).",
            )
            return

        self.report.add_pass(
            check,
            "Article, Organization, and Person (with verified sameAs social proof) schemas present.",
        )

    def check_content_readability(self, soup: BeautifulSoup) -> None:
        """Calculates Flesch Reading Ease score on <p> tag text; warns if < 40."""
        check = "Content Readability Scoring"
        paragraphs = [p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()]
        full_text = " ".join(paragraphs)

        if not full_text:
            self.report.add_warn(check, "No paragraph content (<p>) found on page to analyze.")
            return

        try:
            score = textstat.flesch_reading_ease(full_text)
            if score < 40:
                self.report.add_warn(
                    check,
                    f"Flesch Reading Ease score is {score:.1f} (< 40). "
                    "Content is overly complex and may reduce citation likelihood by LLMs.",
                )
            else:
                self.report.add_pass(check, f"Flesch Reading Ease score is {score:.1f} (>= 40, accessible for LLMs).")
        except Exception as e:
            self.report.add_warn(check, f"Error calculating readability score: {e}")

    def check_experience_markers(self, soup: BeautifulSoup) -> None:
        """Scans <p> text for first-person experience markers."""
        check = "Information Gain / Experience Markers"
        paragraphs = [p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()]
        full_text = " ".join(paragraphs)

        pattern = re.compile(
            r"\b(I tested|we tested|in my experience|our data|my analysis)\b",
            re.IGNORECASE,
        )
        matches = pattern.findall(full_text)

        if not matches:
            self.report.add_warn(
                check,
                "Low Information Gain: 0 first-person experience markers detected. "
                "Add original data or tests (e.g., 'I tested', 'in my experience', 'our data').",
            )
        else:
            self.report.add_pass(
                check,
                f"Detected {len(matches)} first-person experience marker(s): {list(set(matches))}",
            )


# ------------------------------------------------------------------------------
# Post-Deployment Audit Engine (Tested against live production edge/CDN)
# ------------------------------------------------------------------------------
class PostDeployAuditor:
    """Audits live edge HTTP routing, canonical resolution, and response headers."""

    def __init__(
        self,
        url: str,
        prod_domain: str,
        report: AuditReport,
        timeout: int = 15,
        session: requests.Session | None = None,
    ) -> None:
        self.url = url
        self.prod_domain = prod_domain.rstrip("/")
        self.report = report
        self.timeout = timeout
        self.session = session or requests.Session()

    def run_all(self) -> None:
        log_info(f"Starting Post-Deployment Edge Routing Audit on: {self.url}")

        self.check_x_robots_tag()
        self.check_http_to_https_redirect()
        self.check_www_resolution()
        self.check_trailing_slash_strictness()

    def check_x_robots_tag(self) -> None:
        """Inspects live headers to ensure CDN/edge doesn't inject X-Robots-Tag: noindex."""
        check = "Edge Header Guards: X-Robots-Tag"
        try:
            resp = self.session.get(self.url, timeout=self.timeout, allow_redirects=True)
            x_robots = resp.headers.get("X-Robots-Tag", "")
            if "noindex" in x_robots.lower():
                self.report.add_fail(
                    check,
                    f'Discovered "X-Robots-Tag: {x_robots}" in live HTTP response headers. '
                    "Staging edge header rule is leaking to production.",
                )
                return

            self.report.add_pass(check, "No noindex detected in live X-Robots-Tag header.")
        except Exception as e:
            self.report.add_fail(check, f"Failed connecting to {self.url}: {e}")

    def check_http_to_https_redirect(self) -> None:
        """Forces an http:// request and asserts a 301 redirect to https://."""
        check = "Edge Routing: HTTP to HTTPS Redirect"
        parsed = urlparse(self.url)
        http_url = f"http://{parsed.netloc}{parsed.path or '/'}"
        if parsed.query:
            http_url += f"?{parsed.query}"

        try:
            resp = self.session.get(http_url, timeout=self.timeout, allow_redirects=True)
            # Inspect redirect history
            has_301 = any(r.status_code == 301 for r in resp.history)
            final_https = resp.url.startswith("https://")

            if not resp.history:
                self.report.add_fail(
                    check, f"Request to {http_url} returned HTTP {resp.status_code} without redirecting to HTTPS."
                )
                return

            if not has_301:
                codes = [r.status_code for r in resp.history]
                self.report.add_fail(
                    check,
                    f"Redirect history for {http_url} did not contain a 301 redirect (Status codes: {codes}). "
                    "Must use 301 Permanent Redirect for SEO equity.",
                )
                return

            if not final_https:
                self.report.add_fail(check, f"Final destination {resp.url} is not HTTPS.")
                return

            self.report.add_pass(check, f"Verified 301 redirect from {http_url} to {resp.url}.")
        except Exception as e:
            self.report.add_fail(check, f"Error verifying HTTP to HTTPS redirect: {e}")

    def check_www_resolution(self) -> None:
        """Requests non-preferred domain (with/without www) and asserts 301 redirect."""
        check = "Edge Routing: WWW vs Non-WWW Resolution"
        parsed = urlparse(self.url)
        host = parsed.netloc

        if host.startswith("www."):
            non_preferred_host = host[4:]
        else:
            non_preferred_host = f"www.{host}"

        test_url = f"{parsed.scheme}://{non_preferred_host}{parsed.path or '/'}"

        try:
            resp = self.session.get(test_url, timeout=self.timeout, allow_redirects=True)
            if not resp.history:
                self.report.add_warn(
                    check,
                    f"Request to non-preferred domain {test_url} returned HTTP {resp.status_code} without redirect. "
                    "Ensure canonical host resolution is configured at DNS/CDN level.",
                )
                return

            has_301 = any(r.status_code == 301 for r in resp.history)
            if has_301 and parsed.netloc in resp.url:
                self.report.add_pass(check, f"Verified 301 redirect from {test_url} to canonical host {parsed.netloc}.")
            else:
                statuses = [r.status_code for r in resp.history]
                self.report.add_warn(
                    check,
                    f"Redirect from {test_url} resolved to {resp.url} (History status: {statuses}).",
                )
        except Exception as e:
            self.report.add_warn(check, f"Could not test non-preferred host {test_url}: {e}")

    def check_trailing_slash_strictness(self) -> None:
        """Inverts the trailing slash of target URL and asserts a 301 redirect."""
        check = "Edge Routing: Trailing Slash Strictness"
        parsed = urlparse(self.url)
        path = parsed.path or "/"

        if path == "/":
            self.report.add_pass(check, "Root URL '/' has standard trailing slash.")
            return

        if path.endswith("/"):
            inverted_path = path.rstrip("/")
        else:
            inverted_path = f"{path}/"

        inverted_url = f"{parsed.scheme}://{parsed.netloc}{inverted_path}"

        try:
            # Request without following redirects to inspect immediate response code
            resp = self.session.get(inverted_url, timeout=self.timeout, allow_redirects=False)
            if resp.status_code in (301, 308):
                loc = resp.headers.get("Location", "")
                self.report.add_pass(
                    check,
                    f"Inverted trailing slash {inverted_url} returned HTTP {resp.status_code} redirecting to {loc}.",
                )
            elif resp.status_code == 200:
                self.report.add_fail(
                    check,
                    f"Duplicate 200 OK detected! Both {self.url} and {inverted_url} return HTTP 200. "
                    "Edge must enforce single canonical trailing-slash convention via 301 redirect.",
                )
            else:
                self.report.add_pass(
                    check,
                    f"Inverted trailing slash returned HTTP {resp.status_code} (non-duplicate 200).",
                )
        except Exception as e:
            self.report.add_fail(check, f"Error verifying trailing slash strictness on {inverted_url}: {e}")


# ------------------------------------------------------------------------------
# CLI Parser & Orchestrator
# ------------------------------------------------------------------------------
def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Production-Grade Technical SEO & GEO Pipeline Checker",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Target URL to test (e.g. http://localhost:3000 or https://example.com)",
    )
    parser.add_argument(
        "--env",
        choices=["pre", "post"],
        required=True,
        help="Pipeline environment: 'pre' (local dev server) or 'post' (live edge/CDN)",
    )
    parser.add_argument(
        "--prod-domain",
        required=True,
        help="Production base domain to enforce (e.g. https://example.com)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail pipeline (exit 1) on any GEO or readability warnings",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP request timeout in seconds",
    )
    return parser


def main() -> None:
    parser = build_cli_parser()
    args = parser.parse_args()

    report = AuditReport(
        env=args.env,
        target_url=args.url,
        prod_domain=args.prod_domain,
        strict=args.strict,
    )

    if args.env == "pre":
        auditor = PreDeployAuditor(
            url=args.url,
            prod_domain=args.prod_domain,
            report=report,
            timeout=args.timeout,
        )
        auditor.run_all()
    elif args.env == "post":
        auditor_post = PostDeployAuditor(
            url=args.url,
            prod_domain=args.prod_domain,
            report=report,
            timeout=args.timeout,
        )
        auditor_post.run_all()

    report.print_summary()

    if report.has_failed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
