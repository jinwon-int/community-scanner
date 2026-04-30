#!/usr/bin/env python3
"""News feed aggregator: RSS feeds + X/Twitter API v2.

Sources:
  - RSS: Reuters, BBC, Yonhap, AP News
  - X/Twitter: Direct API v2 via Bearer Token (preferred) or Nitter RSS fallback
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "https://vps4.tail1546e7.ts.net:18443")

# --- X API v2 Bearer Token ---
def _load_x_token() -> str:
    tok = os.environ.get("TWITTER_BEARER_TOKEN") or os.environ.get("X_BEARER_TOKEN")
    if tok:
        return tok
    for candidate in [
        Path.home() / ".openclaw" / "openclaw.json",
    ]:
        try:
            with open(candidate) as f:
                c = json.load(f)
                tok = c.get("env", {}).get("vars", {}).get("TWITTER_BEARER_TOKEN", "")
                if tok:
                    return tok
        except Exception:
            continue
    return ""

X_BEARER_TOKEN = _load_x_token()
X_API_BASE = "https://api.twitter.com/2"
# --- End X API ---

RSS_FEEDS = {
    "bbc": "https://feeds.bbci.co.uk/news/rss.xml",
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "yonhap": "https://www.yna.co.kr/rss/news.xml",
    "yonhap_world": "https://www.yna.co.kr/rss/international.xml",
    "yonhap_economy": "https://www.yna.co.kr/rss/economy.xml",
    "yonhap_politics": "https://www.yna.co.kr/rss/politics.xml",
}

# Major X/Twitter accounts via Nitter RSS (public, no API key needed)
NITTER_INSTANCE = "https://nitter.privacydev.net"
NITTER_FALLBACKS = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://xcancel.com",
]
X_RSS_ACCOUNTS = {
    "reuters_x": f"{NITTER_INSTANCE}/Reuters/rss",
    "bbcbreaking_x": f"{NITTER_INSTANCE}/BBCBreaking/rss",
    "ap_x": f"{NITTER_INSTANCE}/AP/rss",
    "cnnbrk_x": f"{NITTER_INSTANCE}/cnnbrk/rss",
}


def _ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _searxng_search(query: str, categories: str = "news", time_range: str = "day", limit: int = 10) -> List[Dict[str, Any]]:
    """Search via SearXNG with news category + time filter."""
    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "time_range": time_range,
        "pageno": 1,
    }
    url = f"{SEARXNG_BASE_URL}/search?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw-NewsBot/1.0"})
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return [{"error": str(e), "source": "searxng", "query": query}]
    
    items = []
    for r in data.get("results", [])[:limit]:
        items.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "published": r.get("publishedDate", ""),
            "source": "x.com" if "x.com" in (r.get("url") or "") else "searxng",
            "snippet": re.sub(r"<[^>]+>", "", r.get("content", "") or "")[:300],
            "engines": r.get("engines", []),
        })
    return items


def _fetch_rss(url: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """Fetch and parse an RSS feed."""
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw-NewsBot/1.0"})
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout) as resp:
            raw = resp.read()
    except Exception as e:
        return [{"error": str(e), "source": "rss", "url": url}]
    
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [{"error": "XML parse failed", "source": "rss", "url": url}]
    
    # RSS 2.0
    for item in root.iter("item"):
        title = ""
        link = ""
        pubdate = ""
        desc = ""
        for child in item:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "title":
                title = (child.text or "").strip()
            elif tag == "link":
                link = (child.text or "").strip()
            elif tag in ("pubDate", "published"):
                pubdate = (child.text or "").strip()
            elif tag == "description":
                desc = re.sub(r"<[^>]+>", "", (child.text or "")).strip()[:300]
        if title:
            items.append({
                "title": title,
                "url": link,
                "published": pubdate,
                "source": "rss",
                "snippet": desc,
            })
    return items


def _filter_recent(items: List[Dict[str, Any]], hours: int = 24) -> List[Dict[str, Any]]:
    """Filter items to recent ones (within N hours)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered = []
    for item in items:
        pub = item.get("published", "")
        if not pub:
            filtered.append(item)  # Keep items without dates
            continue
        # Try common date formats
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
        ]:
            try:
                if fmt.endswith("%Z"):
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub)
                elif fmt.endswith("%z"):
                    dt = datetime.strptime(pub, fmt)
                else:
                    dt = datetime.strptime(pub, fmt).replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    filtered.append(item)
                break
            except (ValueError, OverflowError):
                continue
    return filtered


def collect_rss(feeds: Optional[List[str]] = None, hours: int = 24) -> List[Dict[str, Any]]:
    """Collect from RSS feeds (both news sites and X/Twitter via Nitter)."""
    if feeds is None:
        feeds = list(RSS_FEEDS.keys())
    
    all_urls = {}
    for name in feeds:
        url = RSS_FEEDS.get(name)
        if url:
            all_urls[name] = url
    
    all_items = []
    for name, url in all_urls.items():
        items = _fetch_rss(url)
        for item in items:
            item["feed"] = name
        all_items.extend(items)
    
    return _filter_recent(all_items, hours)


def collect_x_rss(accounts: Optional[List[str]] = None, hours: int = 12) -> List[Dict[str, Any]]:
    """Collect breaking news from X/Twitter via Nitter RSS feeds with instance fallback."""
    if accounts is None:
        accounts = list(X_RSS_ACCOUNTS.keys())
    
    all_items = []
    # Try fastest instance first, fall back on failure
    instances = [NITTER_INSTANCE] + NITTER_FALLBACKS
    
    for name in accounts:
        fetched = False
        for instance in instances:
            if fetched:
                break
            url = f"{instance}/{name.split('_')[0].replace('reuters','Reuters').replace('bbcbreaking','BBCBreaking').replace('ap','AP').replace('cnnbrk','cnnbrk')}/rss"
            # Use the pre-built URL from X_RSS_ACCOUNTS for the primary
            actual_url = X_RSS_ACCOUNTS.get(name, url)
            if instance != NITTER_INSTANCE:
                # Build URL for fallback instance
                account_name = {"reuters_x": "Reuters", "bbcbreaking_x": "BBCBreaking", "ap_x": "AP", "cnnbrk_x": "cnnbrk"}.get(name, name)
                actual_url = f"{instance}/{account_name}/rss"
            try:
                items = _fetch_rss(actual_url, timeout=8)
                if items and not any("error" in i for i in items):
                    for item in items:
                        item["feed"] = name
                        item["source"] = "x.com"
                    all_items.extend(items)
                    fetched = True
            except Exception:
                continue
        if not fetched:
            all_items.append({"title": f"X feed unavailable: {name}", "url": "", "published": "", "source": "x.com", "snippet": "All Nitter instances failed", "feed": name})
    
    return _filter_recent(all_items, hours)


# X/Twitter account handle mappings (for direct API v2 access)
X_BREAKING_ACCOUNTS = ["Reuters", "BBCBreaking", "AP", "cnnbrk"]
X_TECH_ACCOUNTS = ["kaboroe", "_akhaliq", "ai_daily_digest"]


def _x_api_timeline(username: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch recent tweets from a user via X API v2."""
    if not X_BEARER_TOKEN:
        return [{"error": "No X API Bearer Token"}]
    
    # Get user ID first
    try:
        req = urllib.request.Request(
            f"{X_API_BASE}/users/by/username/{username}?user.fields=id,name,username",
            headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            user_data = json.loads(resp.read())
        user_id = user_data.get("data", {}).get("id", "")
        user_name = user_data.get("data", {}).get("name", username)
        if not user_id:
            return [{"error": f"User not found: {username}"}]
    except Exception as e:
        return [{"error": f"User lookup failed for {username}: {e}"}]
    
    # Fetch tweets
    params = {
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics,text",
        "exclude": "retweets",
    }
    url = f"{X_API_BASE}/users/{user_id}/tweets?{urllib.parse.urlencode(params)}"
    
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return [{"error": f"API failed for {username}: {e}"}]
    
    items = []
    for t in data.get("data", []):
        metrics = t.get("public_metrics", {})
        items.append({
            "title": t.get("text", "")[:200],
            "url": f"https://x.com/{username}/status/{t['id']}",
            "published": t.get("created_at", ""),
            "source": "x.com",
            "snippet": t.get("text", "")[:300],
            "feed": f"{username}_api",
            "author": user_name,
        })
    return items


def _x_api_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search recent tweets via X API v2."""
    if not X_BEARER_TOKEN:
        return [{"error": "No X API Bearer Token"}]
    
    params = {
        "query": query,
        "max_results": max(10, min(limit, 100)),
        "tweet.fields": "created_at,public_metrics,author_id,text",
        "user.fields": "name,username",
        "expansions": "author_id",
        "sort_order": "recency",
    }
    url = f"{X_API_BASE}/tweets/search/recent?{urllib.parse.urlencode(params)}"
    
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return [{"error": f"X search failed: {e}"}]
    
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    items = []
    for t in data.get("data", []):
        author = users.get(t.get("author_id", ""), {})
        items.append({
            "title": t.get("text", "")[:200],
            "url": f"https://x.com/{author.get('username','_')}/status/{t['id']}",
            "published": t.get("created_at", ""),
            "source": "x.com",
            "snippet": t.get("text", "")[:300],
            "feed": "x_search",
            "author": author.get("name", ""),
        })
    return items


def collect_x_api(accounts: Optional[List[str]] = None, hours: int = 12, limit: int = 10) -> List[Dict[str, Any]]:
    """Collect breaking news from X/Twitter via API v2 Bearer Token.
    Falls back to Nitter RSS if no token available.
    """
    if not X_BEARER_TOKEN:
        return collect_x_rss(accounts, hours)
    
    if accounts is None:
        accounts = X_BREAKING_ACCOUNTS
    
    all_items = []
    for username in accounts:
        items = _x_api_timeline(username, limit=min(limit, 10))
        for item in items:
            if "error" not in item:
                all_items.append(item)
    
    return _filter_recent(all_items, hours)


def collect_reuters(limit: int = 10) -> List[Dict[str, Any]]:
    """Collect Reuters news via SearXNG (Reuters RSS is behind paywall)."""
    items = _searxng_search("world news", categories="news", time_range="day", limit=limit)
    # Filter to Reuters-only results
    reuters_items = []
    for item in items:
        engines = item.get("engines", [])
        if "reuters" in engines:
            item["source"] = "reuters"
            item["feed"] = "reuters_searxng"
            reuters_items.append(item)
    return reuters_items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate news from RSS feeds and X/Twitter")
    parser.add_argument("--sources", nargs="+", choices=["rss", "x", "reuters", "all"], default=["all"])
    parser.add_argument("--rss-feeds", nargs="+", choices=list(RSS_FEEDS.keys()), default=None,
                        help="Specific RSS feeds to fetch")
    parser.add_argument("--x-accounts", nargs="+", choices=list(X_RSS_ACCOUNTS.keys()), default=None,
                        help="Specific X accounts to fetch via Nitter RSS")
    parser.add_argument("--limit", type=int, default=10, help="Max items per source")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back for RSS")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    
    output = {"items": [], "meta": {"fetched_at": datetime.now(timezone.utc).isoformat()}}
    
    if "rss" in args.sources or "all" in args.sources:
        rss_items = collect_rss(args.rss_feeds, args.hours)
        for item in rss_items[:args.limit]:
            output["items"].append(item)
    
    if "reuters" in args.sources or "all" in args.sources:
        reuters_items = collect_reuters(args.limit)
        for item in reuters_items[:args.limit]:
            output["items"].append(item)
    
    if "x" in args.sources or "all" in args.sources:
        # Prefer X API v2, fall back to Nitter RSS
        if X_BEARER_TOKEN:
            x_items = collect_x_api(None, args.hours, args.limit)
        else:
            x_items = collect_x_rss(args.x_accounts, args.hours)
        for item in x_items[:args.limit]:
            output["items"].append(item)
    
    if args.format == "text":
        for item in output["items"]:
            print(f"[{item.get('source', '?')}/{item.get('feed', 'x')}] {item.get('title', '(no title)')[:120]}")
            if item.get("snippet"):
                print(f"  {item['snippet'][:150]}")
            print(f"  {item.get('url', '')}")
            print()
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
