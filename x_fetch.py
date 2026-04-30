#!/usr/bin/env python3
"""X/Twitter API v2 client for community scanner.

Uses Bearer Token from TWITTER_BEARER_TOKEN env var or X_BEARER_TOKEN env var.
Supports: search, user timeline, conversation, tweet lookup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve token from config env or OS env
def _load_token() -> str:
    # Try OS env first
    token = os.environ.get("TWITTER_BEARER_TOKEN") or os.environ.get("X_BEARER_TOKEN")
    if token:
        return token
    # Try OpenClaw config
    config_path = Path(__file__).resolve().parent.parent / ".." / "openclaw.json"
    # Work around: this script lives in scripts/, workspace is parent
    workspace = Path(__file__).resolve().parent.parent
    config_file = workspace.parent / "openclaw.json" if (workspace / "openclaw.json").exists() else workspace / ".." / "openclaw.json"
    for candidate in [
        workspace / ".." / "openclaw.json",
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

TWITTER_BEARER_TOKEN = _load_token()
API_BASE = "https://api.twitter.com/2"


def _api(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call X API v2 with Bearer Token."""
    if not TWITTER_BEARER_TOKEN:
        return {"error": "No TWITTER_BEARER_TOKEN configured"}
    
    url = f"{API_BASE}{path}"
    if params:
        # Remove None values
        clean = {k: v for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "User-Agent": "OpenClaw-XFetcher/1.0",
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"error": f"HTTP {e.code}", "detail": body[:500]}
    except Exception as e:
        return {"error": str(e)}


def search_tweets(query: str, limit: int = 20, since_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search recent tweets matching query (last 7 days)."""
    params = {
        "query": query,
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics,author_id,conversation_id,text",
        "user.fields": "name,username",
        "expansions": "author_id",
        "sort_order": "recency",
    }
    if since_id:
        params["since_id"] = since_id
    
    params["max_results"] = max(10, min(params["max_results"], 100))
    data = _api("/tweets/search/recent", params)
    if "error" in data:
        return [data]
    
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    items = []
    for t in data.get("data", []):
        author = users.get(t.get("author_id", ""), {})
        metrics = t.get("public_metrics", {})
        items.append({
            "id": t["id"],
            "text": t.get("text", ""),
            "url": f"https://x.com/{author.get('username','_')}/status/{t['id']}",
            "author": author.get("name", ""),
            "username": author.get("username", ""),
            "created_at": t.get("created_at", ""),
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
            "quotes": metrics.get("quote_count", 0),
            "impressions": metrics.get("impression_count", 0),
        })
    return items


def user_timeline(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent tweets from a user."""
    # First get user ID
    user_data = _api(f"/users/by/username/{username}", {"user.fields": "id,name,username"})
    if "error" in user_data:
        return [user_data]
    
    user_id = user_data.get("data", {}).get("id", "")
    if not user_id:
        return [{"error": f"User {username} not found"}]
    
    user_name = user_data["data"].get("name", username)
    user_username = user_data["data"].get("username", username)
    
    params = {
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics,text",
        "exclude": "retweets,replies",
    }
    
    data = _api(f"/users/{user_id}/tweets", params)
    if "error" in data:
        return [data]
    
    items = []
    for t in data.get("data", []):
        metrics = t.get("public_metrics", {})
        items.append({
            "id": t["id"],
            "text": t.get("text", ""),
            "url": f"https://x.com/{user_username}/status/{t['id']}",
            "author": user_name,
            "username": user_username,
            "created_at": t.get("created_at", ""),
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
        })
    return items


def get_tweet(tweet_id: str) -> Dict[str, Any]:
    """Get a single tweet with full details."""
    params = {
        "tweet.fields": "created_at,public_metrics,author_id,conversation_id,text,attachments",
        "user.fields": "name,username",
        "expansions": "author_id,attachments.media_keys",
        "media.fields": "url,type",
    }
    data = _api(f"/tweets/{tweet_id}", params)
    if "error" in data:
        return data
    
    tweet = data.get("data", {})
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    media_list = {m["media_key"]: m for m in data.get("includes", {}).get("media", [])}
    
    author = users.get(tweet.get("author_id", ""), {})
    metrics = tweet.get("public_metrics", {})
    
    result = {
        "id": tweet["id"],
        "text": tweet.get("text", ""),
        "url": f"https://x.com/{author.get('username','_')}/status/{tweet['id']}",
        "author": author.get("name", ""),
        "username": author.get("username", ""),
        "created_at": tweet.get("created_at", ""),
        "likes": metrics.get("like_count", 0),
        "retweets": metrics.get("retweet_count", 0),
        "replies": metrics.get("reply_count", 0),
        "quotes": metrics.get("quote_count", 0),
        "bookmarks": metrics.get("bookmark_count", 0),
        "impressions": metrics.get("impression_count", 0),
        "media": [],
    }
    
    # Attach media URLs
    for mk in tweet.get("attachments", {}).get("media_keys", []):
        m = media_list.get(mk, {})
        if m.get("type") == "photo":
            result["media"].append({"type": "photo", "url": m.get("url", "")})
    
    return {"data": result}


def get_conversation(tweet_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch replies to a specific tweet."""
    params = {
        "query": f"conversation_id:{tweet_id}",
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics,text,in_reply_to_user_id,author_id",
        "user.fields": "name,username",
        "expansions": "author_id",
    }
    
    params["max_results"] = max(10, min(params["max_results"], 100))
    data = _api("/tweets/search/recent", params)
    if "error" in data:
        return [data]
    
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    items = []
    for t in data.get("data", []):
        author = users.get(t.get("author_id", ""), {})
        metrics = t.get("public_metrics", {})
        items.append({
            "id": t["id"],
            "text": t.get("text", ""),
            "url": f"https://x.com/{author.get('username','_')}/status/{t['id']}",
            "author": author.get("name", ""),
            "username": author.get("username", ""),
            "created_at": t.get("created_at", ""),
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "in_reply_to": t.get("in_reply_to_user_id", ""),
        })
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="X/Twitter API v2 client")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=argparse.ArgumentParser)
    
    # search
    p_search = sub.add_parser("search", help="Search recent tweets", add_help=False)
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--format", choices=("json", "text"), default="json")
    
    # user
    p_user = sub.add_parser("user", help="Fetch user timeline", add_help=False)
    p_user.add_argument("username", help="X username (without @)")
    p_user.add_argument("--limit", type=int, default=20)
    p_user.add_argument("--format", choices=("json", "text"), default="json")
    
    # tweet
    p_tweet = sub.add_parser("tweet", help="Get single tweet", add_help=False)
    p_tweet.add_argument("tweet_id", help="Tweet ID")
    p_tweet.add_argument("--format", choices=("json", "text"), default="json")
    
    # conversation
    p_conv = sub.add_parser("conversation", help="Get replies to a tweet", add_help=False)
    p_conv.add_argument("tweet_id", help="Tweet ID")
    p_conv.add_argument("--limit", type=int, default=50)
    p_conv.add_argument("--format", choices=("json", "text"), default="json")
    
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    
    if not TWITTER_BEARER_TOKEN:
        print(json.dumps({"error": "No TWITTER_BEARER_TOKEN configured"}, ensure_ascii=False))
        return 1
    
    if args.command == "search":
        result = search_tweets(args.query, args.limit)
    elif args.command == "user":
        result = user_timeline(args.username, args.limit)
    elif args.command == "tweet":
        result = [get_tweet(args.tweet_id)]
    elif args.command == "conversation":
        result = get_conversation(args.tweet_id, args.limit)
    else:
        result = [{"error": f"Unknown command: {args.command}"}]
    
    payload = {
        "command": args.command,
        "items": result,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if args.format == "text":
        for item in result:
            if "error" in item:
                print(f"[ERROR] {item['error']}")
                continue
            print(f"[{item.get('username', '?')}] {item.get('text', '')[:200]}")
            print(f"  ♥{item.get('likes',0)} 🫩{item.get('retweets',0)} | {item.get('created_at','')}")
            print(f"  {item.get('url','')}")
            print()
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
