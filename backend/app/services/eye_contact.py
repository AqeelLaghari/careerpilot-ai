"""Eye-contact score for one spoken answer (Day 19).

The app looks at the face tracker (web/face_tracker.js) a few times a second while the user
answers and writes ONE letter per look (the video itself never leaves the browser):
    S  looking at the screen         B  blink (counts as looking)
    l r u d   eyes turned left / right / up / down
    L R U D   head turned left / right / up / down
    N  no face in view               M  more than one face
Example at 5 looks per second: "SSSSSSddddddddddSSSS" = 4 s of answer, 2 s looking down.

Scoring rules (what interview coaches teach):
  - Short glances away (under GRACE seconds) are normal while thinking: they count as eye contact.
  - Looking at the screen between two look-aways for under BRIDGE seconds doesn't split them.
  - Eye contact % = time looking at the screen / whole answer. Out of view counts as away.
  - Every look-away of AWAY_LOG seconds or more goes in the log: when, how long, which way.
"""
from collections import Counter

GRACE = 1.5          # s: a glance shorter than this is fine
BRIDGE = 0.6         # s: a moment back at the screen shorter than this doesn't end a look-away
AWAY_LOG = 2.0       # s: look-aways at least this long are listed
GOOD, FAIR = 70, 50  # % eye contact
LOOKING = {"S", "B"}
WHERE = {"l": "left", "r": "right", "u": "up", "d": "down", "L": "left", "R": "right", "U": "up", "D": "down",
         "N": "out of view", "M": "another person in view"}
VALID = set("SBlrudLRUDNM")
MAX_FPS = 30


def _runs(codes: str) -> list[list]:
    """'SSdd' -> [['S', 0, 2], ['d', 2, 2]]  (code, start index, length); look-aways merged."""
    out = []
    for i, c in enumerate(codes):
        away = c not in LOOKING
        if out and out[-1][3] == away:
            out[-1][2] += 1
            if away:
                out[-1][4][c] += 1
        else:
            out.append([c, i, 1, away, Counter({c: 1}) if away else None])
    return out


def analyse(codes: str, fps: float) -> dict:
    codes = "".join(c for c in str(codes or "") if c in VALID)
    fps = max(1.0, min(float(fps or 5), MAX_FPS))
    if not codes:
        return {"eye_contact_pct": None, "label": "no camera data", "away": [], "tips": [], "seconds": 0}
    total = len(codes) / fps
    runs = _runs(codes)
    # a short look back at the screen between two look-aways doesn't split them
    merged = []
    for r in runs:
        if (len(merged) >= 2 and r[3] and not merged[-1][3] and merged[-1][2] / fps < BRIDGE
                and merged[-2][3]):
            screen = merged.pop()
            prev = merged[-1]
            prev[2] += screen[2] + r[2]
            prev[4].update(r[4])
        else:
            merged.append([r[0], r[1], r[2], r[3], Counter(r[4]) if r[4] else None])
    away_time, events = 0.0, []
    for code, start, length, away, kinds in merged:
        secs = length / fps
        if not away or secs < GRACE:
            continue                              # looking, or just a thinking glance
        away_time += secs
        main = kinds.most_common(1)[0][0]
        if secs >= AWAY_LOG:
            events.append({"at": round(start / fps, 1), "seconds": round(secs, 1), "where": WHERE[main],
                           "kind": "head" if main.isupper() and main not in "NM" else
                                   ("eyes" if main.islower() else "face")})
    pct = round(100 * (1 - away_time / total)) if total else None
    counts = Counter(codes)
    missing = round(counts["N"] / fps, 1)
    others = round(counts["M"] / fps, 1)
    label = "good" if pct >= GOOD else ("fair" if pct >= FAIR else "needs work")

    tips = []
    if pct >= GOOD:
        tips.append("Good eye contact. Keep looking at the camera area while you speak.")
    else:
        tips.append("Look at the camera (or the middle of the screen) more; it feels like looking the interviewer in the eye.")
    by_way = Counter(e["where"] for e in events)
    if by_way.get("down", 0) >= 2:
        tips.append(f"You looked down {by_way['down']} times. If you read notes, keep them near the camera.")
    if by_way.get("left", 0) + by_way.get("right", 0) >= 2:
        tips.append("You often looked to the side. Close other windows so nothing pulls your eyes away.")
    if missing >= 3:
        tips.append(f"Your face was out of view for {missing:.0f} s. Sit centred and keep still.")
    if others >= 2:
        tips.append("Another person was in view. Interview alone, in a quiet room.")
    return {"eye_contact_pct": pct, "label": label, "seconds": round(total, 1), "looked_away_seconds": round(away_time, 1),
            "away": events[:15], "away_count": len(events),
            "longest_away": max((e["seconds"] for e in events), default=0),
            "face_missing_seconds": missing, "other_person_seconds": others, "tips": tips}
