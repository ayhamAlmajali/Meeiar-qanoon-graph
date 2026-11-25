from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any
import unicodedata
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup

from ai_ingest import INBOX_DIR, PROJECT_ROOT, ingest_inbox_folder, rebuild_all_embeddings

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}

MANIFEST_PATH = PROJECT_ROOT / "data" / "sources_manifest.json"

ALLOWED_GOV_DOMAINS = (
    ".gov.jo",
    "mol.gov.jo",
    "lob.gov.jo",
    "pm.gov.jo",
    "moh.gov.jo",
)

SEED_URLS = [
    "https://mol.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86",
    "https://mol.gov.jo/AR/List/%D8%A7%D9%84%D8%A3%D9%86%D8%B8%D9%85%D8%A9",
    "https://mol.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D8%B1%D8%A7%D8%B1%D8%A7%D8%AA",
]

ARABIC_TO_WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _is_official_jordanian_gov_url(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().strip(".")
    if not host:
        return False
    return any(host == dom.lstrip(".") or host.endswith(dom) for dom in ALLOWED_GOV_DOMAINS)


def _atomic_write_bytes(target_path: Path, data: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=str(target_path.parent),
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, target_path)


def _atomic_write_json(target_path: Path, payload: Any) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(target_path, serialized)


def _load_manifest() -> dict[str, dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _record_provenance(
    out_path: Path,
    source_url: str,
    sha256_hex: str,
    title: str,
    content_type: str,
) -> None:
    retrieved_at = datetime.now(timezone.utc).isoformat()
    host = (urllib.parse.urlsplit(source_url).hostname or "").lower()
    meta = {
        "filename": out_path.name,
        "title": title,
        "source_url": source_url,
        "source_domain": host,
        "is_official_gov": _is_official_jordanian_gov_url(source_url),
        "retrieved_at": retrieved_at,
        "sha256": sha256_hex,
        "content_type": content_type,
    }
    meta_sidecar = out_path.with_suffix(out_path.suffix + ".meta.json")
    _atomic_write_json(meta_sidecar, meta)

    manifest = _load_manifest()
    manifest[out_path.name] = meta
    _atomic_write_json(MANIFEST_PATH, manifest)


def _encode_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    quoted_path = urllib.parse.quote(parsed.path, safe="/%")
    quoted_query = urllib.parse.quote(parsed.query, safe="=&%+")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, quoted_path, quoted_query, parsed.fragment))


def fetch_bytes(url: str) -> tuple[bytes, str]:
    if not _is_official_jordanian_gov_url(url):
        raise ValueError(f"تم رفض الرابط لأنه خارج نطاق المواقع الحكومية الأردنية المعتمدة (.gov.jo): {url}")
    safe_url = _encode_url(url)
    req = urllib.request.Request(safe_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as resp:
        final_url = resp.geturl()
        if not _is_official_jordanian_gov_url(final_url):
            raise ValueError(f"تمت إعادة التوجيه إلى نطاق غير حكومي: {final_url}")
        ctype = resp.headers.get("Content-Type", "").lower()
        return resp.read(), ctype


def clean_arabic_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    raw_title = soup.title.string.strip() if soup.title and soup.title.string else "legislation_doc"
    title = unicodedata.normalize("NFKC", raw_title).translate(ARABIC_TO_WESTERN_DIGITS)

    text = unicodedata.normalize("NFKC", soup.get_text(separator="\n")).translate(ARABIC_TO_WESTERN_DIGITS)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    clean_lines = [line for line in lines if len(line) > 2]
    return title, "\n".join(clean_lines)


def safe_filename(name: str, ext: str = ".txt") -> str:
    norm = unicodedata.normalize("NFKC", name).translate(ARABIC_TO_WESTERN_DIGITS)
    clean = re.sub(r'[\\/*?:"<>|]+', "_", norm).strip()
    return (clean[:85] or "doc") + ext


def extract_pdf_links_from_html(base_url: str, html: str, max_pdfs: int = 10) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        full_url = urllib.parse.urljoin(base_url, href)
        if not _is_official_jordanian_gov_url(full_url):
            continue
        label = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", a.get_text(" ", strip=True))).strip()
        if ".pdf" in full_url.lower() and full_url not in seen:
            seen.add(full_url)
            found.append((full_url, label or Path(urllib.parse.urlparse(full_url).path).stem))
            if len(found) >= max_pdfs:
                break
    return found


def save_pdf_bytes(raw_bytes: bytes, suggested_name: str, source_url: str) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    manifest = _load_manifest()
    if any(item.get("sha256") == sha256_hex for item in manifest.values()):
        print(f"[Skip Duplicate PDF] {suggested_name} (sha256={sha256_hex[:12]})", flush=True)
        return

    fname = safe_filename(suggested_name, ".pdf")
    out_path = INBOX_DIR / fname
    _atomic_write_bytes(out_path, raw_bytes)
    _record_provenance(out_path, source_url, sha256_hex, suggested_name, "application/pdf")
    print(f"[Saved PDF] {out_path.name} (sha256={sha256_hex[:12]})", flush=True)


def save_text_doc(title: str, clean_text: str, source_url: str) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    encoded = clean_text.encode("utf-8")
    sha256_hex = hashlib.sha256(encoded).hexdigest()
    manifest = _load_manifest()
    if any(item.get("sha256") == sha256_hex for item in manifest.values()):
        print(f"[Skip Duplicate TXT] {title} (sha256={sha256_hex[:12]})", flush=True)
        return

    fname = safe_filename(title, ".txt")
    out_path = INBOX_DIR / fname
    _atomic_write_bytes(out_path, encoded)
    _record_provenance(out_path, source_url, sha256_hex, title, "text/plain")
    print(f"[Saved TXT] {out_path.name} ({len(clean_text)} chars)", flush=True)


def crawl_seeds(urls: list[str], max_pdfs_per_page: int = 8) -> None:
    for url in urls:
        try:
            raw_bytes, ctype = fetch_bytes(url)
            if "application/pdf" in ctype or url.lower().endswith(".pdf"):
                stem = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).stem)
                save_pdf_bytes(raw_bytes, stem, url)
            else:
                html = raw_bytes.decode("utf-8", errors="ignore")
                pdf_links = extract_pdf_links_from_html(url, html, max_pdfs=max_pdfs_per_page)
                if pdf_links:
                    print(f"[Found {len(pdf_links)} PDFs on] {url}", flush=True)
                    for pdf_url, pdf_label in pdf_links:
                        try:
                            p_bytes, _ = fetch_bytes(pdf_url)
                            save_pdf_bytes(p_bytes, pdf_label, pdf_url)
                            time.sleep(1.0)
                        except Exception as exc:
                            print(f"[PDF Download Error] {pdf_url}: {exc}", flush=True)
                else:
                    title, clean_text = clean_arabic_html(html)
                    if len(clean_text) >= 400:
                        save_text_doc(title, clean_text, url)
            time.sleep(1.5)
        except Exception as exc:
            print(f"[Crawl Error] {url}: {exc}", flush=True)


def run_full_automation() -> None:
    crawl_seeds(SEED_URLS, max_pdfs_per_page=8)
    summary = ingest_inbox_folder()
    total_emb = rebuild_all_embeddings(force=False)
    print(f"\n[Automation Complete] Files processed: {summary['processed_files']} | Total vectors: {total_emb}", flush=True)


if __name__ == "__main__":
    run_full_automation()