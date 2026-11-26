from collections import defaultdict, deque
import json
import os
from pathlib import Path
import re
from typing import Any
import unicodedata
from urllib.parse import quote
import urllib.request

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARABIC_TO_WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
TASHKEEL_AND_TATWEEL_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")

_EMBED_MATRIX_CACHE: dict[str, Any] = {
    "mtime": 0.0,
    "ids": [],
    "matrix": None,
}

_SOURCE_FILE_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "files": [],
    "manifest": {},
}


def _get_cached_embeddings() -> tuple[list[str], Any]:
    emb_path = PROJECT_ROOT / "data" / "embeddings_index.json"
    if not emb_path.exists():
        return [], None

    mtime = emb_path.stat().st_mtime
    if _EMBED_MATRIX_CACHE["mtime"] == mtime and _EMBED_MATRIX_CACHE["matrix"] is not None:
        return _EMBED_MATRIX_CACHE["ids"], _EMBED_MATRIX_CACHE["matrix"]

    raw_index: dict[str, list[float]] = json.loads(emb_path.read_text(encoding="utf-8"))
    valid_items = [(k, v) for k, v in raw_index.items() if v]
    if not valid_items:
        return [], None

    ids = [k for k, _ in valid_items]
    matrix = np.array([v for _, v in valid_items], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized_matrix = matrix / norms

    _EMBED_MATRIX_CACHE["mtime"] = mtime
    _EMBED_MATRIX_CACHE["ids"] = ids
    _EMBED_MATRIX_CACHE["matrix"] = normalized_matrix
    return ids, normalized_matrix


def _load_env_if_present() -> None:
    backend_dir = Path(__file__).resolve().parent
    for env_path in (PROJECT_ROOT / ".env", backend_dir / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and (k not in os.environ or not os.environ[k].strip()):
                os.environ[k] = v


def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).translate(ARABIC_TO_WESTERN_DIGITS).strip()
    t = TASHKEEL_AND_TATWEEL_RE.sub("", t)
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ى", "ي", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).lower()


def _extract_canonical_law_key(title: str, explicit_type: str = "") -> str:
    clean = re.sub(r"\s+", " ", normalize_text(title)).strip()
    if "دستور" in clean:
        leg_type = "constitution"
    elif "نظام" in clean:
        leg_type = "regulation"
    elif "تعليمات" in clean or "قرار" in clean:
        leg_type = "instructions"
    elif "قانون" in clean:
        leg_type = "law"
    else:
        leg_type = (explicit_type or "law").strip().lower() or "law"

    num_m = re.search(r"رقم\s*(\d+)", clean)
    year_m = re.search(r"لسنه\s*(\d{4})", clean)
    if num_m and year_m:
        return f"{leg_type}_{num_m.group(1)}_{year_m.group(1)}"
    return clean


def load_legislations(json_path: str = "data/legislations.json") -> list[dict[str, Any]]:
    path = Path(json_path)
    resolved = path if path.is_absolute() else PROJECT_ROOT / path
    if not resolved.exists():
        return []
    data = json.loads(resolved.read_text(encoding="utf-8"))
    return data.get("articles", [])


REPO_BLOB_BASE = os.environ.get(
    "SOURCE_REPO_BASE_URL",
    "https://github.com/ayhamAlmajali/qanoon-graph/blob/main/",
).rstrip("/") + "/"


def _norm_source_token(value: str) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).lower()
    s = TASHKEEL_AND_TATWEEL_RE.sub("", s)
    for ch in ("أ", "إ", "آ"):
        s = s.replace(ch, "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[ـ_\-]+", " ", s)
    s = re.sub(r"[^\w\s.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _get_cached_repo_sources() -> tuple[list[str], dict[str, Any]]:
    import time

    now = time.monotonic()
    if _SOURCE_FILE_CACHE["files"] and (now - _SOURCE_FILE_CACHE["ts"]) < 30.0:
        return _SOURCE_FILE_CACHE["files"], _SOURCE_FILE_CACHE["manifest"]

    found: list[str] = []
    for rel_dir in ("data/raw_pdfs", "data/inbox_docs"):
        d = PROJECT_ROOT / rel_dir
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.endswith(".meta.json"):
                    found.append(f"{rel_dir}/{f.name}")

    manifest: dict[str, Any] = {}
    manifest_path = PROJECT_ROOT / "data" / "sources_manifest.json"
    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
        except Exception:
            manifest = {}

    _SOURCE_FILE_CACHE["ts"] = now
    _SOURCE_FILE_CACHE["files"] = found
    _SOURCE_FILE_CACHE["manifest"] = manifest
    return found, manifest


def resolve_article_source(article: dict[str, Any]) -> dict[str, str | None]:
    existing_url = str(article.get("source_url") or "").strip()
    existing_lbl = str(article.get("source_label") or "").strip()
    if existing_url.startswith(("http://", "https://")):
        return {"source_label": existing_lbl or existing_url, "source_url": existing_url}

    raw = str(article.get("official_source") or "").strip()
    title = str(article.get("legislation_title") or "").strip()
    if not raw and not title:
        return {"source_label": None, "source_url": None}

    if raw.startswith("http://") or raw.startswith("https://"):
        return {"source_label": raw, "source_url": raw}

    repo_files, manifest = _get_cached_repo_sources()

    cleaned = re.sub(r"^ملف\s*pdf\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
    base_name = Path(cleaned).name if cleaned else ""
    if base_name and base_name in manifest:
        meta = manifest[base_name]
        official_url = str(meta.get("source_url") or "").strip()
        if official_url.startswith(("http://", "https://")):
            return {
                "source_label": str(meta.get("title") or cleaned or base_name),
                "source_url": official_url,
            }

    m = re.search(r"((?:data/(?:raw_pdfs|inbox_docs)/[^\s]+))", raw)
    if m:
        rel_path = m.group(1).lstrip("./")
        encoded = "/".join(quote(part) for part in rel_path.split("/"))
        return {"source_label": raw, "source_url": f"{REPO_BLOB_BASE}{encoded}"}

    norm_raw = _norm_source_token(cleaned)
    norm_title = _norm_source_token(title)

    for rel_path in repo_files:
        fname = Path(rel_path).name
        stem = Path(rel_path).stem
        norm_stem = _norm_source_token(stem)
        if (
            (norm_raw and (norm_stem in norm_raw or norm_raw in norm_stem))
            or ("المرن" in norm_title and "44" in fname)
            or ("10 لسنه 2023" in norm_title and "2023" in fname)
            or ("قانون العمل" in norm_title and "1996" in fname)
        ):
            encoded = "/".join(quote(part) for part in rel_path.split("/"))
            return {"source_label": cleaned or fname, "source_url": f"{REPO_BLOB_BASE}{encoded}"}

    return {"source_label": cleaned or title or None, "source_url": None}


def enrich_article_with_source(article: dict[str, Any]) -> dict[str, Any]:
    item = dict(article)
    src_info = resolve_article_source(item)
    if src_info.get("source_label") and not item.get("source_label"):
        item["source_label"] = src_info["source_label"]
    if src_info.get("source_url") and not item.get("source_url"):
        item["source_url"] = src_info["source_url"]
    item.pop("_norm_haystack", None)
    return item


class QanoonGraphEngine:
    def __init__(self, articles: list[dict[str, Any]]) -> None:
        self.articles = articles
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._precompute_index()
        self._build_graph()

    def _precompute_index(self) -> None:
        for art in self.articles:
            src_info = resolve_article_source(art)
            if src_info.get("source_label") and not art.get("source_label"):
                art["source_label"] = src_info["source_label"]
            if src_info.get("source_url") and not art.get("source_url"):
                art["source_url"] = src_info["source_url"]

            if not art.get("canonical_law_id"):
                art["canonical_law_id"] = _extract_canonical_law_key(
                    str(art.get("legislation_title", "")),
                    str(art.get("legislation_type", "")),
                )

            art["_norm_haystack"] = normalize_text(" ".join([
                art.get("legislation_title", ""),
                str(art.get("article_number", "")),
                art.get("status", ""),
                art.get("text", ""),
                " ".join(art.get("topic_tags", [])),
            ]))

    def _build_graph(self) -> None:
        for art in self.articles:
            art_id = art["id"]
            art_num = unicodedata.normalize("NFKC", str(art.get("article_number", ""))).translate(ARABIC_TO_WESTERN_DIGITS).strip()
            title = art.get("legislation_title", "")
            self.nodes[art_id] = {
                "id": art_id,
                "kind": "article",
                "label": f"{title} - مادة ({art_num})",
                "legislation_title": title,
                "canonical_law_id": art.get("canonical_law_id", ""),
                "legislation_type": art.get("legislation_type", ""),
                "article_number": art_num,
                "effective_date": art.get("effective_date", ""),
                "status": art.get("status", "ساري"),
                "topic_tags": art.get("topic_tags", []),
                "official_source": art.get("official_source", ""),
                "source_label": art.get("source_label"),
                "source_url": art.get("source_url"),
                "text": art.get("text", ""),
            }

        for art in self.articles:
            art_id = art["id"]
            for rel in art.get("relations", []):
                target_id = str(rel.get("target_ref") or "").strip()
                rel_type = str(rel.get("relation_type") or "details_or_links").strip()
                note = str(rel.get("note") or "").strip()
                if not target_id:
                    continue

                if target_id not in self.nodes:
                    self.nodes[target_id] = {
                        "id": target_id,
                        "kind": "external_ref",
                        "label": target_id,
                        "legislation_title": target_id,
                        "article_number": "-",
                        "status": "مرجع خارجي",
                        "topic_tags": [],
                        "text": note,
                    }

                edge = {
                    "source": art_id,
                    "source_label": self.nodes[art_id]["label"],
                    "target": target_id,
                    "target_label": self.nodes[target_id]["label"],
                    "relation_type": rel_type,
                    "note": note,
                }
                self.edges.append(edge)
                self.adjacency[art_id].append(edge)
                self.adjacency[target_id].append({
                    "source": target_id,
                    "source_label": self.nodes[target_id]["label"],
                    "target": art_id,
                    "target_label": self.nodes[art_id]["label"],
                    "relation_type": f"incoming_{rel_type}",
                    "note": note,
                })

    def get_summary(self) -> dict[str, Any]:
        rel_counts: dict[str, int] = defaultdict(int)
        for edge in self.edges:
            rel_counts[edge["relation_type"]] += 1

        return {
            "total_articles": len(self.articles),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "relations_by_type": dict(rel_counts),
        }

    def get_article_by_id_or_number(self, identifier: str) -> dict[str, Any] | None:
        clean = unicodedata.normalize("NFKC", identifier).translate(ARABIC_TO_WESTERN_DIGITS).strip()
        for art in self.articles:
            if art["id"] == clean:
                return art
        if ":" in clean:
            law_part, num_part = clean.split(":", 1)
            for art in self.articles:
                num = unicodedata.normalize("NFKC", str(art.get("article_number", ""))).translate(ARABIC_TO_WESTERN_DIGITS).strip()
                if num == num_part.strip() and law_part.strip() in str(art.get("canonical_law_id", "")):
                    return art
        for art in self.articles:
            num = unicodedata.normalize("NFKC", str(art.get("article_number", ""))).translate(ARABIC_TO_WESTERN_DIGITS).strip()
            if num == clean:
                return art
        return None

    def search_articles(self, query: str, min_score: float = 2.0) -> list[dict[str, Any]]:
        q_norm = normalize_text(query)
        if not q_norm:
            return self.articles

        emb_ids, emb_matrix = _get_cached_embeddings()
        sim_lookup: dict[str, float] = {}

        if emb_matrix is not None and len(emb_ids) > 0:
            try:
                from ai_ingest import get_embedding

                q_vec_list = get_embedding(query)
                if q_vec_list:
                    q_vec = np.array(q_vec_list, dtype=np.float32)
                    if emb_matrix.ndim == 2 and emb_matrix.shape[1] == q_vec.shape[0]:
                        q_norm_val = np.linalg.norm(q_vec)
                        if q_norm_val > 0:
                            q_vec = q_vec / q_norm_val
                            sims = emb_matrix @ q_vec
                            sim_lookup = {
                                emb_ids[i]: float(sims[i])
                                for i in range(len(emb_ids))
                                if sims[i] > 0.42
                            }
            except Exception:
                sim_lookup = {}

        if not sim_lookup:
            try:
                import re as _re
                q_tokens = set(_re.findall(r"[\w\u0600-\u06FF]{2,}", normalize_text(query)))
                if q_tokens:
                    for art in self.articles:
                        aid = str(art.get("id") or "")
                        if not aid:
                            continue
                        raw_txt = " ".join([
                            str(art.get("title") or ""),
                            str(art.get("legislation_title") or ""),
                            str(art.get("text") or ""),
                        ])
                        art_tokens = set(_re.findall(r"[\w\u0600-\u06FF]{2,}", normalize_text(raw_txt)))
                        if art_tokens:
                            overlap = len(q_tokens & art_tokens) / max(len(q_tokens), 1)
                            if overlap > 0:
                                sim_lookup[aid] = round(min(0.95, 0.35 + 0.60 * overlap), 4)
            except Exception:
                sim_lookup = {}

        stop_tokens = {
            "في", "من", "على", "الي", "عن", "مع", "ما", "هو", "هي", "هل",
            "قانون", "نظام", "تعليمات", "قرار", "ماده", "الماده", "حكم", "احكام", "الاردن", "الاردني"
        }
        tokens = [tok for tok in q_norm.split() if len(tok) > 1 and tok not in stop_tokens]
        if not tokens:
            tokens = [tok for tok in q_norm.split() if len(tok) > 1]
        scored: list[tuple[float, dict[str, Any]]] = []

        for art in self.articles:
            haystack = art.get("_norm_haystack") or normalize_text(" ".join([
                art.get("legislation_title", ""),
                str(art.get("article_number", "")),
                art.get("status", ""),
                art.get("text", ""),
                " ".join(art.get("topic_tags", [])),
            ]))
            lexical_score = sum(2.0 for tok in tokens if tok in haystack)
            if q_norm in haystack:
                lexical_score += 4.0

            semantic_score = sim_lookup.get(art["id"], 0.0) * 10.0
            total_score = lexical_score + semantic_score
            if total_score >= min_score:
                scored.append((total_score, art))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[dict[str, Any]] = []
        for _, art in scored:
            aid = str(art.get("id") or "")
            cos_val = round(float(sim_lookup.get(aid, 0.0)), 4)
            art_copy = dict(art)
            art_copy["cosine_similarity"] = cos_val
            results.append(art_copy)
        return results

    def trace_impact_chain(self, node_id: str, max_depth: int = 3) -> dict[str, Any]:
        if node_id not in self.nodes:
            return {
                "root": node_id,
                "impacted_nodes": [],
                "impact_paths": [],
                "potentially_outdated_regulations": [],
            }

        visited = {node_id}
        queue = deque([(node_id, 0)])
        impacted_nodes = []
        impact_paths = []
        potentially_outdated_regulations = []

        propagating_types = {
            "amends",
            "repeals",
            "contradicts",
            "overlaps_with",
            "possible_implicit_repeal",
            "incoming_issued_under",
        }

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self.adjacency.get(current, []):
                rtype = edge["relation_type"]
                if rtype not in propagating_types:
                    continue
                nxt = edge["target"]
                impact_paths.append({
                    "from": edge["source_label"],
                    "to": edge["target_label"],
                    "relation_type": rtype,
                    "note": edge["note"],
                    "depth": depth + 1,
                })
                if rtype == "incoming_issued_under" and nxt in self.nodes:
                    potentially_outdated_regulations.append(self.nodes[nxt])
                if nxt not in visited:
                    visited.add(nxt)
                    impacted_nodes.append(self.nodes[nxt])
                    queue.append((nxt, depth + 1))

        return {
            "root": self.nodes[node_id],
            "impacted_nodes": impacted_nodes,
            "impact_paths": impact_paths,
            "potentially_outdated_regulations": potentially_outdated_regulations,
        }

    def detect_conflicts_and_changes(self) -> dict[str, list[dict[str, Any]]]:
        repeals, amendments, contradictions, overlaps, subordinate_links = [], [], [], [], []
        for edge in self.edges:
            rtype = edge["relation_type"]
            if rtype in {"repeals", "possible_implicit_repeal"}:
                repeals.append(edge)
            elif rtype == "amends":
                amendments.append(edge)
            elif rtype == "contradicts":
                contradictions.append(edge)
            elif rtype == "overlaps_with":
                overlaps.append(edge)
            elif rtype == "issued_under":
                subordinate_links.append(edge)
        return {
            "repeals": repeals,
            "amendments": amendments,
            "contradictions": contradictions,
            "overlaps": overlaps,
            "subordinate_regulations": subordinate_links,
        }

    def _verify_answer_citations(self, answer: str, articles: list[dict[str, Any]]) -> str:
        norm_ans = unicodedata.normalize("NFKC", answer).translate(ARABIC_TO_WESTERN_DIGITS)
        cited_nums = {
            m.group(1)
            for m in re.finditer(r"(?:المادة|مادة)\s*[\(\[]?\s*(\d+)\s*[\)\]]?", norm_ans)
        }
        if not cited_nums:
            return answer

        valid_nums = {
            unicodedata.normalize("NFKC", str(a.get("article_number", ""))).translate(ARABIC_TO_WESTERN_DIGITS).strip()
            for a in articles
            if a.get("article_number")
        }
        unverified = sorted(num for num in cited_nums if num not in valid_nums)
        if not unverified:
            return answer

        warning = (
            f"\n\nتنبيه تدقيق آلي: وردت في الصياغة إشارة إلى رقم مادة غير مدرج ضمن المواد المسترجعة أعلاه ({'، '.join(unverified)})؛ "
            "يرجى الاعتماد على المواد الموثقة في قسم الأدلة فقط."
        )
        return answer + warning

    def analyze_legal_question(self, question: str, role: str = "lawyer") -> dict[str, Any]:
        candidates = self.search_articles(question, min_score=4.0)[:10]
        if not candidates:
            candidates = self.search_articles(question, min_score=2.0)[:6]

        if not candidates:
            return {
                "question": question,
                "engine_mode": "insufficient_evidence",
                "has_conflict_or_overlap": False,
                "verdict": (
                    "لم يتم العثور على مواد مطابقة بدرجة ثقة كافية في الفهرس الحالي للإجابة على هذا الاستفسار. "
                    "عدم وجود تطابق نصي مباشر في القاعدة الحالية لا يعني بالضرورة خروج الموضوع عن التشريع الأردني، "
                    "بل يستدعي صياغة السؤال بمصطلحات تشريعية أدق أو إضافة الوثيقة المختصة."
                ),
                "evidence_articles": [],
                "sources": [],
                "detected_relations": [],
            }

        rerank_scores_by_id: dict[str, float] = {}
        try:
            from reranker import rerank_articles as _rr_fn

            reranked_pairs = _rr_fn(question, candidates, top_k=6)
            for a, sc in reranked_pairs:
                if sc is not None and a.get("id"):
                    rerank_scores_by_id[str(a["id"])] = round(float(sc), 4)
            scored_pairs = [(a, sc) for a, sc in reranked_pairs if sc is not None]
            if scored_pairs:
                filtered_pairs = [(a, sc) for a, sc in scored_pairs if sc >= 0.25]
                matched_articles = [a for a, _ in (filtered_pairs or scored_pairs[:3])]
            else:
                matched_articles = [a for a, _ in reranked_pairs[:6]]
        except Exception:
            matched_articles = candidates[:6]

        related_edges = []
        seen_edges = set()
        for art in matched_articles:
            for edge in self.adjacency.get(art["id"], []):
                key = (edge["source"], edge["target"], edge["relation_type"])
                if key not in seen_edges:
                    seen_edges.add(key)
                    related_edges.append(edge)

        conflicts = [
            e for e in related_edges
            if e["relation_type"] in {"contradicts", "overlaps_with", "repeals", "amends", "incoming_repeals", "incoming_amends"}
        ]

        llm_answer, engine_mode = self._try_llm_synthesis(question, matched_articles, conflicts)
        if llm_answer:
            llm_answer = self._verify_answer_citations(llm_answer, matched_articles)
        verdict = llm_answer or self._rule_based_synthesis(question, matched_articles, conflicts)

        enriched_evidence = []
        for a in matched_articles:
            item = enrich_article_with_source(a)
            aid = str(a.get("id") or "")
            cos_val = a.get("cosine_similarity")
            cos_val = round(float(cos_val), 4) if cos_val is not None else 0.0
            rr_val = rerank_scores_by_id.get(aid)
            item["cosine_similarity"] = cos_val
            item["similarity"] = cos_val if cos_val > 0.0 else (rr_val if rr_val is not None else 0.0)
            enriched_evidence.append(item)
        unique_sources: list[dict[str, str | None]] = []
        seen_src: set[str] = set()
        for a in enriched_evidence:
            s_url = a.get("source_url")
            s_lbl = a.get("source_label") or a.get("official_source")
            key = str(s_url or s_lbl or "").strip()
            if key and key not in seen_src:
                seen_src.add(key)
                unique_sources.append({
                    "label": s_lbl,
                    "url": s_url,
                    "legislation_title": a.get("legislation_title"),
                })

        return {
            "question": question,
            "engine_mode": engine_mode,
            "has_conflict_or_overlap": any(
                e["relation_type"] in {"contradicts", "overlaps_with", "repeals"} for e in conflicts
            ),
            "verdict": verdict,
            "evidence_articles": enriched_evidence,
            "sources": unique_sources,
            "detected_relations": conflicts or related_edges,
        }

    def _rule_based_synthesis(
        self,
        question: str,
        articles: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
    ) -> str:
        top = articles[0]
        citations = "، ".join(
            f"المادة ({a['article_number']}) من {a['legislation_title']}" for a in articles[:3]
        )
        top_leg = str(top.get("legislation_title", ""))
        top_text = str(top.get("text", ""))
        is_labor_context = ("العمل" in top_leg) and ("عامل" in top_text or "عاملة" in top_text or "العمل" in top_text)
        labor_suffix = " (وفقاً لمبدأ النص الأعلى حماية للعامل ضمن نطاق أحكام العمل)." if is_labor_context else ""
        conflict_note = (
            f"تم رصد {len(conflicts)} ارتباط/تداخل تشريعي مباشر: {conflicts[0]['note']}."
            if conflicts
            else f"لم يُرصد تعارض إلغاء مباشر بين النصوص المطابقة{labor_suffix}"
        )
        return (
            f"بناءً على تحليل قاعدة البيانات التشريعية ({citations}): "
            f"تنص {top['legislation_title']} - المادة ({top['article_number']}) على: «{top['text']}» "
            f"حالة النص: ({top['status']}). {conflict_note}"
        )

    def _try_llm_synthesis(
        self,
        question: str,
        articles: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        role: str = "lawyer",
    ) -> tuple[str | None, str]:
        role_guidance = (
            "خاطب المواطن بلغة عربية واضحة ومبسطة تركز على حقوقه والتزاماته العملية."
            if role == "citizen"
            else (
                "خاطب المشرّع وصانع القرار بلغة مؤسسية تركز على الاتساق التشريعي وأثر التعديل أو الإلغاء."
                if role == "legislator"
                else "خاطب المحامي والمختص بلغة قانونية دقيقة مع ذكر أرقام المواد وأسماء التشريعات."
            )
        )
        _load_env_if_present()

        context_blocks = [
            f"- [{a.get('legislation_title', '')} | مادة {a.get('article_number', '')} | الحالة: {a.get('status', '')}]: {a.get('text', '')}"
            for a in articles
        ]
        rel_blocks = [
            f"- ({c.get('relation_type', '')}) من [{c.get('source_label', '')}] إلى [{c.get('target_label', '')}]: {c.get('note', '')}"
            for c in conflicts
        ]

        system_prompt = (
            f"أنت مستشار تحليل تشريعي أردني في منصة (معيار). {role_guidance} "
            "وجميع التشريعات والقرارات في قاعدة البيانات هي تشريعات أردنية صادرة في المملكة الأردنية الهاشمية؛ لا تنسب أي تشريع إلى دولة أخرى. "
            "أجب باللغة العربية الفصحى الواضحة والمنظمة معتمداً حصراً على المواد والعلاقات المرفقة.\n"
            "قواعد صارمة جداً:\n"
            "- استخرج واشرح جميع الأحكام والحقوق والالتزامات الواردة في النصوص المرفقة والمتعلقة بموضوع السؤال بوضوح وتفصيل (حتى لو صاغ المستخدم سؤاله بعبارة عامة مثل 'قانون كذا' بدلاً من اسم التشريع الحرفي).\n"
            "- لا تقل 'لا تتضمن النصوص حكماً صريحاً' إلا إذا كانت النصوص المرفقة بعيدة تماماً عن موضوع السؤال ولا تنظم أي جانب منه.\n"
            "- التزم حصراً بما ورد في النصوص المرفقة ولا تختلق أي رقم مادة أو حكم غير موجود فيها.\n"
            "- لا تكرر أي عنوان مرتين متتاليتين.\n"
            "- اكتب كل قسم مرة واحدة فقط وبشكل مباشر:\n"
            "  1. الحكم القانوني المباشر: إجابة واضحة ومباشرة للسؤال من واقع النصوص فقط.\n"
            "  2. الأثر التشريعي (إلغاء / تعديل / تداخل): وضح بدقة هل يوجد إلغاء أو تعارض ملزم أم تداخل تنظيمي.\n"
            "  3. المواد المستند إليها: قائمة مختصرة برقم المادة واسم التشريع وحالته فقط.\n"
            "  4. الخلاصة: سطران مكثفان كحد أقصى يلخصان النتيجة."
        )
        user_prompt = (
            f"السؤال القانوني: {question}\n\n"
            f"المواد المسترجعة من قاعدة البيانات:\n" + "\n".join(context_blocks) + "\n\n"
            f"العلاقات والتداخلات المرصودة في الرسم البياني:\n"
            + ("\n".join(rel_blocks) if rel_blocks else "لا توجد علاقات إضافية مسجلة.")
        )

        provider = os.environ.get("LLM_PROVIDER", "groq").strip().lower()
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat").strip()
        ollama_model = (
            os.environ.get("OLLAMA_MODEL", "").strip()
            or os.environ.get("OLLAMA_CHAT_MODEL", "").strip()
            or "qwen2.5:7b"
        )

        if provider == "none":
            return None, "graph_semantic_reasoning"

        def _try_groq() -> tuple[str, str] | None:
            if not groq_key:
                return None
            payload = json.dumps({
                "model": groq_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {groq_key}",
                    "User-Agent": "Mozilla/5.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answer = (data["choices"][0]["message"]["content"] or "").strip()
                if answer:
                    return answer, f"groq:{groq_model}"
            return None

        def _try_ollama() -> tuple[str, str] | None:
            timeout_sec = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "15"))
            payload = json.dumps({
                "model": ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            }).encode("utf-8")
            req = urllib.request.Request(
                ollama_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answer = (data.get("message", {}).get("content") or "").strip()
                if answer:
                    return answer, f"ollama:{ollama_model}"
            return None

        if provider == "ollama":
            try:
                res = _try_ollama()
                if res:
                    return res
            except Exception:
                pass
            return None, "graph_semantic_reasoning"

        if groq_key:
            try:
                res = _try_groq()
                if res:
                    return res
            except Exception:
                pass
            allow_ollama = os.environ.get("ALLOW_OLLAMA_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}
            if allow_ollama:
                try:
                    res = _try_ollama()
                    if res:
                        return res
                except Exception:
                    pass
            return None, "graph_semantic_reasoning"

        try:
            res = _try_ollama()
            if res:
                return res
        except Exception:
            pass

        return None, "graph_semantic_reasoning"

    def to_graph_payload(
        self,
        limit: int = 180,
        legislation_title: str | None = None,
    ) -> dict[str, Any]:
        all_nodes = list(self.nodes.values())
        if legislation_title and legislation_title.strip():
            q = legislation_title.strip()
            filtered = [
                n for n in all_nodes
                if q in str(n.get("legislation_title", "")) or q in str(n.get("label", ""))
            ]
        else:
            connected_ids = {
                e.get("source") for e in self.edges if e.get("source")
            } | {
                e.get("target") for e in self.edges if e.get("target")
            }
            connected = [n for n in all_nodes if n.get("id") in connected_ids]
            others = [n for n in all_nodes if n.get("id") not in connected_ids]
            filtered = connected + others

        capped = filtered[: max(1, int(limit))]
        allowed_ids = {n.get("id") for n in capped if n.get("id")}
        filtered_edges = [
            e for e in self.edges
            if e.get("source") in allowed_ids and e.get("target") in allowed_ids
        ]
        return {
            "nodes": capped,
            "edges": filtered_edges,
            "total_nodes": len(all_nodes),
            "total_edges": len(self.edges),
            "returned_nodes": len(capped),
            "returned_edges": len(filtered_edges),
        }

    def get_legislation_evolution(
        self,
        legislation_title: str | None = None,
        article_number: str | None = None,
    ) -> dict[str, Any]:
        counts: dict[str, int] = {}
        canonical_by_title: dict[str, str] = {}
        for art in self.articles:
            t = str(art.get("legislation_title") or "").strip()
            if t:
                counts[t] = counts.get(t, 0) + 1
                canonical_by_title[t] = str(art.get("canonical_law_id") or "")

        available = [
            {
                "legislation_title": t,
                "canonical_law_id": canonical_by_title.get(t),
                "article_count": c,
            }
            for t, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ]
        if not available:
            return {"selected_legislation": None, "available_legislations": [], "stages": []}

        chosen = (legislation_title or "").strip()
        if not chosen or chosen not in counts:
            if chosen:
                matches = [t for t in counts if chosen in t]
                chosen = matches[0] if matches else available[0]["legislation_title"]
            else:
                chosen = available[0]["legislation_title"]

        chosen_canonical = canonical_by_title.get(chosen, "")
        by_id = {a.get("id"): a for a in self.articles if a.get("id")}
        main_arts = [
            a for a in self.articles
            if str(a.get("legislation_title") or "").strip() == chosen
            or (chosen_canonical and str(a.get("canonical_law_id") or "") == chosen_canonical)
        ]
        if article_number and article_number.strip():
            num_q = unicodedata.normalize("NFKC", article_number).translate(ARABIC_TO_WESTERN_DIGITS).strip()
            filtered_num = [
                a for a in main_arts
                if unicodedata.normalize("NFKC", str(a.get("article_number") or "")).translate(ARABIC_TO_WESTERN_DIGITS).strip() == num_q
            ]
            if filtered_num:
                main_arts = filtered_num

        main_ids = {a.get("id") for a in main_arts if a.get("id")}
        stages: list[dict[str, Any]] = []

        for art in main_arts:
            enriched = enrich_article_with_source(art)
            rels = [
                r for r in (art.get("relations") or [])
                if isinstance(r, dict)
                and r.get("relation_type") in {"repeals", "amends", "contradicts", "overlaps_with", "issued_under"}
            ]
            if rels:
                for rel in rels:
                    target = by_id.get(rel.get("target_ref"))
                    stages.append({
                        "date": str(art.get("effective_date") or "غير محدد"),
                        "change_type": rel.get("relation_type"),
                        "article_id": art.get("id"),
                        "article_number": art.get("article_number"),
                        "legislation_title": art.get("legislation_title") or chosen,
                        "status": art.get("status", "ساري"),
                        "before_or_related_ref": (
                            f"{target.get('legislation_title')} - مادة ({target.get('article_number')})"
                            if target else str(rel.get("target_ref") or "")
                        ),
                        "before_text": target.get("text", "") if target else "",
                        "current_text": art.get("text", ""),
                        "note": rel.get("note", ""),
                        "source_label": enriched.get("source_label"),
                        "source_url": enriched.get("source_url"),
                    })

        for other in self.articles:
            if other.get("id") in main_ids:
                continue
            enriched_other = enrich_article_with_source(other)
            for rel in (other.get("relations") or []):
                if not isinstance(rel, dict):
                    continue
                if rel.get("relation_type") not in {"repeals", "amends", "contradicts", "overlaps_with", "issued_under"}:
                    continue
                if rel.get("target_ref") in main_ids:
                    target = by_id.get(rel.get("target_ref"))
                    stages.append({
                        "date": str(other.get("effective_date") or "غير محدد"),
                        "change_type": rel.get("relation_type", "amends"),
                        "article_id": other.get("id"),
                        "article_number": other.get("article_number"),
                        "legislation_title": other.get("legislation_title"),
                        "status": other.get("status", "ساري"),
                        "before_or_related_ref": (
                            f"{target.get('legislation_title')} - مادة ({target.get('article_number')})"
                            if target else chosen
                        ),
                        "before_text": target.get("text", "") if target else "",
                        "current_text": other.get("text", ""),
                        "note": rel.get("note", ""),
                        "source_label": enriched_other.get("source_label"),
                        "source_url": enriched_other.get("source_url"),
                    })

        if not stages:
            sorted_main = sorted(
                main_arts,
                key=lambda a: (str(a.get("effective_date") or "9999"), str(a.get("article_number") or "")),
            )
            for art in sorted_main[:25]:
                enriched = enrich_article_with_source(art)
                stages.append({
                    "date": str(art.get("effective_date") or "غير محدد"),
                    "change_type": "enacted",
                    "article_id": art.get("id"),
                    "article_number": art.get("article_number"),
                    "legislation_title": art.get("legislation_title") or chosen,
                    "status": art.get("status", "ساري"),
                    "before_or_related_ref": "",
                    "before_text": "",
                    "current_text": art.get("text", ""),
                    "note": "نص تشريعي مسجل حسب تاريخ النفاذ.",
                    "source_label": enriched.get("source_label"),
                    "source_url": enriched.get("source_url"),
                })

        stages.sort(key=lambda s: str(s.get("date") or "9999"))
        return {
            "selected_legislation": chosen,
            "canonical_law_id": chosen_canonical,
            "article_filter": article_number,
            "total_stages": len(stages),
            "available_legislations": available,
            "stages": stages,
        }