"""Eye-contact score from the per-look letters (Day 19)."""
from app.services import eye_contact as ec

FPS = 5


def test_all_on_screen_is_full_eye_contact():
    r = ec.analyse("S" * 50 + "B" * 3 + "S" * 20, FPS)
    assert r["eye_contact_pct"] == 100 and r["label"] == "good" and r["away"] == []


def test_short_thinking_glances_are_fine():
    codes = ("S" * 20 + "u" * 5) * 6                    # 1 s glances up every 4 s
    assert ec.analyse(codes, FPS)["eye_contact_pct"] == 100


def test_long_look_away_is_logged_with_time_and_direction():
    codes = "S" * 50 + "d" * 20 + "S" * 30              # 10 s, then 4 s down, then 6 s
    r = ec.analyse(codes, FPS)
    assert r["eye_contact_pct"] == 80 and r["away_count"] == 1
    assert r["away"][0] == {"at": 10.0, "seconds": 4.0, "where": "down", "kind": "eyes"}


def test_brief_return_to_screen_does_not_split_a_look_away():
    codes = "S" * 25 + "d" * 8 + "S" * 2 + "d" * 8 + "S" * 25      # 0.4 s back at the screen
    r = ec.analyse(codes, FPS)
    assert r["away_count"] == 1 and r["away"][0]["seconds"] == 3.6


def test_head_turns_out_of_view_other_person_and_tips():
    codes = "S" * 20 + "L" * 15 + "S" * 10 + "N" * 20 + "S" * 10 + "M" * 15 + "S" * 10
    r = ec.analyse(codes, FPS)
    kinds = {(e["where"], e["kind"]) for e in r["away"]}
    assert ("left", "head") in kinds and ("out of view", "face") in kinds
    assert r["face_missing_seconds"] == 4.0 and r["other_person_seconds"] == 3.0
    assert r["eye_contact_pct"] == 50 and r["label"] == "fair" and any("out of view" in t for t in r["tips"])
    assert any("Another person" in t for t in r["tips"])


def test_looking_down_often_tip_and_bad_input():
    codes = ("S" * 15 + "d" * 12) * 3
    assert any("looked down 3 times" in t for t in ec.analyse(codes, FPS)["tips"])
    assert ec.analyse("", FPS)["eye_contact_pct"] is None
    assert ec.analyse("xyz<>!0", FPS)["eye_contact_pct"] is None
    assert ec.analyse("S" * 10, 999)["seconds"] == round(10 / ec.MAX_FPS, 1)
