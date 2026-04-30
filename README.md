# Community Scanner

Multi-source community signal aggregator for OpenClaw agents.

## Sources

| Source | Fetch Script | API |
|---|---|---|
| Reddit | `reddit_fetch.py` | Reddit JSON API (no auth) |
| DC Inside | `dc_fetch.py` | DC Inside web/API |
| GitHub | `github_fetch.py` | GitHub API |
| Hacker News | `hn_fetch.py` | HN Firebase API |
| YouTube | `youtube_fetch.py` | YouTube Data API v3 |
| X/Twitter | `x_fetch.py` | X API v2 (Bearer Token) |
| SearXNG | inline in aggregator | SearXNG JSON API |
| News Feeds | `news_feeds.py` | RSS + SearXNG |
| Discord | `discord_fetch.py` | Discord API |

## Quick Start

### Full scan (all sources)
```bash
python3 community_aggregate.py hot --sources reddit dc github hn youtube searxng x
```

### Presets
```bash
# General news across communities
python3 community_aggregate.py --preset general-news

# Breaking world news (SearXNG)
python3 community_aggregate.py --preset breaking-news

# Korea news
python3 community_aggregate.py --preset korea-news

# X/Twitter signals only
python3 community_aggregate.py --preset x-news
```

### X/Twitter standalone
```bash
export TWITTER_BEARER_TOKEN="your-token"
python3 x_fetch.py search "#AI lang:en" --limit 20
python3 x_fetch.py user elonmusk --limit 10
```

## Configuration

| Env Var | Purpose | Default |
|---|---|---|
| `TWITTER_BEARER_TOKEN` | X API v2 auth | auto-detect from `openclaw.json` |
| `SEARXNG_BASE_URL` | SearXNG instance | `https://vps4.tail1546e7.ts.net:18443` |
| `COMMUNITY_SCANNER_UA` | User-Agent prefix | `community-scanner-*` |

## Dependencies

Python 3.9+ standard library only. No pip installs required.

## License

Internal use — jinwon-int.
