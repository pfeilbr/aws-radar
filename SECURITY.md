# Security

AWS Radar is a static site built from public feeds. It has no server, no user accounts and
no stored personal data. The parts worth protecting are the GitHub Actions workflows (they
hold a token that can push to `main`) and the site's visitors (it renders third-party text).

## Reporting

Please report a vulnerability privately through
[GitHub security advisories](https://github.com/pfeilbr/aws-radar/security/advisories/new),
not in a public issue.

## Safeguards in place

- **Workflows**: actions pinned to full commit SHAs (Dependabot updates them), least-privilege
  `permissions` per workflow, read-only jobs check out without persisted credentials, every
  job has a timeout. Dependabot PRs auto-merge only when CI passes, the branch is in this
  repository, and every commit on it is Dependabot's.
- **Secrets**: none in the repository. Tokens come from environment variables named by
  `auth_env` in `config/sources.yaml`; a test rejects inline secret keys there. `.env` is
  git-ignored.
- **Site**: all feed text is HTML-escaped; links from feed data must be `http(s)`; a
  Content-Security-Policy allows only the site's own scripts (inline theme snippet by hash,
  checked by `tests/test_site.py`).
- **Feeds out**: Atom links are attribute-escaped and limited to `http(s)`.
- **Fetching**: stdlib HTTP with a descriptive User-Agent, conditional GETs and per-host
  spacing; nothing behind a login is fetched.
