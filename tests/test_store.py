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


def test_unreadable_line_is_skipped_not_fatal(tmp_path, capsys):
    store = RawStore(tmp_path)
    a = make_item(source="s", key="1", url="u1", title="A", published=datetime(2026, 10, 30, tzinfo=UTC))
    store.add([a])
    with (tmp_path / "s" / "2026-10.jsonl").open("a") as fh:
        fh.write('{"id": "s:cut-off-mid-wri')       # a run killed mid-append
    assert [i["id"] for i in RawStore(tmp_path).all_items()] == [a["id"]]
    assert "unreadable line skipped" in capsys.readouterr().err
    b = make_item(source="s", key="2", url="u2", title="B", published=datetime(2026, 10, 30, tzinfo=UTC))
    RawStore(tmp_path).add([b])                     # starts on a fresh line, so b survives
    assert [i["id"] for i in RawStore(tmp_path).all_items()] == [a["id"], b["id"]]
