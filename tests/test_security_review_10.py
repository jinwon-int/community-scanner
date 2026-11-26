"""Regression tests for the community-scanner#10 security review (F1-F3). No network."""
import importlib.util
import os
import re
from pathlib import Path
import ssl
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, env=None):
    with mock.patch.dict(os.environ, env or {}, clear=False):
        for key in ("SEARXNG_BASE_URL", "SEARXNG_CA_FILE"):
            if env is None or key not in env:
                os.environ.pop(key, None)
        spec = importlib.util.spec_from_file_location(f"{name}_under_test", ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


class GhApiMethodTests(unittest.TestCase):
    """F2: read paths must never become POST."""

    def setUp(self):
        self.gf = load("github_fetch")

    def run_gh_api(self, path, params):
        done = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
        with mock.patch.object(self.gf.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(self.gf.subprocess, "run", return_value=done) as run:
            self.gf.gh_api(path, params)
        return run.call_args.args[0]

    def test_gh_api_forces_get_even_with_params(self):
        cmd = self.run_gh_api("/repos/o/r/issues", {"state": "open", "per_page": 5})
        self.assertEqual(cmd[:5], ["gh", "api", "--method", "GET", "/repos/o/r/issues"])
        self.assertIn("state=open", cmd)

    def test_gh_api_forces_get_without_params(self):
        cmd = self.run_gh_api("/search/issues", None)
        self.assertEqual(cmd[2:4], ["--method", "GET"])

    def test_valid_repo_names(self):
        for name in ("octo/hello", "a-b/c_d.e", "jinwon-int/community-scanner", "o/.github"):
            with self.subTest(name=name):
                self.assertEqual(self.gf.validate_full_name(name), name)

    def test_invalid_repo_names_rejected(self):
        bad = ["", "octo", "a/b/c", "../x", "a/..", "./b", "a/b?x=1", "a/b#f",
               "a b/c", "a/b\n", "/a/b", "a/", "a/b/../../user"]
        for name in bad:
            with self.subTest(name=name):
                with self.assertRaises(self.gf.GitHubFetchError):
                    self.gf.validate_full_name(name)

    def test_repo_fetchers_validate_before_any_api_call(self):
        calls = [
            lambda: self.gf.fetch_repo("../user"),
            lambda: self.gf.fetch_repo_issues("a/b/c", "open", 5),
            lambda: self.gf.fetch_repo_prs("a/..", "open", 5),
            lambda: self.gf.fetch_releases("x?y=1/z", 5),
        ]
        with mock.patch.object(self.gf, "api") as api:
            for call in calls:
                with self.assertRaises(self.gf.GitHubFetchError):
                    call()
            api.assert_not_called()

    def test_cli_rejects_bad_repo_with_exit_2(self):
        result = subprocess.run([sys.executable, str(ROOT / "github_fetch.py"), "issues", "a/b/../c"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid repository name", result.stderr)


class TlsVerificationTests(unittest.TestCase):
    """F1: TLS verification stays on; a CA file only adds trust."""

    def test_default_context_verifies(self):
        nf = load("news_feeds")
        ctx = nf._ssl_context()
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_ca_file_is_added_not_replacing_and_verification_stays_on(self):
        nf = load("news_feeds", {"SEARXNG_CA_FILE": "/tmp/extra-ca.pem"})
        with mock.patch.object(ssl.SSLContext, "load_verify_locations") as load_ca:
            ctx = nf._ssl_context()
        load_ca.assert_called_once_with(cafile="/tmp/extra-ca.pem")
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_no_cert_none_left_in_sources(self):
        for path in ROOT.glob("*.py"):
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertFalse("CERT_NONE" in text, "TLS verification disabled")
                self.assertFalse("check_hostname = False" in text, "hostname check disabled")


class SearxngDefaultTests(unittest.TestCase):
    """F3: no internal endpoint baked in; unset means skip without network."""

    def test_no_internal_host_default(self):
        for path in ROOT.glob("*.py"):
            with self.subTest(path=path.name):
                self.assertIsNone(re.search(r"\.ts\.net\b", path.read_text()), "internal host default")

    def test_news_feeds_unset_skips_without_network(self):
        nf = load("news_feeds")
        self.assertIsNone(nf.SEARXNG_BASE_URL)
        with mock.patch.object(nf.urllib.request, "urlopen", side_effect=AssertionError("network")):
            rows = nf._searxng_search("world news")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "searxng")
        self.assertIn("not set", rows[0]["error"])

    def test_aggregate_unset_skips_without_network(self):
        ca = load("community_aggregate")
        self.assertIsNone(ca.SEARXNG_BASE_URL)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(ca.AggregateError, "not set"):
                ca.collect_searxng("rust release", 5)

    def test_env_value_is_used_when_set(self):
        ca = load("community_aggregate", {"SEARXNG_BASE_URL": "https://search.example.test/"})
        self.assertEqual(ca.SEARXNG_BASE_URL, "https://search.example.test")


if __name__ == "__main__":
    unittest.main()
