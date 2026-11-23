from app.pipeline.align import align


def w(start, end, word):
    return {"start": start, "end": end, "word": word}


def t(start, end, speaker):
    return {"start": start, "end": end, "speaker": speaker}


def speakers_and_text(segments):
    return [(s["speaker"], s["text"]) for s in segments]


def test_clean_overlap_merges_words_per_speaker():
    words = [w(0.0, 0.4, " Good"), w(0.5, 0.9, " morning."), w(2.0, 2.3, " Hi"), w(2.4, 2.8, " all.")]
    turns = [t(0.0, 1.0, "SPEAKER_00"), t(1.8, 3.0, "SPEAKER_01")]

    segments = align(words, turns)

    assert speakers_and_text(segments) == [
        ("SPEAKER_00", "Good morning."),
        ("SPEAKER_01", "Hi all."),
    ]
    assert (segments[0]["start"], segments[0]["end"]) == (0.0, 0.9)
    assert (segments[1]["start"], segments[1]["end"]) == (2.0, 2.8)


def test_word_straddling_two_turns_goes_to_larger_overlap():
    words = [w(0.8, 1.4, "word")]
    turns = [t(0.0, 1.0, "SPEAKER_00"), t(1.0, 2.0, "SPEAKER_01")]

    assert align(words, turns)[0]["speaker"] == "SPEAKER_01"


def test_word_in_gap_goes_to_nearest_turn():
    words = [w(0.0, 0.5, "one"), w(1.3, 1.5, "two"), w(3.0, 3.5, "three")]
    turns = [t(0.0, 1.0, "SPEAKER_00"), t(2.9, 4.0, "SPEAKER_01")]

    segments = align(words, turns)

    assert speakers_and_text(segments) == [
        ("SPEAKER_00", "one two"),
        ("SPEAKER_01", "three"),
    ]


def test_word_after_last_turn_goes_to_last_speaker():
    words = [w(5.0, 5.4, "late")]
    turns = [t(0.0, 1.0, "SPEAKER_00"), t(1.0, 4.0, "SPEAKER_01")]

    assert align(words, turns)[0]["speaker"] == "SPEAKER_01"


def test_speaker_change_mid_sentence_splits_segment():
    words = [
        w(0.0, 0.3, " So"),
        w(0.35, 0.6, " the"),
        w(0.65, 1.0, " answer"),
        w(1.05, 1.3, " is"),
        w(1.35, 1.8, " forty-two."),
    ]
    turns = [t(0.0, 1.02, "SPEAKER_00"), t(1.02, 2.0, "SPEAKER_01")]

    segments = align(words, turns)

    assert speakers_and_text(segments) == [
        ("SPEAKER_00", "So the answer"),
        ("SPEAKER_01", "is forty-two."),
    ]
    assert segments[0]["end"] <= segments[1]["start"]


def test_pause_longer_than_threshold_starts_new_segment():
    words = [w(0.0, 0.5, "before"), w(2.1, 2.5, "after")]
    turns = [t(0.0, 3.0, "SPEAKER_00")]

    segments = align(words, turns)

    assert speakers_and_text(segments) == [
        ("SPEAKER_00", "before"),
        ("SPEAKER_00", "after"),
    ]


def test_pause_of_exactly_threshold_does_not_split():
    words = [w(0.0, 0.5, "before"), w(2.0, 2.5, "after")]
    turns = [t(0.0, 3.0, "SPEAKER_00")]

    assert speakers_and_text(align(words, turns)) == [("SPEAKER_00", "before after")]


def test_no_turns_puts_everything_under_unknown():
    words = [w(0.0, 0.5, " Hello"), w(0.6, 1.0, " there.")]

    assert speakers_and_text(align(words, [])) == [("UNKNOWN", "Hello there.")]


def test_no_turns_still_splits_on_long_pause():
    words = [w(0.0, 0.5, "one"), w(3.0, 3.5, "two")]

    assert speakers_and_text(align(words, [])) == [("UNKNOWN", "one"), ("UNKNOWN", "two")]


def test_no_words_gives_no_segments():
    assert align([], [t(0.0, 1.0, "SPEAKER_00")]) == []


def test_unsorted_input_and_blank_words():
    words = [w(1.0, 1.4, " world"), w(0.0, 0.4, " hello"), w(0.5, 0.6, "  ")]
    turns = [t(0.0, 2.0, "SPEAKER_00")]

    assert speakers_and_text(align(words, turns)) == [("SPEAKER_00", "hello world")]


def test_segments_are_ordered_and_non_overlapping_when_word_times_overlap():
    words = [w(0.0, 1.0, "a"), w(0.95, 1.5, "b"), w(1.45, 2.0, "c")]
    turns = [t(0.0, 0.97, "SPEAKER_00"), t(0.97, 1.47, "SPEAKER_01"), t(1.47, 2.0, "SPEAKER_00")]

    segments = align(words, turns)

    assert [s["speaker"] for s in segments] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]
    for prev, cur in zip(segments, segments[1:]):
        assert prev["end"] <= cur["start"]
    for seg in segments:
        assert seg["start"] <= seg["end"]
