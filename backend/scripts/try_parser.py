"""Try the resume parser on a PDF from the terminal.

Usage (from the backend folder, venv active):
    python scripts/try_parser.py "C:\\path\\to\\resume.pdf"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.pdf_parser import extract_pdf  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)

result = extract_pdf(Path(sys.argv[1]).read_bytes())

print("=" * 60, "\nLAYOUT:", json.dumps(result["layout"], indent=2))
print("\nCONTACT:", json.dumps(result["contact"], indent=2))
print("\nHEADINGS FOUND:", result["headings_found"])
for name, text in result["sections"].items():
    preview = text[:300] + ("..." if len(text) > 300 else "")
    print(f"\n--- [{name.upper()}] ---\n{preview}")

# ---- Day 5: entities ----
from app.services.entity_extractor import extract_entities  # noqa: E402

e = extract_entities(result["sections"], result["text"])
print("\n" + "=" * 60 + "\nENTITIES")
print(f"Name: {e['name']}\nHeadline: {e['headline']}\nLocation: {e['location']}")
print(f"Method: {e['extraction_method']}   Total experience: {e['total_experience_months']} months")
print("\nSKILLS:", ", ".join(f"{s['name']}({s['mentions']})" for s in e["skills"]))
print("\nEXPERIENCE:")
for j in e["experience"]:
    print(f"  - {j['title']} @ {j['company']} | {j['start']} – {j['end']} | {j['months']} months | {len(j['bullets'])} bullets")
print("\nEDUCATION:")
for d in e["education"]:
    print(f"  - [{d['degree_level']}] {d['degree']} | field: {d['field']} | {d['institution']} | {d['end_year']} | CGPA {d['cgpa']}")
print("\nPROJECTS:")
for p in e["projects"]:
    print(f"  - {p['title']}  →  {', '.join(p['skills'])}")
print("\nLanguages:", e["languages"], "\nCertifications:", e["certifications"])
