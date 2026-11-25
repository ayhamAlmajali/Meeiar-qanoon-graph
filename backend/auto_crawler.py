from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup

from ai_ingest import INBOX_DIR, ingest_inbox_folder, rebuild_all_embeddings

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}

SEED_URLS = [
    "https://mol.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D8%B1%D8%A7%D8%B1%D8%A7%D8%AA",
    "https://jtgcu.org/ebv4.0/root_storage/ar/eb_list_page/%D9%82%D8%A7%D9%86%D9%88%D9%86_%D8%A7%D9%84%D8%B9%D9%85%D9%84_%D8%A7%D9%84%D8%A7%D8%B1%D8%AF%D9%86%D9%8A_%D9%85%D8%B9_%D8%AA%D8%B9%D8%AF%D9%8A%D9%84%D8%A7%D8%AA_2019.pdf",
]


def _encode_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    quoted_path = urllib.parse.quote(parsed.path, safe="/%")
    quoted_query = urllib.parse.quote(parsed.query, safe="=&%+")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, quoted_path, quoted_query, parsed.fragment))


def fetch_bytes(url: str) -> tuple[bytes, str]:
    safe_url = _encode_url(url)
    req = urllib.request.Request(safe_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as resp:
        ctype = resp.headers.get("Content-Type", "").lower()
        return resp.read(), ctype


def clean_arabic_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else "legislation_doc"
    text = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    clean_lines = [line for line in lines if len(line) > 2]
    return title, "\n".join(clean_lines)


def safe_filename(name: str, ext: str = ".txt") -> str:
    clean = re.sub(r'[\\/*?:"<>|]+', "_", name).strip()
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
        label = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if ".pdf" in full_url.lower() and full_url not in seen:
            seen.add(full_url)
            found.append((full_url, label or Path(urllib.parse.urlparse(full_url).path).stem))
            if len(found) >= max_pdfs:
                break
    return found


def save_pdf_bytes(raw_bytes: bytes, suggested_name: str) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(suggested_name, ".pdf")
    out_path = INBOX_DIR / fname
    out_path.write_bytes(raw_bytes)
    print(f"[Saved PDF] {out_path.name}", flush=True)


def save_text_doc(title: str, clean_text: str) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(title, ".txt")
    out_path = INBOX_DIR / fname
    out_path.write_text(clean_text, encoding="utf-8")
    print(f"[Saved TXT] {out_path.name} ({len(clean_text)} chars)", flush=True)


def crawl_seeds(urls: list[str], max_pdfs_per_page: int = 8) -> None:
    for url in urls:
        try:
            raw_bytes, ctype = fetch_bytes(url)
            if "application/pdf" in ctype or url.lower().endswith(".pdf"):
                stem = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).stem)
                save_pdf_bytes(raw_bytes, stem)
            else:
                html = raw_bytes.decode("utf-8", errors="ignore")
                pdf_links = extract_pdf_links_from_html(url, html, max_pdfs=max_pdfs_per_page)
                if pdf_links:
                    print(f"[Found {len(pdf_links)} PDFs on] {url}", flush=True)
                    for pdf_url, pdf_label in pdf_links:
                        try:
                            p_bytes, _ = fetch_bytes(pdf_url)
                            save_pdf_bytes(p_bytes, pdf_label)
                            time.sleep(1.0)
                        except Exception as exc:
                            print(f"[PDF Download Error] {pdf_url}: {exc}", flush=True)
                else:
                    title, clean_text = clean_arabic_html(html)
                    if len(clean_text) >= 400:
                        save_text_doc(title, clean_text)
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