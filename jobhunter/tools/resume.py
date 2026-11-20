from pathlib import Path

from pypdf import PdfReader


def load_resume(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume not found: {p.resolve()}")
    if p.suffix.lower() == ".pdf":
        return "\n".join((page.extract_text() or "") for page in PdfReader(p).pages).strip()
    return p.read_text().strip()
