from datetime import UTC, datetime

from radar.store import RawStore, make_item


def test_add_dedupes_and_appends(tmp_path):
    store = RawStore(tmp_path)
    when = datetime(2026, 10, 30, tzinfo=UTC)
    a = make_item(source="s", key="1", url="u1", title="A", published=when)
    b = make_item(source="s", key="2", url="u2", title="B", published=when)
    assert len(store.add([a, b])) == 2
    assert store.add([a]) == []                      # same id again: skipped
    fresh = RawStore(tmp_path)                       # re-reads ids from disk
    assert fresh.add([a]) == []
    assert (tmp_path / "s" / "2026-10.jsonl").read_text().count("\n") == 2
    assert {i["id"] for i in fresh.all_items()} == {a["id"], b["id"]}
