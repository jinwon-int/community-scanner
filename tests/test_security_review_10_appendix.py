"""Regression tests for community-scanner#10 appendix findings F4-F7 + CI. No network."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
NETWORK_SCRIPTS = ["community_aggregate", "dc_fetch", "discord_fetch", "github_fetch", "hn_fetch",
                   "news_feeds", "reddit_fetch", "x_fetch", "youtube_fetch"]


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_appendix_test", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ControlCharTests(unittest.TestCase):
    """F4: scraped fields cannot forge rows or ANSI sequences in text mode."""

    def test_clean_line_strips_c0_c1_and_del(self):
        for name in NETWORK_SCRIPTS:
            with self.subTest(script=name):
                clean = load(name)._clean_line
                out = clean("ok\nFAKE ROW\r\x1b[31mred\x7f\x9bend\tx")
                self.assertNotRegex(out, r"[\x00-\x1f\x7f-\x9f]")
                self.assertIn("FAKE ROW", out)  # text kept, only controls replaced
                self.assertEqual(clean("한글 ✓ plain"), "한글 ✓ plain")

    def test_aggregate_text_output_has_no_injected_rows(self):
        ca = load("community_aggregate")
        item = ca.to_item("hn", "story", "title\n- [fake/row] injected", "https://example.test/a",
                          author="bob\x1b[2J", summary="s")
        payload = {"query": "q", "sources": ["hn"], "successful_sources": ["hn"], "count": 1,
                   "items": [item], "buckets": {}, "bucket_summaries": {}, "errors": [],
                   "fetched_at": "2026-11-26T00:00:00+00:00"}
        text = ca.emit_text(payload, output_mode="full")
        self.assertNotIn("\x1b", text)
        self.assertFalse(any(line.startswith("- [fake/row]") for line in text.splitlines()))
        self.assertIn("injected", text)

    def test_json_output_is_untouched(self):
        ca = load("community_aggregate")
        self.assertEqual(ca.to_item("hn", "story", "a\nb", "https://x.test")["title"], "a\nb")


class ResponseCapTests(unittest.TestCase):
    """F5: response bodies are bounded."""

    def test_every_network_script_caps_reads(self):
        for name in NETWORK_SCRIPTS:
            with self.subTest(script=name):
                text = (ROOT / f"{name}.py").read_text()
                self.assertNotRegex(text, r"\bresp\.read\(\)")
                self.assertNotIn("json.load(resp)", text)
                mod = load(name)
                self.assertEqual(mod._read_capped(io.BytesIO(b"abc"), limit=3), b"abc")
                with self.assertRaises(Exception) as ctx:
                    mod._read_capped(io.BytesIO(b"abcd"), limit=3)
                self.assertIn("exceeds", str(ctx.exception))

    def test_cap_error_is_the_module_error_type(self):
        gf = load("github_fetch")
        with self.assertRaises(gf.GitHubFetchError):
            gf._read_capped(io.BytesIO(b"x" * 10), limit=5)


class DiscordTokenTests(unittest.TestCase):
    """F6: the bot token is never accepted on the command line."""

    def run_cli(self, *args, env_token=None):
        env = {k: v for k, v in os.environ.items() if k != "DISCORD_BOT_TOKEN"}
        if env_token is not None:
            env["DISCORD_BOT_TOKEN"] = env_token
        return subprocess.run([sys.executable, str(ROOT / "discord_fetch.py"), *args],
                              capture_output=True, text=True, timeout=10, env=env)

    def test_token_flag_is_rejected_before_any_request(self):
        result = self.run_cli("--token", "not-a-real-token", "messages", "123")
        self.assertEqual(result.returncode, 2)
        self.assertIn("DISCORD_BOT_TOKEN", result.stderr)
        self.assertNotIn("not-a-real-token", result.stderr + result.stdout)

    def test_help_does_not_advertise_token_flag(self):
        self.assertNotIn("--token", self.run_cli("--help").stdout)

    def test_missing_env_token_still_soft_fails_for_aggregate(self):
        result = self.run_cli("--allow-missing-token", "messages", "123")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Missing Discord bot token", result.stdout)


class UrlSchemeTests(unittest.TestCase):
    """F7: only http(s) links leave the aggregator."""

    def test_safe_url(self):
        ca = load("community_aggregate")
        for url in ("https://example.test/a", "http://example.test", "HTTPS://Example.test/x"):
            with self.subTest(url=url):
                self.assertEqual(ca.safe_url(url), url)
        for url in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x", "file:///etc/passwd",
                    "vbscript:x", "//example.test/a", "/relative", "", None):
            with self.subTest(url=url):
                self.assertEqual(ca.safe_url(url), "")

    def test_to_item_applies_scheme_allowlist(self):
        ca = load("community_aggregate")
        self.assertEqual(ca.to_item("dc", "post", "t", "javascript:alert(1)")["url"], "")


class RepoHygieneTests(unittest.TestCase):
    def test_no_bytecode_tracked(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        self.assertEqual([f for f in tracked if f.endswith((".pyc", ".pyo")) or "__pycache__/" in f], [])


class CiCredentialTests(unittest.TestCase):
    def test_checkout_does_not_persist_credentials(self):
        for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = wf.read_text()
            with self.subTest(workflow=wf.name):
                self.assertEqual(text.count("actions/checkout@"), text.count("persist-credentials: false"))


if __name__ == "__main__":
    unittest.main()
