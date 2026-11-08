"""Learn which skills each job role needs from real job postings (ATS Layer 2).

Usage (from the backend folder, venv active):
    python scripts/build_market_model.py                 # all postings in data/raw/
    python scripts/build_market_model.py --limit 5000    # quick trial run

Input : any CSV(s) of job postings under data/raw/ with a title and a description
        column (column names are detected automatically). Re-run it whenever new
        postings are added; the model is rebuilt from scratch, no code changes.
Output: data/market_model.json       roles → learned skill weights (used by the app)
        data/market_candidates.json  frequent tech-looking terms that are NOT in
                                     skills.json yet (to grow the dictionary)
"""
import argparse
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR  # noqa: E402
from app.services.entity_extractor import find_skills_batch  # noqa: E402
from app.services.market_model import MODEL_PATH, normalize_title  # noqa: E402

RAW_DIR = DATA_DIR / "raw"
CANDIDATES_PATH = DATA_DIR / "market_candidates.json"
TITLE_COLS = ["title", "job_title", "position", "job_position"]
DESC_COLS = ["description", "job_description", "jobdescription", "desc"]
EXTRA_COLS = ["skills_desc", "job_skills", "skills"]
TIME_COLS = ["listed_time", "original_listed_time", "post_date", "posted_date", "date_posted", "first_seen"]
TECH_TERM_RE = re.compile(r"(?<![\w.])(?:[A-Za-z][A-Za-z0-9]*(?:[.+#][A-Za-z0-9+#]+)+|[A-Z][a-z]+[A-Z][A-Za-z0-9]+)(?![\w])")


def _pick(columns, candidates):
    low = {c.lower(): c for c in columns}
    return next((low[c] for c in candidates if c in low), None)


def find_posting_files() -> list[Path]:
    """CSV files that look like job postings (have a title and a description column)."""
    files = []
    for p in sorted(RAW_DIR.rglob("*.csv")):
        try:
            cols = pd.read_csv(p, nrows=0).columns
        except Exception:
            continue
        if _pick(cols, TITLE_COLS) and _pick(cols, DESC_COLS):
            files.append(p)
    return files


def load_postings(files: list[Path], limit: int | None) -> pd.DataFrame:
    frames = []
    for p in files:
        cols = pd.read_csv(p, nrows=0).columns
        title, desc = _pick(cols, TITLE_COLS), _pick(cols, DESC_COLS)
        extra, when = _pick(cols, EXTRA_COLS), _pick(cols, TIME_COLS)
        use = [c for c in (title, desc, extra, when) if c]
        df = pd.read_csv(p, usecols=use, dtype=str, nrows=limit)
        df = df.rename(columns={title: "title", desc: "description", **({extra: "extra"} if extra else {}),
                                **({when: "when"} if when else {})})
        df["source"] = p.name
        frames.append(df)
        print(f"  {p.relative_to(RAW_DIR)}: {len(df):,} postings  (title='{title}', description='{desc}'"
              f"{f', extra={extra!r}' if extra else ''}{f', date={when!r}' if when else ''})")
    df = pd.concat(frames, ignore_index=True)
    for c in ("extra", "when"):
        if c not in df:
            df[c] = None
    df = df.dropna(subset=["title", "description"])
    df = df.drop_duplicates(subset=["title", "description"])
    return df


def parse_when(series: pd.Series) -> pd.Series:
    """Posting dates: epoch milliseconds (LinkedIn dataset) or date strings."""
    num = pd.to_numeric(series, errors="coerce")
    if num.notna().mean() > 0.5:
        unit = "ms" if num.median() > 1e11 else "s"
        return pd.to_datetime(num, unit=unit, errors="coerce", utc=True)
    return pd.to_datetime(series, errors="coerce", utc=True)


def known_aliases() -> set[str]:
    vocab = json.loads((DATA_DIR / "skills.json").read_text(encoding="utf-8"))
    return {a.lower() for cat, entries in vocab.items() if not cat.startswith("_")
            for e in entries for a in e.lstrip("!").split("|")}


def build(limit: int | None, min_postings: int, half_life_days: float, top_k: int) -> dict:
    t0 = time.time()
    files = find_posting_files()
    if not files:
        sys.exit(f"No job-posting CSVs found under {RAW_DIR}. See ROADMAP Day 8.")
    print("Reading postings:")
    df = load_postings(files, limit)
    df["role"] = df["title"].map(normalize_title)
    counts = df["role"].value_counts()
    roles = counts[(counts >= min_postings) & (counts.index.str.len() >= 3)].index
    df = df[df["role"].isin(roles)].reset_index(drop=True)
    print(f"{len(df):,} postings in {len(roles):,} roles with ≥{min_postings} postings")

    # Newer postings count more: weight halves every `half_life_days`
    when = parse_when(df["when"])
    newest = when.max()
    if pd.notna(newest):
        age = (newest - when).dt.days.fillna((newest - when).dt.days.median()).clip(lower=0)
        df["w"] = 0.5 ** (age / half_life_days)
    else:
        df["w"] = 1.0

    # 1. find skills in every posting
    texts = (df["title"] + "\n" + df["description"].str[:6000] + "\n" + df["extra"].fillna("")).tolist()
    role_w = defaultdict(float)
    skill_w = defaultdict(lambda: defaultdict(float))
    skill_n = defaultdict(Counter)
    categories = {}
    aliases, term_df = known_aliases(), Counter()
    for i, found in enumerate(find_skills_batch(texts)):
        role, w = df.at[i, "role"], df.at[i, "w"]
        role_w[role] += w
        for skill, cat in found.items():
            skill_w[role][skill] += w
            skill_n[role][skill] += 1
            categories[skill] = cat
        term_df.update({t for t in TECH_TERM_RE.findall(texts[i]) if t.lower() not in aliases})
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1:,}/{len(texts):,} postings scanned ({time.time() - t0:.0f}s)")

    # 2. freq per role, then IDF across roles
    freq = {r: {s: skill_w[r][s] / role_w[r] for s in skill_w[r] if skill_n[r][s] >= 3} for r in role_w}
    n_roles = len(freq)
    common_in = Counter(s for r in freq for s, f in freq[r].items() if f >= 0.05)
    idf = {s: math.log((1 + n_roles) / (1 + common_in[s])) + 1 for s in categories}

    out_roles, dropped = {}, 0
    for r, fs in freq.items():
        scored = [(s, f, f * idf[s]) for s, f in fs.items() if f >= 0.03]
        if len(scored) < 5:           # too few known skills to say anything useful
            dropped += 1
            continue
        scored.sort(key=lambda x: -x[2])
        top = scored[:top_k]
        mx = top[0][2]
        cat_votes = Counter()
        for s, f, sc in top[:10]:
            if categories[s] != "soft_skills":
                cat_votes[categories[s]] += sc
        out_roles[r] = {
            "postings": int(counts[r]),
            "category": cat_votes.most_common(1)[0][0] if cat_votes else "soft_skills",
            "skills": [{"name": s, "category": categories[s], "freq": round(f, 3), "weight": round(sc / mx, 3)}
                       for s, f, sc in top],
        }

    candidates = [{"term": t, "postings": n} for t, n in term_df.most_common(300) if n >= 20][:150]
    model = {
        "version": "market-v1",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sorted(df["source"].unique().tolist()),
        "postings_used": int(len(df)),
        "data_from": when.min().date().isoformat() if pd.notna(when.min()) else None,
        "data_to": newest.date().isoformat() if pd.notna(newest) else None,
        "half_life_days": half_life_days,
        "min_postings_per_role": min_postings,
        "roles": dict(sorted(out_roles.items(), key=lambda kv: -kv[1]["postings"])),
    }
    MODEL_PATH.write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf-8")
    CANDIDATES_PATH.write_text(json.dumps(candidates, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone in {time.time() - t0:.0f}s: {len(out_roles):,} roles saved "
          f"({dropped} dropped: <5 known skills). Data {model['data_from']} → {model['data_to']}")
    print(f"Saved {MODEL_PATH.name} ({MODEL_PATH.stat().st_size / 1e6:.1f} MB) and "
          f"{CANDIDATES_PATH.name} ({len(candidates)} unknown-term candidates)")
    return model


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="read only the first N rows of each file (trial run)")
    ap.add_argument("--min-postings", type=int, default=30, help="roles need at least this many postings")
    ap.add_argument("--half-life-days", type=float, default=365, help="a posting this old counts half")
    ap.add_argument("--top-k", type=int, default=40, help="skills kept per role")
    a = ap.parse_args()
    build(a.limit, a.min_postings, a.half_life_days, a.top_k)
