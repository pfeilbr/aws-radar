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
   items are not re-fetched. Re-derive generated files (`data/services/`, `site/data/`,
   `config/services.yaml`) from their inputs, never the other way round. Raw items hold only
   what the source said; services and tags are computed at build time so rule changes apply
   to history.
3. **Every source lives in `config/sources.yaml`.** No URLs hardcoded in collectors. A new
   source is a YAML entry plus, only if its format is new, a collector module.
4. **The site stays static.** Plain HTML, CSS, vanilla JS, pre-built data as `.js` files. No framework, no
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
  library; current deps are `feedparser` and `pyyaml`. HTTP goes through `radar/http.py`
  (stdlib urllib): do not switch it to httpx/requests, Reddit blocks httpx from CI runners.
- Item schema (one JSON object per line in `data/raw/<source_id>/<YYYY-MM>.jsonl`):
  `id` (`<source>:<sha1 of guid>`), `source`, `url`, `title`, `summary` (plain text),
  `published` and `fetched` (ISO 8601 UTC), `authors`, `tags_raw` (whatever the source
  gave us), `extra` (source-specific: points, sdk_service, video_id, ...).
- Service ids are short slugs (`s3`, `lambda`, `bedrock`, `ecs`). `config/services.yaml` is
  generated: change ids, aliases and keywords in `config/service_overrides.yaml`, then run
  `scripts/build_catalog.py --report` and check the unmatched list. Icons live in
  `site/assets/icons/services/<id>.svg`.
- Classification (`radar/classify.py`) returns primary services (the item is about them)
  and mentions (tagged or named in passing). Service pages show primary by default.
- A source failing must never stop a run: collectors raise, `radar/collect.py` records the
  error in `data/state/<source>.json` and moves on.
- Be polite to sources: send a descriptive User-Agent, honour ETag/Last-Modified, keep request
  rates low, and never scrape anything that needs a login.
- Samples go in `samples/<service-id>/<language>/<short-name>/`, each with a README copied
  from `samples/_template/README.md` (what it shows, how to run, resources, cost, cleanup,
  last run date). Add new samples to the table in `samples/README.md`; the build links them
  from the service page automatically. Do not run samples that create billable resources
  without asking Brian.
- New collector types need a fixture-based test in `tests/test_collectors.py`.
- Workflows: pin every action to a full commit SHA with a `# vX.Y.Z` comment, give each job a
  `timeout-minutes`, keep `permissions` minimal, and check out with
  `persist-credentials: false` unless the job pushes. `UV_LOCKED=1` is set, so update
  `uv.lock` (`uv lock`) whenever `pyproject.toml` changes.
- Site security: build links from feed data with `safeUrl()` (http(s) only) and text with
  `esc()`. `site/index.html` has a Content-Security-Policy; if you edit its inline script,
  update the `sha256-` hash (`tests/test_site.py` fails until you do). No inline `on*=`
  handlers.
- Writes that must not be half-done (state files) go to a temp file and `os.replace`.
  Raw JSONL is only ever appended to.
- `Catalog.match_text` skips a regex when its literal prefix is absent from the text. Keyword
  regexes still work as before; one starting with a group or a top-level `|` just isn't
  prefiltered.

## Commands

```bash
uv run scripts/update.py                      # collect due sources + rebuild
uv run scripts/update.py --force --only aws-blogs
uv run scripts/update.py --build-only         # after changing rules, catalog or the site
uv run scripts/update.py --commit --push      # what the scheduled workflow runs
uv run scripts/validate_sources.py            # hit every source, report status
uv run scripts/build_catalog.py --report      # icons + catalog, list unmatched names
uv run pytest -q && uv run ruff check .       # must pass before pushing code (CI runs both)
uv run scripts/health_issues.py --dry-run     # what the failing-source issue step would do
python3 -m http.server -d site 8765           # preview the site
```

Generated outputs (never hand-edit; rebuilt by `build.py` from `data/raw`): `site/data/`,
`site/feeds/`, `data/services/`, `data/weekly/`, `data/changes/`,
`data/reports/catalog-gaps.md`. When the gaps report lists a real service, add an alias in
`config/service_overrides.yaml`; when it lists a topic, add it to `ignore_tags`.

Reddit rate-limits hard (429). When testing, use `--only` and avoid re-polling Reddit.

When adding commands, list them here and in the README.

## Git

- The scheduled update job commits with a message like `data: update 2026-10-31 (+42 items)`.
- Hand-made changes use normal descriptive commits. Do not mix pipeline data and code changes
  in one commit.
- Work in small commits straight on `main` and push each one; no long-lived branches or PRs
  (Brian, 2026-11-02).
- **Always merge Dependabot PRs** (Brian's standing rule). `.github/workflows/dependabot-merge.yml`
  merges them when CI passes. If one is still open (e.g. an Actions update without the
  `DEPENDABOT_MERGE_TOKEN` secret), merge it with `gh pr merge <n> --squash --delete-branch`
  once its CI is green, then pull.
