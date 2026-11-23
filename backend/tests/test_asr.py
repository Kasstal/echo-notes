from app.pipeline import asr


def w(start, end, word="x"):
    return {"start": start, "end": end, "word": word}


def test_fully_covered_span_is_not_a_gap():
    words = [w(0.0, 0.5), w(0.5, 1.2), w(1.2, 2.0)]
    assert asr.uncovered_spans([(0.0, 2.0)], words) == []


def test_span_with_no_words_is_a_gap():
    words = [w(0.0, 1.0), w(1.0, 2.0)]
    assert asr.uncovered_spans([(0.0, 2.0), (2.5, 6.0)], words) == [(2.5, 6.0)]


def test_only_the_wordless_part_of_a_span_is_a_gap():
    # Re-transcribing the whole span would duplicate the word that is already there.
    assert asr.uncovered_spans([(10.0, 14.0)], [w(13.5, 14.0)]) == [(10.0, 13.5)]


def test_gaps_between_words_in_one_long_span():
    # Short pauses make VAD merge a Russian, English, Russian, English exchange into one span;
    # the English replies show up as holes between the recognized Russian words.
    words = [w(0.0, 3.0), w(3.0, 5.96), w(10.88, 13.0), w(13.0, 16.52)]
    assert asr.uncovered_spans([(0.0, 21.54)], words) == [(5.96, 10.88), (16.52, 21.54)]


def test_gap_at_the_start_of_a_span():
    assert asr.uncovered_spans([(2.0, 8.0)], [w(5.0, 8.0)]) == [(2.0, 5.0)]


def test_short_pauses_between_words_are_not_gaps():
    words = [w(0.0, 1.0), w(1.6, 2.5), w(3.3, 4.0)]
    assert asr.uncovered_spans([(0.0, 4.0)], words) == []


def test_overlapping_word_timestamps():
    words = [w(0.0, 3.0), w(2.5, 2.8), w(4.5, 5.0)]
    assert asr.uncovered_spans([(0.0, 5.0)], words) == [(3.0, 4.5)]


def test_short_spans_are_ignored():
    assert asr.uncovered_spans([(3.0, 3.6)], []) == []


def test_words_outside_the_span_do_not_count():
    words = [w(0.0, 5.0), w(9.0, 12.0)]
    assert asr.uncovered_spans([(5.0, 9.0)], words) == [(5.0, 9.0)]
