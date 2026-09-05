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
| `TWITTER_BEARER_TOKEN` | X API v2 auth | unset; provide explicitly for X runs |
| `SEARXNG_BASE_URL` | SearXNG instance | unset; provide an operator-approved endpoint for live runs |
| `COMMUNITY_SCANNER_UA` | User-Agent prefix | `community-scanner-*` |

## Dependencies

Python 3.9+ standard library only. No pip installs required.

## CI scope

- `.github/workflows/baseline-ci.yml` runs Python compile checks, import smoke checks, CLI `--help` smoke checks, Markdown/relative-link validation, and a conservative secret-pattern scan.
- CI intentionally does not call Reddit, DC Inside, GitHub, HN, YouTube, SearXNG, X/Twitter, Discord, or RSS endpoints.
- Live scanner runs remain manual/scheduled operations and should use explicit credentials/environment outside CI.

## License

MIT. See [LICENSE](LICENSE).

## Public source visibility boundary

This repository is being prepared for possible public source visibility. A
public repository setting would be source-only: it would not approve release or
tag creation, package/image publication, production deploy/restart/reload,
database mutation, provider or Telegram sends, credential movement, history
rewrite, or any other live operation.

Runtime credentials and private operational data must stay outside the
repository. Example configuration must use placeholders only.

### Aggregate CLI result status

Collectors are resolved beside `community_aggregate.py`, both in a fresh clone and in the existing `workspace/scripts` layout. JSON includes `successful_sources` and per-source `errors`. The CLI exits 1 when every requested source raises a collection error, while still printing the result and diagnostics. A successful empty result, filtered-out results, or partial source failure exits 0. Collector warnings remain in `errors` and do not by themselves fail a successful call.

Offline regression checks: `python3 -m unittest discover -s tests -v`. Fixtures run sibling collectors in temporary directories.
