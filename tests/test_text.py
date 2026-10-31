from radar.text import first_sentences, html_to_text, strip_filler


def test_html_to_text_strips_tags_and_entities():
    assert html_to_text("<p>A&nbsp;&amp; B</p>\n<p>C</p>") == "A & B C"


def test_strip_filler_removes_marketing_openers():
    assert strip_filler("Today, we are excited to announce that DAX is now in Tokyo.") == "DAX is now in Tokyo."
    assert strip_filler("We're pleased to announce the general availability of X.") == "X."
    assert strip_filler("Starting today, you can use Y.") == "You can use Y."


def test_first_sentences_keeps_whole_sentences():
    text = "First sentence here. Second one is a bit longer. Third."
    assert first_sentences(text, 30) == "First sentence here."
    assert first_sentences("x" * 50, 20).endswith("…")
