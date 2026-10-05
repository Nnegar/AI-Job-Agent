"""
Resume Loader Module.
Loads resume content by CV name from the resumes directory.
Supports Markdown (.md), Word (.docx), PDF (.pdf), and text (.txt).
"""

from pathlib import Path
from typing import Dict, List, Optional
import docx
import pypdf

RESUMES_DIR = Path(__file__).resolve().parents[2] / "resumes"

_RESUME_CACHE: Dict[str, str] = {}


def _extract_from_docx(file_path: Path) -> str:
    doc = docx.Document(file_path)
    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            cleaned = text.lstrip("•- \t").strip()
            if text.startswith("•") or text.startswith("-"):
                lines.append(f"- {cleaned}")
            else:
                lines.append(cleaned)
    return "\n".join(lines).strip()


def _extract_from_pdf(file_path: Path) -> str:
    reader = pypdf.PdfReader(file_path)
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text.strip())
    return "\n\n".join(pages_text).strip()


def load_resume(resume_name: str, use_cache: bool = True) -> str:
    """
    Load resume text given a resume name or filename (e.g. 'Telecom_AI_CV').
    Tries .md, .docx, .pdf, and .txt in order of preference.
    """
    stem = Path(resume_name).stem
    if use_cache and stem in _RESUME_CACHE:
        return _RESUME_CACHE[stem]

    # Extensions in priority order
    extensions = [".md", ".docx", ".pdf", ".txt"]

    # If resume_name already has an extension, try that exact path first
    explicit_path = RESUMES_DIR / resume_name
    if explicit_path.is_file():
        target_path = explicit_path
    else:
        target_path = None
        for ext in extensions:
            candidate = RESUMES_DIR / f"{stem}{ext}"
            if candidate.is_file():
                target_path = candidate
                break

    if target_path is None or not target_path.exists():
        available = get_available_resumes()
        raise FileNotFoundError(
            f"Resume '{resume_name}' not found in {RESUMES_DIR}. "
            f"Available resumes: {available}"
        )

    ext = target_path.suffix.lower()
    if ext == ".md" or ext == ".txt":
        content = target_path.read_text(encoding="utf-8").strip()
    elif ext == ".docx":
        content = _extract_from_docx(target_path)
    elif ext == ".pdf":
        content = _extract_from_pdf(target_path)
    else:
        content = target_path.read_text(encoding="utf-8", errors="ignore").strip()

    if use_cache:
        _RESUME_CACHE[stem] = content

    return content


def get_available_resumes() -> List[str]:
    """
    Returns list of unique available resume base names in resumes/.
    """
    if not RESUMES_DIR.exists():
        return []

    stems = set()
    for f in RESUMES_DIR.iterdir():
        if f.is_file() and not f.name.startswith(".") and ":Zone.Identifier" not in f.name:
            if f.suffix.lower() in [".md", ".docx", ".pdf", ".txt"]:
                stems.add(f.stem)
    return sorted(list(stems))
