from conftest import FIXTURES, FakeResponse

from radar.collectors import botocore, github_issues, rss


def test_rss_whats_new(ctx_factory):
    src = {"id": "aws-whats-new", "url": "https://example/feed"}
    ctx = ctx_factory({"example/feed": FakeResponse((FIXTURES / "whats-new.xml").read_bytes())})
    items = rss.collect(src, ctx)
    assert [i["title"][:20] for i in items] == ["Amazon DynamoDB Acce", "Amazon EKS Auto Mode"]
    assert "general:products/amazon-dynamodb" in items[0]["tags_raw"]   # comma list split
    assert items[0]["summary"].startswith("Today, we are excited")        # raw keeps source text
    assert items[0]["published"] == "2026-10-28T17:00:00Z"


def test_botocore_changelog_cursor(ctx_factory):
    src = {"id": "botocore-changelog", "url": "https://example/CHANGELOG.rst", "backfill_days": 100000}
    pypi = {"files": [{"filename": "botocore-1.43.123.tar.gz", "upload-time": "2026-10-30T19:18:44Z"},
                      {"filename": "botocore-1.43.122.tar.gz", "upload-time": "2026-10-29T19:00:00Z"}]}
    routes = {"CHANGELOG": FakeResponse((FIXTURES / "botocore-CHANGELOG.rst").read_bytes()),
              "pypi.org": FakeResponse(b"", payload=pypi)}
    ctx = ctx_factory(routes)
    items = botocore.collect(src, ctx)
    assert [i["extra"]["sdk_service"] for i in items] == ["lambda", "s3control", "bedrock-agentcore", "endpoint-rules"]
    assert items[1]["summary"] == "Adds a new API."                       # [``botocore``] prefix dropped
    assert items[0]["published"] == "2026-10-30T19:18:44Z"
    assert ctx.state["last_version"] == "1.43.123"
    # Next run with the cursor at the newest version: nothing new.
    assert botocore.collect(src, ctx_factory(routes, state=dict(ctx.state))) == []


def test_github_issues_keyed_by_label(ctx_factory):
    src = {"id": "rm", "url": "https://api.github.com/x?page={page}", "label": "Shipped", "state": "closed"}
    issue = {"number": 7, "html_url": "https://github.com/x/7", "title": "[ECS] thing", "body": "b",
             "labels": [{"name": "ECS"}, {"name": "Shipped"}], "created_at": "2026-01-01T00:00:00Z",
             "closed_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-02T00:00:00Z"}
    items = github_issues.collect(src, ctx_factory({"api.github.com": FakeResponse(b"", payload=[issue])}))
    assert items[0]["published"] == "2026-02-01T00:00:00Z"
    assert items[0]["tags_raw"] == ["ECS", "Shipped"]
