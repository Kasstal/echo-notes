from app.pipeline import asr


def w(start, end, word="x"):
    return {"start": start, "end": end, "word": word}


def test_fully_covered_span_is_not_a_gap():
    words = [w(0.0, 0.5), w(0.5, 1.2), w(1.2, 2.0)]
    assert asr.uncovered_spans([(0.0, 2.0)], words) == []


def test_span_with_no_words_is_a_gap():
    words = [w(0.0, 1.0), w(1.0, 2.0)]
    assert asr.uncovered_spans([(0.0, 2.0), (2.5, 6.0)], words) == [(2.5, 6.0)]


def test_mostly_empty_span_is_a_gap():
    # 0.5 s of words in a 4 s span: 12.5% covered.
    assert asr.uncovered_spans([(10.0, 14.0)], [w(13.5, 14.0)]) == [(10.0, 14.0)]


def test_short_spans_are_ignored():
    assert asr.uncovered_spans([(3.0, 3.6)], []) == []


def test_words_outside_the_span_do_not_count():
    words = [w(0.0, 5.0), w(9.0, 12.0)]
    assert asr.uncovered_spans([(5.0, 9.0)], words) == [(5.0, 9.0)]
