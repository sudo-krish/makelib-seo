"""
Comprehensive test suite for seo_checker.py covering all pre- and post-deployment rules.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import responses
from bs4 import BeautifulSoup

from src.seo_checker import (
    AuditReport,
    PostDeployAuditor,
    PreDeployAuditor,
    main,
)
from tests.mock_server import MockServer

PROD_DOMAIN = "https://example.com"
DEV_URL = "http://127.0.0.1:3000"


@pytest.fixture
def clean_report() -> AuditReport:
    return AuditReport(env="pre", target_url=DEV_URL, prod_domain=PROD_DOMAIN)


@pytest.fixture
def post_report() -> AuditReport:
    return AuditReport(env="post", target_url=PROD_DOMAIN, prod_domain=PROD_DOMAIN)


# ------------------------------------------------------------------------------
# AuditReport Unit Tests
# ------------------------------------------------------------------------------
class TestAuditReport:
    def test_report_summary_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        report = AuditReport(env="pre", target_url=DEV_URL, prod_domain=PROD_DOMAIN, strict=True)
        report.add_pass("Check 1", "Passed detail")
        report.add_fail("Check 2", "Failed reason")
        report.add_warn("Check 3", "Warning reason")

        assert report.has_failed is True
        report.print_summary()
        captured = capsys.readouterr()
        assert "CRITICAL FAILURES DETECTED" in captured.out
        assert "WARNINGS" in captured.out
        assert "FAILURE: CI/CD pipeline halted" in captured.out

    def test_report_success_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        report = AuditReport(env="pre", target_url=DEV_URL, prod_domain=PROD_DOMAIN)
        report.add_pass("Check 1", "OK")
        assert report.has_failed is False
        report.print_summary()
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out


# ------------------------------------------------------------------------------
# Pre-Deployment Unit Tests
# ------------------------------------------------------------------------------
class TestPreDeployAuditor:
    def test_accidental_noindex_clean(self, clean_report: AuditReport) -> None:
        html = '<html><head><meta name="robots" content="index, follow"></head><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_accidental_noindex(soup)
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) == 1

    def test_accidental_noindex_detected(self, clean_report: AuditReport) -> None:
        html = '<html><head><meta name="robots" content="noindex, nofollow"></head><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_accidental_noindex(soup)
        assert len(clean_report.failed) == 1
        assert "noindex" in clean_report.failed[0].lower()

    def test_canonical_url_valid(self, clean_report: AuditReport) -> None:
        html = f'<html><head><link rel="canonical" href="{PROD_DOMAIN}/blog/post-1"></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_canonical_url(soup)
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) == 1

    def test_canonical_url_missing(self, clean_report: AuditReport) -> None:
        html = "<html><head></head></html>"
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_canonical_url(soup)
        assert len(clean_report.failed) == 1
        assert "missing" in clean_report.failed[0].lower()

    def test_canonical_url_leaked_staging(self, clean_report: AuditReport) -> None:
        html = '<html><head><link rel="canonical" href="http://staging.internal/post-1"></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_canonical_url(soup)
        assert len(clean_report.failed) == 1
        assert "staging/dev urls must not leak" in clean_report.failed[0].lower()

    def test_html_meta_integrity_valid(self, clean_report: AuditReport) -> None:
        title = "A" * 40
        desc = "B" * 130
        html = f"""
        <html lang="en">
        <head>
          <title>{title}</title>
          <meta name="description" content="{desc}">
          <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
          <h1>Main Title</h1>
          <h2>Section 1</h2>
          <h3>Sub Section</h3>
          <img src="pic.jpg" alt="Description">
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_html_meta_integrity(soup)
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) >= 5

    def test_html_meta_integrity_failures(self, clean_report: AuditReport) -> None:
        html = """
        <html>
        <head>
          <title>Short</title>
          <meta name="description" content="Too short">
        </head>
        <body>
          <h1>First H1</h1>
          <h1>Second H1</h1>
          <h2>Section</h2>
          <h4>Skipped directly to H4</h4>
          <img src="pic.jpg">
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_html_meta_integrity(soup)
        assert len(clean_report.failed) >= 5

    def test_html_meta_missing_title_and_desc(self, clean_report: AuditReport) -> None:
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_html_meta_integrity(soup)
        assert any("Title" in f for f in clean_report.failed)
        assert any("Meta Description" in f for f in clean_report.failed)
        assert any("Headings" in f for f in clean_report.failed)

    @responses.activate
    def test_robots_txt_ai_bots_cleared(self, clean_report: AuditReport) -> None:
        responses.add(
            responses.GET,
            f"{DEV_URL}/robots.txt",
            body="User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nAllow: /\n",
            status=200,
        )
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_robots_txt_ai_bots()
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) == 1

    @responses.activate
    def test_robots_txt_ai_bots_blocked(self, clean_report: AuditReport) -> None:
        responses.add(
            responses.GET,
            f"{DEV_URL}/robots.txt",
            body="User-agent: ClaudeBot\nDisallow: /\n",
            status=200,
        )
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_robots_txt_ai_bots()
        assert len(clean_report.failed) == 1
        assert "claudebot" in clean_report.failed[0].lower()

    @responses.activate
    def test_robots_txt_404_allowed(self, clean_report: AuditReport) -> None:
        responses.add(responses.GET, f"{DEV_URL}/robots.txt", status=404)
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_robots_txt_ai_bots()
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) == 1

    @responses.activate
    def test_robots_txt_500_error(self, clean_report: AuditReport) -> None:
        responses.add(responses.GET, f"{DEV_URL}/robots.txt", status=500)
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_robots_txt_ai_bots()
        assert len(clean_report.failed) == 1

    @responses.activate
    def test_sitemap_xml_valid(self, clean_report: AuditReport) -> None:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>{PROD_DOMAIN}/page1</loc></url>
          <url><loc>{PROD_DOMAIN}/page2</loc></url>
        </urlset>
        """
        responses.add(responses.GET, f"{DEV_URL}/sitemap.xml", body=xml, status=200)
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_sitemap_xml()
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) == 1

    @responses.activate
    def test_sitemap_xml_invalid_domain(self, clean_report: AuditReport) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>http://localhost:3000/leaked</loc></url>
        </urlset>
        """
        responses.add(responses.GET, f"{DEV_URL}/sitemap.xml", body=xml, status=200)
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_sitemap_xml()
        assert len(clean_report.failed) == 1
        assert "do not start with" in clean_report.failed[0].lower()

    @responses.activate
    def test_sitemap_xml_parse_error(self, clean_report: AuditReport) -> None:
        responses.add(responses.GET, f"{DEV_URL}/sitemap.xml", body="INVALID XML <<>>", status=200)
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_sitemap_xml()
        assert len(clean_report.failed) == 1
        assert "parsing error" in clean_report.failed[0].lower()

    @responses.activate
    def test_sitemap_xml_no_locs(self, clean_report: AuditReport) -> None:
        responses.add(responses.GET, f"{DEV_URL}/sitemap.xml", body="<urlset></urlset>", status=200)
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_sitemap_xml()
        assert len(clean_report.failed) == 1
        assert "0 <loc>" in clean_report.failed[0]

    def test_json_ld_schemas_valid(self, clean_report: AuditReport) -> None:
        payload = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": "Test Org"},
                {"@type": "Person", "name": "Alice", "sameAs": ["https://linkedin.com/in/alice"]},
                {"@type": "Article", "headline": "SEO Best Practices"},
            ],
        }
        html = f'<html><head><script type="application/ld+json">{json.dumps(payload)}</script></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_json_ld_schemas(soup)
        assert len(clean_report.failed) == 0
        assert len(clean_report.passed) == 1

    def test_json_ld_schemas_missing_person_sameas(self, clean_report: AuditReport) -> None:
        payload = [
            {"@type": "Organization", "name": "Test Org"},
            {"@type": "Person", "name": "Alice"},  # missing sameAs
            {"@type": "Article", "headline": "SEO Best Practices"},
        ]
        html = f'<html><head><script type="application/ld+json">{json.dumps(payload)}</script></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_json_ld_schemas(soup)
        assert len(clean_report.failed) == 1
        assert "sameas" in clean_report.failed[0].lower()

    def test_json_ld_missing_scripts(self, clean_report: AuditReport) -> None:
        html = "<html><head></head></html>"
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_json_ld_schemas(soup)
        assert len(clean_report.failed) == 1
        assert 'no <script type="application/ld+json">' in clean_report.failed[0].lower()

    def test_json_ld_invalid_json(self, clean_report: AuditReport) -> None:
        html = '<html><head><script type="application/ld+json">{broken-json</script></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_json_ld_schemas(soup)
        assert len(clean_report.failed) == 1
        assert "invalid json syntax" in clean_report.failed[0].lower()

    def test_content_readability_and_markers(self, clean_report: AuditReport) -> None:
        html = """
        <html>
        <body>
          <p>
            I tested this tool on the web. We tested the fast page. In my experience it is very easy to use.
            Our data shows great speed. My analysis proves it works well.
          </p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_content_readability(soup)
        auditor.check_experience_markers(soup)
        assert len(clean_report.warnings) == 0
        assert len(clean_report.passed) >= 2

    def test_content_readability_warning_and_missing_markers(self, clean_report: AuditReport) -> None:
        html = """
        <html>
        <body>
          <p>
            The psycho-pathological manifestations of multifaceted socioeconomic institutionalizations
            substantiate an incomprehensibly convoluted counter-intuitive epistemological paradigm.
          </p>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_content_readability(soup)
        auditor.check_experience_markers(soup)
        assert len(clean_report.warnings) >= 2

    def test_content_empty_paragraphs(self, clean_report: AuditReport) -> None:
        html = "<html><body><p></p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        auditor = PreDeployAuditor(DEV_URL, PROD_DOMAIN, clean_report)
        auditor.check_content_readability(soup)
        auditor.check_experience_markers(soup)
        assert any("No paragraph content" in w for w in clean_report.warnings)


# ------------------------------------------------------------------------------
# Post-Deployment Unit Tests
# ------------------------------------------------------------------------------
class TestPostDeployAuditor:
    @responses.activate
    def test_x_robots_tag_clean(self, post_report: AuditReport) -> None:
        responses.add(
            responses.GET,
            PROD_DOMAIN,
            headers={"X-Robots-Tag": "index, follow"},
            status=200,
        )
        auditor = PostDeployAuditor(PROD_DOMAIN, PROD_DOMAIN, post_report)
        auditor.check_x_robots_tag()
        assert len(post_report.failed) == 0
        assert len(post_report.passed) == 1

    @responses.activate
    def test_x_robots_tag_noindex_failure(self, post_report: AuditReport) -> None:
        responses.add(
            responses.GET,
            PROD_DOMAIN,
            headers={"X-Robots-Tag": "noindex"},
            status=200,
        )
        auditor = PostDeployAuditor(PROD_DOMAIN, PROD_DOMAIN, post_report)
        auditor.check_x_robots_tag()
        assert len(post_report.failed) == 1
        assert "noindex" in post_report.failed[0].lower()

    def test_http_to_https_redirect_success(self, post_report: AuditReport) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        hist_resp = MagicMock()
        hist_resp.status_code = 301
        mock_response.history = [hist_resp]

        mock_session.get.return_value = mock_response

        auditor = PostDeployAuditor(PROD_DOMAIN, PROD_DOMAIN, post_report, session=mock_session)
        auditor.check_http_to_https_redirect()
        assert len(post_report.failed) == 0
        assert len(post_report.passed) == 1

    def test_http_to_https_redirect_failure(self, post_report: AuditReport) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "http://example.com/"
        mock_response.history = []
        mock_session.get.return_value = mock_response

        auditor = PostDeployAuditor(PROD_DOMAIN, PROD_DOMAIN, post_report, session=mock_session)
        auditor.check_http_to_https_redirect()
        assert len(post_report.failed) == 1

    def test_www_resolution_success(self, post_report: AuditReport) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        hist_resp = MagicMock()
        hist_resp.status_code = 301
        mock_response.history = [hist_resp]
        mock_session.get.return_value = mock_response

        auditor = PostDeployAuditor("https://example.com/", PROD_DOMAIN, post_report, session=mock_session)
        auditor.check_www_resolution()
        assert len(post_report.passed) == 1

    def test_trailing_slash_root_path(self, post_report: AuditReport) -> None:
        auditor = PostDeployAuditor("https://example.com/", PROD_DOMAIN, post_report)
        auditor.check_trailing_slash_strictness()
        assert any("Root URL" in p for p in post_report.passed)

    def test_trailing_slash_strictness_success(self, post_report: AuditReport) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 301
        mock_response.headers = {"Location": "/pricing"}
        mock_session.get.return_value = mock_response

        auditor = PostDeployAuditor("https://example.com/pricing", PROD_DOMAIN, post_report, session=mock_session)
        auditor.check_trailing_slash_strictness()
        assert len(post_report.failed) == 0
        assert len(post_report.passed) == 1

    def test_trailing_slash_duplicate_200_failure(self, post_report: AuditReport) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        auditor = PostDeployAuditor("https://example.com/pricing", PROD_DOMAIN, post_report, session=mock_session)
        auditor.check_trailing_slash_strictness()
        assert len(post_report.failed) == 1
        assert "duplicate 200" in post_report.failed[0].lower()

    def test_post_deploy_run_all(self, post_report: AuditReport) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-Robots-Tag": "index, follow"}
        mock_response.url = "https://example.com/"
        hist = MagicMock()
        hist.status_code = 301
        mock_response.history = [hist]
        mock_session.get.return_value = mock_response

        auditor = PostDeployAuditor(PROD_DOMAIN, PROD_DOMAIN, post_report, session=mock_session)
        auditor.run_all()
        assert len(post_report.passed) >= 3


# ------------------------------------------------------------------------------
# End-to-End Mock Server & CLI Tests
# ------------------------------------------------------------------------------
class TestEndToEndMockIntegration:
    server: MockServer

    @classmethod
    def setup_class(cls) -> None:
        cls.server = MockServer()
        cls.server.start()

    @classmethod
    def teardown_class(cls) -> None:
        cls.server.stop()

    def test_e2e_pre_deployment_pass(self) -> None:
        report = AuditReport(env="pre", target_url=self.server.url, prod_domain=PROD_DOMAIN)
        auditor = PreDeployAuditor(self.server.url, PROD_DOMAIN, report)
        auditor.run_all()
        assert not report.has_failed
        assert len(report.failed) == 0
        assert len(report.passed) >= 8

    def test_cli_execution_pre(self) -> None:
        with patch(
            "sys.argv", ["seo_checker.py", "--url", self.server.url, "--env", "pre", "--prod-domain", PROD_DOMAIN]
        ):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0

    def test_cli_execution_post_mocked(self) -> None:
        with patch("src.seo_checker.PostDeployAuditor.run_all"):
            with patch(
                "sys.argv", ["seo_checker.py", "--url", PROD_DOMAIN, "--env", "post", "--prod-domain", PROD_DOMAIN]
            ):
                with pytest.raises(SystemExit) as excinfo:
                    main()
                assert excinfo.value.code == 0

    def test_cli_strict_failure_on_warn(self) -> None:
        # Strict mode causes exit code 1 if warnings are generated
        def fake_run(self_auditor: PreDeployAuditor) -> None:
            self_auditor.report.add_warn("Readability", "Low score")

        with patch.object(PreDeployAuditor, "run_all", side_effect=fake_run, autospec=True):
            with patch(
                "sys.argv",
                ["seo_checker.py", "--url", self.server.url, "--env", "pre", "--prod-domain", PROD_DOMAIN, "--strict"],
            ):
                with pytest.raises(SystemExit) as excinfo:
                    main()
                assert excinfo.value.code == 1
