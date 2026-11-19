from backend.clip_generation.selector import select_clips


def H(s, e, score):
    return {"start": s, "end": e, "score": score, "title": f"t{s}", "duration": e - s}


def test_best_first_and_no_overlap():
    hl = [H(0, 30, 90), H(20, 50, 80), H(60, 90, 70)]
    out = select_clips(hl, count=5)
    assert [c["start"] for c in out] == [0, 60]
    for a in out:
        for b in out:
            if a is not b:
                assert a["end"] <= b["start"] or a["start"] >= b["end"]


def test_count_and_min_score():
    hl = [H(0, 30, 90), H(40, 70, 60), H(80, 110, 20)]
    assert len(select_clips(hl, count=1)) == 1
    assert len(select_clips(hl, min_score=50)) == 2


def test_padding_clamped_to_video():
    out = select_clips([H(1, 30, 80)], pad_before=3, pad_after=5, duration=32)
    assert out[0]["start"] == 0.0
    assert out[0]["end"] == 32.0


def test_blocked_ranges_are_skipped():
    out = select_clips([H(0, 30, 90), H(60, 90, 70)], blocked=[(0, 30)])
    assert [c["start"] for c in out] == [60]


def test_too_short_and_too_long():
    assert select_clips([H(0, 3, 99)], min_len=5) == []
    out = select_clips([H(0, 200, 99)], max_len=60)
    assert out[0]["duration"] == 60.0