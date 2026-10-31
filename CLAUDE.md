# CLAUDE.md

Guidance for Claude (and any other agent) working in this repository.

## What this repo is

AWS Radar keeps an expert-level, per-service digest of everything new in AWS. Python scripts
collect from AWS blogs, What's New, changelogs, Reddit, Hacker News and social feeds, map items
to services, write JSON/Markdown digests, build a static site, and commit the result.
See `README.md` for the pipeline diagram and layout.

The audience is Brian, an AWS expert who knows every service. Write accordingly.

## Hard rules

1. **No LLM calls in the pipeline.** Collectors, classifier, digest and site builder are plain,
   deterministic Python. Do not add a dependency on Claude, OpenAI, Bedrock or any model API
   to anything under `radar/` or `scripts/`. If a task seems to need summarization, use the
   source's own title/summary, truncate, and tag with rules.
2. **Never throw away collected data.** `data/raw/` is append-only. Never rewrite or delete
   existing lines; dedupe on write by item id. Before fetching, check state so already-seen
   items are not re-fetched. Re-derive generated files (`data/services/`, `data/changes/`,
   `site/data/`) from raw, never the other way round.
3. **Every source lives in `config/sources.yaml`.** No URLs hardcoded in collectors. A new
   source is a YAML entry plus, only if its format is new, a collector module.
4. **The site stays static.** Plain HTML, CSS, vanilla JS, pre-built JSON. No framework, no
   bundler, no server. It must work from GitHub Pages and from `file://`.
5. **Public repo.** Commit nothing secret. Tokens (X, optional GitHub) come from environment
   variables named in `sources.yaml` (`auth_env`). Never commit `.env`.

## Digest style

- One line per item: `YYYY-MM-DD · [tags] · title-or-first-sentence · source link`.
- Tags come from rules: `GA`, `preview`, `region`, `pricing`, `deprecation`, `security`,
  `quota`, `feature`, `sdk`, `community`. Keep the rule table in `radar/classify.py`.
- Strip marketing filler ("We are excited to announce", "today, we're pleased to"). Keep
  service names, API names, regions and numbers.
- Do not explain what a service is.

## Conventions

- Python 3.12+, managed with `uv`. Dependencies in `pyproject.toml`. Prefer the standard
  library; current deps are `httpx`, `feedparser`, `pyyaml`.
- Item schema (one JSON object per line in `data/raw/<source_id>/<YYYY-MM>.jsonl`):
  `id` (stable: source id + guid/url hash), `source`, `url`, `title`, `summary`,
  `published` (ISO 8601 UTC), `fetched`, `authors`, `tags_raw` (whatever the source gave us),
  `services` and `tags` (filled by the classifier).
- Service ids are lowercase slugs matching `config/services.yaml` (`s3`, `lambda`, `bedrock`,
  `ec2`, ...). Icons live in `site/assets/icons/<service-id>.svg`.
- Be polite to sources: send a descriptive User-Agent, honour ETag/Last-Modified, keep request
  rates low, and never scrape anything that needs a login.
- Samples go in `samples/<service-id>/<language>/<short-name>/`, each with its own README
  stating what it shows, how to run it, and what AWS resources (and cost) it creates.

## Commands

```bash
uv run scripts/validate_sources.py            # hit every source, report status
uv run scripts/validate_sources.py --only aws-whats-new
```

When adding commands, list them here and in the README.

## Git

- The scheduled update job commits with a message like `data: update 2026-10-31 (+42 items)`.
- Hand-made changes use normal descriptive commits. Do not mix pipeline data and code changes
  in one commit.
