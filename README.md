# AWS Radar

A self-updating, expert-level digest of everything new in AWS, browsable by service.

AWS ships dozens of changes a day across hundreds of services, spread over What's New posts, a
few hundred blogs, SDK changelogs, security bulletins, conference sessions, Reddit threads and
social posts. AWS Radar pulls all of it on a schedule, maps each item to the service(s) it is
about, and publishes a static site where you pick a service (by its official AWS icon) and see
what changed, newest first, in one line each.

It is written for people who already know AWS well: no "what is S3" intros, no marketing copy,
just the change, the date, the source link and a tag such as `GA`, `preview`, `region`,
`pricing` or `deprecation`.

## How it works

```
 sources (config/sources.yaml)
   │  RSS/Atom, AWS JSON APIs, Reddit, Hacker News, GitHub releases, Bluesky, X
   ▼
 collect   ──► data/raw/<source>/<YYYY-MM>.jsonl     append-only, one JSON item per line
   ▼
 classify  ──► service ids + change tags              keyword/tag rules, no LLM
   ▼
 digest    ──► data/services/<service>.json           per-service timeline
           ──► data/changes/<YYYY-MM-DD>.md           what is new since the last run
   ▼
 build     ──► site/                                  static HTML + JSON, AWS icons
   ▼
 git commit + push                                    the diff *is* the changelog
```

Design rules:

- **No LLM tokens in the pipeline.** Everything is deterministic Python: feeds, APIs, regex
  and keyword rules. Runs are repeatable and cheap, and can run in GitHub Actions for free.
- **Git is the database.** Collected items are committed as JSONL. Each run's commit diff shows
  exactly what arrived. Nothing already collected is fetched or recomputed again.
- **Static output.** The site is plain HTML, CSS and vanilla JS reading pre-built JSON. It can be
  served from GitHub Pages or opened from disk.
- **Official icons.** Service tiles use the
  [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/) asset package.

## Repository layout

```
aws-radar/
├── config/
│   ├── sources.yaml            every source: type, URL, cadence, auth needs, default service
│   ├── service_overrides.yaml  hand-curated ids, aliases, keywords (edit this)
│   ├── services.yaml           service catalog (generated from the icon package + overrides)
│   └── vocab/                  What's New product slugs and botocore service names
├── radar/                      Python package (the pipeline)
│   ├── collectors/             one module per source type: rss, aws_blog_api, hn, bluesky, botocore, x
│   ├── catalog.py              service catalog + name matcher
│   ├── classify.py             item → services + change tags (rules, no LLM)
│   ├── collect.py              runs due collectors, appends to data/raw
│   ├── build.py                digests, per-run changes, site data
│   └── store.py / http.py / text.py
├── scripts/
│   ├── update.py               collect → build → commit (the scheduled job)
│   ├── validate_sources.py     hit every source, report health
│   └── build_catalog.py        download AWS icons, regenerate services.yaml
├── data/
│   ├── raw/<source>/<YYYY-MM>.jsonl   collected items, append-only, committed
│   ├── services/<service>.md   per-service digest, readable on GitHub (generated)
│   ├── changes/<YYYY-MM-DD>.md what each run added (generated)
│   └── state/                  cursors, ETags, last run per source
├── site/                       static front end: index.html, app.js, app.css
│   ├── assets/icons/           AWS Architecture Icons (SVG), services/ and categories/
│   └── data/                   generated JS data (gitignored, built by the pages workflow)
├── samples/                runnable prototypes and playgrounds, by service and language
│   └── <service>/<python|node|...>/<sample>/
├── docs/                   design notes (sources, classification rules)
└── .github/workflows/      scheduled update job
```

## Sources

The full list, with URLs and status, is in [`config/sources.yaml`](config/sources.yaml) and
explained in [`docs/sources.md`](docs/sources.md). In short:

| Group | Examples | Auth |
| --- | --- | --- |
| AWS official | What's New, all ~45 AWS blogs (one JSON API), News Blog, Security Bulletins, service health | none |
| AWS code | botocore changelog (every API change), CDK / SAM CLI / AWS MCP releases | none |
| AWS media | AWS Podcast, three AWS YouTube channels | none |
| Community | r/aws and related subreddits, Hacker News, Last Week in AWS, AWS Community Builders | none |
| Social | Bluesky accounts and lists, X accounts I follow | Bluesky: none. X: paid API token |

## Running it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv run scripts/update.py                # collect due sources, rebuild digests and site data
uv run scripts/update.py --force        # poll every source now, ignoring cadence
uv run scripts/update.py --build-only   # rebuild from data/raw without network
uv run scripts/validate_sources.py      # check every configured source responds
uv run scripts/build_catalog.py --report   # refresh AWS icons + service catalog
python3 -m http.server -d site 8765     # browse http://localhost:8765 (or open site/index.html)
```

The first run backfills: about 3 months of AWS blog posts, 90 days of botocore API changes,
and whatever each feed still holds. After that each run only fetches what changed
(conditional GETs, cursors) and appends new items.

### Automation

- [`.github/workflows/update.yml`](.github/workflows/update.yml) runs every 6 hours:
  collect, build, and commit `data/` back to `main` when new items arrived
  (message `data: update <time> (+N items)`), then redeploys the site if anything changed.
  It rebases before pushing, so a local `update.py --commit --push` can run alongside it.
- [`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds `site/data/` from
  `data/raw/` and publishes `site/` to GitHub Pages on every push to `main`.

### The site

Pick a service (official AWS icon tiles, sorted by recent activity or grouped by category)
to see its timeline. Filter by kind (launches, API changes, blogs, security & health,
video, community, social) and by tag (`GA`, `preview`, `region`, `pricing`,
`deprecation`, ...). Posts that only tag a service in passing are hidden unless you ask
for them. The home page also has a cross-service "Latest" stream for the past 7 days.
Press `/` to search.

## Status

- [x] Repo, README, CLAUDE.md
- [x] Source registry (`config/sources.yaml`) and validator (18 sources live, X pending a token)
- [x] Collectors and append-only raw store
- [x] Service catalog with icons (294 services, 289 official icons)
- [x] Classifier and per-service digests
- [x] Static site
- [x] Scheduled GitHub Actions run with auto-commit
- [ ] X (Twitter) collector (needs a paid API token)
- [ ] Samples

## License

Code is MIT. Digests link to and briefly quote public sources; the original content belongs to
its authors. AWS service icons are © Amazon Web Services and used under AWS's icon terms.
This project is not affiliated with or endorsed by AWS.
