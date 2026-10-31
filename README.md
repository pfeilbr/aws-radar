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
│   ├── sources.yaml        every source: type, URL, cadence, auth needs, default service
│   └── services.yaml       service catalog: id, name, category, icon, match keywords
├── radar/                  Python package (the pipeline)
│   ├── collectors/         one module per source type (rss, aws_api, reddit, hn, github, bluesky, x)
│   ├── classify.py         item → services + tags
│   ├── digest.py           per-service timelines and run diffs
│   └── site.py             static site builder
├── scripts/                entry points: update, validate sources, fetch icons
├── data/
│   ├── raw/                collected items, append-only JSONL, committed
│   ├── services/           per-service digests (generated)
│   ├── changes/            per-run "what's new" markdown (generated)
│   └── state/              cursors, ETags, seen ids
├── site/                   static front end (template + generated JSON)
│   └── assets/icons/       AWS Architecture Icons (SVG)
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
uv run scripts/validate_sources.py      # check every configured source responds
```

More entry points (`update`, `fetch_icons`, `build`) land as the pipeline is built; see the
status section below.

## Status

- [x] Repo, README, CLAUDE.md
- [x] Source registry (`config/sources.yaml`) and validator (18 sources live, X pending a token)
- [ ] Collectors and append-only raw store
- [ ] Service catalog with icons
- [ ] Classifier and per-service digests
- [ ] Static site
- [ ] Scheduled GitHub Actions run with auto-commit
- [ ] Samples

## License

Code is MIT. Digests link to and briefly quote public sources; the original content belongs to
its authors. AWS service icons are © Amazon Web Services and used under AWS's icon terms.
This project is not affiliated with or endorsed by AWS.
