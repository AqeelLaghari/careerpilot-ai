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
