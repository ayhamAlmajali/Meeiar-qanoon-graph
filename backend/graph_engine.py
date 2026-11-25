from urllib.parse import quote
from collections import defaultdict, deque
import json
import os
from pathlib import Path
import re
from typing import Any
import urllib.request

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARABIC_TO_WESTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_EMBED_MATRIX_CACHE: dict[str, Any] = {
    "mtime": 0.0,
    "ids": [],
    "matrix": None,
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
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def normalize_text(text: str) -> str:
    t = text.translate(ARABIC_TO_WESTERN_DIGITS).strip()
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ى", "ي", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).lower()


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
    s = str(value or "").lower()
    for ch in ("أ", "إ", "آ"):
        s = s.replace(ch, "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[ـ_\-]+", " ", s)
    s = re.sub(r"[^\w\s.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _discover_repo_source_files() -> list[str]:
    found: list[str] = []
    for rel_dir in ("data/raw_pdfs", "data/inbox_docs"):
        d = PROJECT_ROOT / rel_dir
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    found.append(f"{rel_dir}/{f.name}")
    return found


def resolve_article_source(article: dict[str, Any]) -> dict[str, str | None]:
    raw = str(article.get("official_source") or "").strip()
    title = str(article.get("legislation_title") or "").strip()
    if not raw and not title:
        return {"source_label": None, "source_url": None}

    if raw.startswith("http://") or raw.startswith("https://"):
        return {"source_label": raw, "source_url": raw}

    m = re.search(r"((?:data/(?:raw_pdfs|inbox_docs)/[^\s]+))", raw)
    if m:
        rel_path = m.group(1).lstrip("./")
        encoded = "/".join(quote(part) for part in rel_path.split("/"))
        return {"source_label": raw, "source_url": f"{REPO_BLOB_BASE}{encoded}"}

    cleaned = re.sub(r"^ملف\s*pdf\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
    norm_raw = _norm_source_token(cleaned)
    norm_title = _norm_source_token(title)
    repo_files = _discover_repo_source_files()

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
    return item


class QanoonGraphEngine:
    def __init__(self, articles: list[dict[str, Any]]) -> None:
        self.articles = articles
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._build_graph()

    def _build_graph(self) -> None:
        for art in self.articles:
            art_id = art["id"]
            art_num = str(art.get("article_number", "")).translate(ARABIC_TO_WESTERN_DIGITS).strip()
            title = art.get("legislation_title", "")
            self.nodes[art_id] = {
                "id": art_id,
                "kind": "article",
                "label": f"{title} - مادة ({art_num})",
                "legislation_title": title,
                "legislation_type": art.get("legislation_type", ""),
                "article_number": art_num,
                "effective_date": art.get("effective_date", ""),
                "status": art.get("status", "ساري"),
                "topic_tags": art.get("topic_tags", []),
                "official_source": art.get("official_source", ""),
                "text": art.get("text", ""),
            }

        for art in self.articles:
            art_id = art["id"]
            for rel in art.get("relations", []):
                target_id = rel.get("target_ref", "").strip()
                rel_type = rel.get("relation_type", "details_or_links")
                note = rel.get("note", "")
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
        clean = identifier.translate(ARABIC_TO_WESTERN_DIGITS).strip()
        for art in self.articles:
            if art["id"] == clean:
                return art
            num = str(art.get("article_number", "")).translate(ARABIC_TO_WESTERN_DIGITS).strip()
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
                    q_norm_val = np.linalg.norm(q_vec)
                    if q_norm_val > 0:
                        q_vec = q_vec / q_norm_val
                        sims = emb_matrix @ q_vec
                        sim_lookup = {
                            emb_ids[i]: float(sims[i])
                            for i in range(len(emb_ids))
                            if sims[i] > 0.55
                        }
            except Exception:
                sim_lookup = {}

        stop_tokens = {
            "في", "من", "على", "الى", "عن", "مع", "ما", "هو", "هي", "هل",
            "قانون", "نظام", "تعليمات", "قرار", "ماده", "الماده", "حكم", "احكام", "الاردن", "الاردني"
        }
        tokens = [tok for tok in q_norm.split() if len(tok) > 1 and tok not in stop_tokens]
        if not tokens:
            tokens = [tok for tok in q_norm.split() if len(tok) > 1]
        scored: list[tuple[float, dict[str, Any]]] = []

        for art in self.articles:
            haystack = normalize_text(" ".join([
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
        return [item[1] for item in scored]

    def trace_impact_chain(self, node_id: str, max_depth: int = 3) -> dict[str, Any]:
        if node_id not in self.nodes:
            return {"root": node_id, "impacted_nodes": [], "impact_paths": []}

        visited = {node_id}
        queue = deque([(node_id, 0)])
        impacted_nodes = []
        impact_paths = []

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self.adjacency.get(current, []):
                nxt = edge["target"]
                impact_paths.append({
                    "from": edge["source_label"],
                    "to": edge["target_label"],
                    "relation_type": edge["relation_type"],
                    "note": edge["note"],
                    "depth": depth + 1,
                })
                if nxt not in visited:
                    visited.add(nxt)
                    impacted_nodes.append(self.nodes[nxt])
                    queue.append((nxt, depth + 1))

        return {
            "root": self.nodes[node_id],
            "impacted_nodes": impacted_nodes,
            "impact_paths": impact_paths,
        }

    def detect_conflicts_and_changes(self) -> dict[str, list[dict[str, Any]]]:
        repeals, amendments, overlaps = [], [], []
        for edge in self.edges:
            rtype = edge["relation_type"]
            if rtype in {"repeals", "repealed_by"}:
                repeals.append(edge)
            elif rtype in {"amends", "amended_by"}:
                amendments.append(edge)
            elif rtype == "overlaps_with":
                overlaps.append(edge)
        return {"repeals": repeals, "amendments": amendments, "overlaps": overlaps}

    def analyze_legal_question(self, question: str, role: str = "lawyer") -> dict[str, Any]:
        candidates = self.search_articles(question, min_score=4.0)[:10]
        if not candidates:
            candidates = self.search_articles(question, min_score=2.0)[:6]

        if not candidates:
            return {
                "question": question,
                "role": role,
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

        try:
            from reranker import rerank_articles as _rr_fn
            reranked_pairs = _rr_fn(question, candidates, top_k=6)
            filtered_pairs = [(a, sc) for a, sc in reranked_pairs if sc >= 0.25]
            matched_articles = [a for a, _ in (filtered_pairs or reranked_pairs[:3])]
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
            if any(tag in e["relation_type"] for tag in ["overlaps_with", "repeals", "amends"])
        ]

        llm_answer, engine_mode = self._try_llm_synthesis(question, matched_articles, conflicts, role=role)
        verdict = llm_answer or self._rule_based_synthesis(question, matched_articles, conflicts)

        enriched_evidence = [enrich_article_with_source(a) for a in matched_articles]
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
            "has_conflict_or_overlap": len(conflicts) > 0,
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

        # 1. Local Ollama (qwen2.5:7b)
        ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
        ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        try:
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answer = (data.get("message", {}).get("content") or "").strip()
                if answer:
                    return answer, f"ollama:{ollama_model}"
        except Exception:
            pass

        # 2. Cloud fallback (Groq) for online deployment
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            try:
                payload = json.dumps({
                    "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    answer = (data["choices"][0]["message"]["content"] or "").strip()
                    if answer:
                        return answer, "groq:llama-3.3-70b"
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
        for art in self.articles:
            t = str(art.get("legislation_title") or "").strip()
            if t:
                counts[t] = counts.get(t, 0) + 1

        available = [
            {"legislation_title": t, "article_count": c}
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

        by_id = {a.get("id"): a for a in self.articles if a.get("id")}
        main_arts = [
            a for a in self.articles
            if str(a.get("legislation_title") or "").strip() == chosen
        ]
        if article_number and article_number.strip():
            num_q = article_number.strip()
            filtered_num = [a for a in main_arts if str(a.get("article_number") or "").strip() == num_q]
            if filtered_num:
                main_arts = filtered_num

        main_ids = {a.get("id") for a in main_arts if a.get("id")}
        stages: list[dict[str, Any]] = []

        # 1) محطات نفاذ التشريع المختار وعلاقاته الصادرة (تعديل / إلغاء / تداخل)
        for art in main_arts:
            enriched = enrich_article_with_source(art)
            rels = [
                r for r in (art.get("relations") or [])
                if isinstance(r, dict) and r.get("relation_type") in {"repeals", "amends", "overlaps_with", "repealed_by", "amended_by"}
            ]
            if rels:
                for rel in rels:
                    target = by_id.get(rel.get("target_ref"))
                    stages.append({
                        "date": str(art.get("effective_date") or "غير محدد"),
                        "change_type": rel.get("relation_type"),
                        "article_id": art.get("id"),
                        "article_number": art.get("article_number"),
                        "legislation_title": chosen,
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

        # 2) محطات لاحقة من تشريعات أخرى عدّلت أو ألغت أو تداخلت مع هذا التشريع
        for other in self.articles:
            if str(other.get("legislation_title") or "").strip() == chosen:
                continue
            enriched_other = enrich_article_with_source(other)
            for rel in (other.get("relations") or []):
                if not isinstance(rel, dict):
                    continue
                if rel.get("relation_type") not in {"repeals", "amends", "overlaps_with", "repealed_by", "amended_by"}:
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

        # 3) إذا لم تُسجّل علاقات تعديل صريحة، نعرض محطات النفاذ الأساسية للمواد مرتبة زمنياً
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
                    "legislation_title": chosen,
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
            "article_filter": article_number,
            "total_stages": len(stages),
            "available_legislations": available,
            "stages": stages,
        }
