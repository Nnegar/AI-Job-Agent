"""
Cross-Source Job Deduplicator.
Normalizes URLs, companies, and titles to detect duplicates across multiple job sources
(Greenhouse, Lever, Ashby, Arbeitnow, LinkedIn).
"""

import re
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "jobs.db"

# Corporate suffixes to remove from company names
COMPANY_SUFFIXES = [
    r"\binc\b\.?",
    r"\bincorporated\b",
    r"\bllc\b",
    r"\bltd\b\.?",
    r"\blimited\b",
    r"\bgmbh\b",
    r"\bag\b",
    r"\bab\b",
    r"\bs\.?a\.?\b",
    r"\bs\.?r\.?l\.?\b",
    r"\bs\.?p\.?a\.?\b",
    r"\bb\.?v\.?\b",
    r"\bn\.?v\.?\b",
    r"\bcorp\b\.?",
    r"\bcorporation\b",
    r"\btechnologies\b",
    r"\btechnology\b",
    r"\bholding\b",
    r"\bholdings\b",
    r"\bgroup\b",
]

# Fluff tags to remove from job titles
TITLE_FLUFF_PATTERNS = [
    r"\([mfdw/]+\)",               # (m/w/d), (f/m/d), etc.
    r"\[[mfdw/]+\]",
    r"\(all genders\)",
    r"\(hybrid\)",
    r"\[hybrid\]",
    r"\(remote\)",
    r"\[remote\]",
    r"\(on-?site\)",
    r"\[on-?site\]",
    r"\s*-\s*(?:emea|europe|uk|germany|italy|ireland|netherlands|london|milan|berlin|amsterdam|paris)\b.*$",
    r"\s*/\s*(?:emea|europe|uk|germany|italy|ireland|netherlands|london|milan|berlin|amsterdam|paris)\b.*$",
]

# Tracking query params to strip from URLs
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gh_jid",
    "ref",
    "trk",
    "trackingid",
    "sessionid",
    "sub_id",
    "source",
    "fbclid",
    "gclid",
    "mode",
}


def normalize_company(company: Optional[str]) -> str:
    if not company:
        return ""
    text = company.lower().strip()
    for pattern in COMPANY_SUFFIXES:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    # Remove punctuation & collapse spaces
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    text = title.lower().strip()
    for pattern in TITLE_FLUFF_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    # Remove punctuation & collapse spaces
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def normalize_url(raw_url: Optional[str]) -> str:
    if not raw_url:
        return ""
    parsed = urllib.parse.urlparse(raw_url.strip())
    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    # Strip tracking params
    if parsed.query:
        query_pairs = urllib.parse.parse_qsl(parsed.query)
        cleaned_pairs = [(k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS]
        clean_query = urllib.parse.urlencode(cleaned_pairs)
    else:
        clean_query = ""

    # Omit fragment (#)
    return urllib.parse.urlunparse((scheme, netloc, path, "", clean_query, ""))


def generate_job_signature(company: str, title: str) -> str:
    norm_c = normalize_company(company)
    norm_t = normalize_title(title)
    return f"{norm_c}::{norm_t}"


class JobDeduplicator:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.known_urls: Set[str] = set()
        self.known_source_ids: Set[Tuple[str, str]] = set()
        self.known_signatures: Set[str] = set()

        if self.db_path.exists():
            self._load_existing_jobs()

    def _load_existing_jobs(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, source, source_job_id, company, title, url FROM jobs")
        for row in cursor.fetchall():
            jid, src, src_id, comp, title, url = row
            if url:
                self.known_urls.add(normalize_url(url))
            if src and src_id:
                self.known_source_ids.add((src.lower(), str(src_id)))
            if comp and title:
                sig = generate_job_signature(comp, title)
                if sig != "::":
                    self.known_signatures.add(sig)
        conn.close()

    def is_duplicate(self, job: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether a candidate job is a duplicate of an existing record.
        Returns: (is_dup, reason)
        """
        # 1. Check Normalized URL
        url = job.get("url")
        if url:
            norm_url = normalize_url(url)
            if norm_url and norm_url in self.known_urls:
                return True, "duplicate_url"

        # 2. Check (source, source_job_id)
        src = job.get("source")
        src_id = job.get("external_id") or job.get("source_job_id") or job.get("id")
        if src and src_id:
            pair = (str(src).lower(), str(src_id))
            if pair in self.known_source_ids:
                return True, "duplicate_source_id"

        # 3. Check Semantic Signature (Company + Title)
        comp = job.get("company", "")
        title = job.get("title", "")
        if comp and title:
            sig = generate_job_signature(comp, title)
            if sig in self.known_signatures:
                return True, "duplicate_semantic_signature"

        return False, None

    def register_job(self, job: Dict[str, Any]):
        """
        Registers a job into in-memory indices to avoid duplicates within the same batch.
        """
        url = job.get("url")
        if url:
            self.known_urls.add(normalize_url(url))

        src = job.get("source")
        src_id = job.get("external_id") or job.get("source_job_id") or job.get("id")
        if src and src_id:
            self.known_source_ids.add((str(src).lower(), str(src_id)))

        comp = job.get("company", "")
        title = job.get("title", "")
        if comp and title:
            sig = generate_job_signature(comp, title)
            if sig != "::":
                self.known_signatures.add(sig)
