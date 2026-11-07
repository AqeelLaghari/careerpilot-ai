"""Run every CV in evaluation/resumes/ through the full pipeline and print a summary table.

Usage (from the backend folder, venv active):
    python scripts/batch_test.py

Privacy: the table shows only file names, counts and yes/no flags, never names,
emails or phone numbers, so it is safe to paste into chat.
Full per-CV details are saved to evaluation/resumes/_results.json (git-ignored).
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.ats_scorer import score_resume  # noqa: E402
from app.services.entity_extractor import extract_entities  # noqa: E402
from app.services.pdf_parser import PDFError, extract_pdf  # noqa: E402

CV_DIR = ROOT.parent / "evaluation" / "resumes"


def flags_for(parsed: dict, ent: dict) -> list[str]:
    """Signs that the parser may have struggled with this CV."""
    f, sec, lay = [], parsed["sections"], parsed["layout"]
    if lay["is_scanned"]:
        f.append("SCANNED")
    if len([s for s in sec if s != "header"]) < 2:
        f.append("few-sections")
    if not ent["name"]:
        f.append("no-name")
    if not parsed["contact"]["email"]:
        f.append("no-email")
    if len(ent["skills"]) < 5:
        f.append("few-skills")
    if "experience" in sec and not ent["experience"]:
        f.append("exp-not-parsed")
    if "education" in sec and not ent["education"]:
        f.append("edu-not-parsed")
    if "education" not in sec:
        f.append("no-edu-heading")
    if len(sec.get("header", "").split()) > 120:
        f.append("big-header(missed-heading?)")
    if ent["llm_filled"]:
        f.append("gemini:" + "+".join(ent["llm_filled"]))
    return f


def main():
    pdfs = sorted(CV_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {CV_DIR}. Put some resumes there first.")

    rows, details, all_flags = [], {}, Counter()
    t0 = time.time()
    for pdf in pdfs:
        try:
            parsed = extract_pdf(pdf.read_bytes())
        except PDFError as e:
            rows.append((pdf.name, "-", "-", "-", "-", "-", "-", "-", f"ERROR: {e}"))
            continue
        ent = extract_entities(parsed["sections"], parsed["text"])
        ats = score_resume(parsed, ent)
        fl = flags_for(parsed, ent)
        all_flags.update(x.split(":")[0] for x in fl)
        sections = [s for s in parsed["sections"] if s != "header"]
        rows.append((
            pdf.name[:30], parsed["layout"]["columns"], len(sections), len(ent["skills"]),
            len(ent["experience"]), len(ent["education"]), len(ent["projects"]),
            ats["readability_score"], ", ".join(fl) or "-",
        ))
        details[pdf.name] = {"sections": sections, "headings": parsed["headings_found"],
                             "layout": parsed["layout"], "ats": ats["readability_score"],
                             "skills": [s["name"] for s in ent["skills"]], "flags": fl}

    header = ("File", "Cols", "Secs", "Skills", "Jobs", "Edu", "Proj", "ATS", "Flags")
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))]
    line = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(line.format(*header))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(line.format(*map(str, r)))

    scores = [r[7] for r in rows if isinstance(r[7], int)]
    print(f"\n{len(pdfs)} CVs in {time.time() - t0:.1f}s | "
          f"avg ATS {sum(scores) / max(len(scores), 1):.0f} | min {min(scores, default=0)} | max {max(scores, default=0)}")
    if all_flags:
        print("Flag counts:", dict(all_flags.most_common()))
    (CV_DIR / "_results.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    print(f"Details saved to {CV_DIR / '_results.json'}")


if __name__ == "__main__":
    main()
