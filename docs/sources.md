# Sources

`config/sources.yaml` is the source of truth. This page explains why each source is there,
what it is good for, and the traps found while verifying them (2026-10-31).

Check them all at any time:

```bash
uv run scripts/validate_sources.py          # enabled sources
uv run scripts/validate_sources.py --all    # include disabled ones
```

`ok` = responded with items, `old` = responded but newest item is older than
`stale_after_days`, `FAIL` = error or empty, `off` = disabled.

## What each group is for

| Group | Signal | Why it matters |
| --- | --- | --- |
| **What's New** | every launch, region expansion, GA, price change | the canonical launch log; RSS `<category>` gives `general:products/<slug>` service tags for free |
| **AWS Blogs API** | deep dives, how-tos, launch posts across ~45 blogs | one JSON endpoint, tagged by service, includes authors |
| **AWS News Blog** | the headline launches, weekly roundups | full content; overlaps the Blogs API (dedupe by URL) |
| **Security Bulletins** | CVEs and advisories that touch AWS services | low volume, high importance |
| **Service Health** | outages and degradations | kept apart from launches in the UI |
| **botocore CHANGELOG** | every API / parameter / enum change for every service | API-level truth, often before any blog post; service name in each line |
| **GitHub releases** | CDK, SAM CLI, AWS MCP servers | tooling changes that do not appear on What's New |
| **YouTube / Podcast** | re:Invent and Summit sessions, launch videos | media links per service |
| **Reddit** | r/aws, r/aws_cdk, r/serverless, r/amazonbedrock | practitioner reaction, gotchas, bugs |
| **Hacker News** | AWS stories with 20+ points | what the wider industry noticed |
| **Last Week in AWS / Community Builders** | opinion and community write-ups | context and criticism; tagged `community` |
| **Bluesky / X** | AWS staff, Heroes, community voices | early signal, hallway commentary |

## Traps found while verifying

- **What's New feed is short.** The RSS holds ~100 items, about 10 days. Poll at least daily.
- **What's New JSON API is frozen.** `api/dirs/items/search?item.directoryId=whats-new`
  still answers but its newest item is from 2024-05. Use the RSS feed.
- **Blogs JSON API is live** (`directoryId=blog-posts`, ~40k posts) and is the best single
  source for blog content. Page with `page=N`; 100 posts ≈ 5 days.
- **Reddit:** `.json` endpoints return 403 to scripts; `.rss` works. Unauthenticated requests
  hit 429 after two or three quick calls, so all subreddits go in one multireddit URL
  (`r/a+b+c/new/.rss`) and the fetcher backs off on 429 using `Retry-After`.
  **From GitHub Actions, Reddit blocks the httpx client, not the IP or User-Agent.** A probe
  on 2026-10-31 sent one request per runner with the same User-Agent: curl 200 (2/2), Python
  urllib 200 (2/2), httpx 403 Blocked (4/4). From a home IP httpx works, which hid it. So
  `radar/http.py` uses the standard library's urllib; keep it that way. Reddit also allows
  about one unauthenticated request per IP every few seconds, so all subreddits stay in one
  multireddit URL. If Reddit ever blocks urllib too, the next step is its OAuth API (a
  "script" app; its token endpoint is reachable from runners).
- **botocore CHANGELOG.rst** is ~1.6 MB. Use `If-None-Match` and parse only versions above the
  stored cursor.
- **AWS Podcast** feed is still the one AWS links to, but the newest episode is 2026-04-07.
- **Last Week in AWS:** `/feed/` is the blog; `/newsletter/feed/` is the newsletter archive.

## AWS blog slugs (fallback)

If the Blogs API ever breaks, each blog has an RSS feed at
`https://aws.amazon.com/blogs/<slug>/feed/`:

```
apn architecture aws-cloud-financial-management aws-insights aws awsforsap awsmarketplace
big-data business-intelligence compute contact-center containers database
desktop-and-application-streaming developer devops dotnet enterprise-strategy gametech hpc
ibm-redhat industries infrastructure-and-automation iot machine-learning media
messaging-and-targeting migration-and-modernization mobile modernizing-with-aws mt
networking-and-content-delivery opensource physical-ai publicsector quantum-computing robotics
security smb social-impact storage supply-chain training-and-certification web3
```

## X (Twitter): the people I follow

X offers no free read access and blocks unauthenticated scraping (Nitter-style mirrors are
gone). Options, in order of preference:

1. **Bluesky first.** Many AWS people post there too, and its public API needs no auth.
   Export the X follow list once, look up each person's Bluesky handle, add them to
   `bluesky-aws-people.actors`.
2. **X API with a token.** Set `X_BEARER_TOKEN` and `x-following.handle`, then enable the
   source. The collector would read the follow list once, keep accounts that post about AWS,
   and pull their recent posts within the plan's read quota. This costs money.
3. **A curated X List** instead of the full follow list: fewer accounts, less quota, better
   signal. Same token requirement.

## Adding a source

1. Add an entry to `config/sources.yaml` (copy a similar one).
2. Run `uv run scripts/validate_sources.py --only <id>`.
3. If the `type` is new, add a check in `scripts/validate_sources.py` and a collector in
   `radar/collectors/`.

## Candidates not yet added

- `aws/containers-roadmap` and `aws-cloudformation/cloudformation-coverage-roadmap`
  shipped issues (GitHub API)
- AWS re:Post (no public feed found yet)
- re:Invent / Summit session catalogs (seasonal)
- Per-service documentation "Document history" pages
- Screaming in the Cloud podcast (broad cloud, not AWS-only)
