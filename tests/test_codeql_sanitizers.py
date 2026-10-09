"""Regression tests for the CodeQL fixes in community-scanner#8.

Each fix must (a) reject the bypass shape CodeQL flagged and (b) keep the
previous output for the ordinary inputs the scrapers actually see.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import dc_fetch  # noqa: E402
import news_feeds  # noqa: E402
import reddit_fetch  # noqa: E402


def _old_dc_text(raw: str) -> str:
    """The pre-#8 regex pipeline, kept here only to pin output equivalence."""
    raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<br\s*/?\s*>', '\n', raw)
    raw = re.sub(r'</p>', '\n', raw)
    text = re.sub(r'<[^>]+>', '', raw)
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _new_dc_text(raw: str) -> str:
    return re.sub(r'\n{3,}', '\n\n', dc_fetch._html_fragment_to_text(raw)).strip()


class XHostTest(unittest.TestCase):
    def test_real_x_hosts(self):
        for url in ("https://x.com/user/status/1", "https://www.x.com/a", "http://mobile.x.com/b"):
            self.assertTrue(news_feeds._is_x_host(url), url)

    def test_substring_lookalikes_are_not_x(self):
        for url in ("https://evil.com/?q=x.com", "https://notx.com/a", "https://x.com.evil.example/",
                    "https://example.com/x.com/path", "", "not a url"):
            self.assertFalse(news_feeds._is_x_host(url), url)


class RedditPermalinkTest(unittest.TestCase):
    def test_reddit_link_becomes_relative_like_before(self):
        link = "https://www.reddit.com/r/python/comments/abc123/title/?utm=1#c"
        self.assertEqual(reddit_fetch._reddit_permalink(link),
                         link.replace("https://www.reddit.com", ""))

    def test_lookalike_and_foreign_hosts_are_unchanged(self):
        for link in ("https://www.reddit.com.evil.example/r/x", "https://old.reddit.com/r/x",
                     "http://www.reddit.com/r/x", "https://example.com/r/x"):
            self.assertEqual(reddit_fetch._reddit_permalink(link), link)


class DcFragmentTextTest(unittest.TestCase):
    ORDINARY = [
        '<p>첫 줄</p><p>둘째 &amp; 셋째</p>',
        '안녕<br>하세요<br/>반갑<br />습니다',
        '<div><span>A&nbsp;B</span> &lt;tag&gt; &quot;q&quot;</div>',
        '<p>본문</p><script>var a = "<b>x</b>";</script><p>끝</p>',
        '<p>a</p>\n\n\n\n<p>b</p>',
        '<img src="x.png"><a href="/l">링크</a> 텍스트',
    ]

    def test_ordinary_fragments_match_previous_output(self):
        for raw in self.ORDINARY:
            self.assertEqual(_new_dc_text(raw), _old_dc_text(raw), raw)

    def test_script_variants_the_regex_missed_are_dropped(self):
        for raw in ('<p>ok</p><script>alert(1)</script >',
                    '<p>ok</p><SCRIPT type="text/javascript">alert(1)</SCRIPT>',
                    '<p>ok</p><style>p{color:red}</style>',
                    '<p>ok</p><script>alert(1)'):
            text = _new_dc_text(raw)
            self.assertEqual(text, "ok", raw)

    def test_extract_post_content_uses_parser_fallback(self):
        html = ('<div class="thum-txtin"><p>본문</p><script>alert(1)</script >'
                '<p>둘째</p></div></div>')
        self.assertEqual(dc_fetch._extract_post_content(html)["content"], "본문\n둘째")


if __name__ == "__main__":
    unittest.main()
