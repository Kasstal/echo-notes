import numpy as np

from app.pipeline.diarize import merge_speakers


def turn(start, end, speaker):
    return {"start": start, "end": end, "speaker": speaker}


def unit(angle_deg):
    a = np.radians(angle_deg)
    return np.array([np.cos(a), np.sin(a), 0.0])


def speakers(turns):
    return sorted({t["speaker"] for t in turns})


def test_merges_near_identical_voices_into_the_longer_speaker():
    turns = [turn(0, 10, "A"), turn(10, 12, "B"), turn(12, 20, "A")]
    # 30 degrees apart: cosine distance 0.13
    merged = merge_speakers(turns, {"A": unit(0), "B": unit(30)})
    assert speakers(merged) == ["A"]
    assert [t["start"] for t in merged] == [0, 10, 12]


def test_keeps_different_voices_apart():
    turns = [turn(0, 10, "A"), turn(10, 20, "B")]
    # 90 degrees apart: cosine distance 1.0
    assert speakers(merge_speakers(turns, {"A": unit(0), "B": unit(90)})) == ["A", "B"]


def test_folds_a_speaker_with_almost_no_speech_into_the_nearest_voice():
    turns = [turn(0, 10, "A"), turn(10, 20, "B"), turn(20, 20.5, "C")]
    merged = merge_speakers(turns, {"A": unit(0), "B": unit(90), "C": unit(80)})
    assert speakers(merged) == ["A", "B"]
    assert merged[-1]["speaker"] == "B"


def test_never_goes_below_the_requested_minimum():
    turns = [turn(0, 10, "A"), turn(10, 12, "B")]
    merged = merge_speakers(turns, {"A": unit(0), "B": unit(10)}, keep_at_least=2)
    assert speakers(merged) == ["A", "B"]


def test_speaker_without_a_usable_embedding_is_left_alone():
    turns = [turn(0, 10, "A"), turn(10, 10.4, "B")]
    merged = merge_speakers(turns, {"A": unit(0), "B": np.array([np.nan, 0.0, 0.0])})
    assert speakers(merged) == ["A", "B"]
