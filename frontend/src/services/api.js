const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function graphRequest(options = {}) {
  const {
    signal,
    limit,
    legislation_title,
    legislationTitle,
    ...requestOptions
  } = options;
  const parsedLimit = Number(limit);
  const safeLimit = Number.isInteger(parsedLimit) && parsedLimit > 0 ? parsedLimit : 180;
  const params = new URLSearchParams({ limit: String(safeLimit) });
  const title = typeof legislation_title === "string"
    ? legislation_title.trim()
    : typeof legislationTitle === "string"
      ? legislationTitle.trim()
      : "";
  if (title) params.set("legislation_title", title);
  return request(`/graph?${params.toString()}`, { ...requestOptions, signal });
}

async function request(path, { method = "GET", body, signal } = {}) {
  const headers = { Accept: "application/json" };
  const options = { method, headers, signal };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(API_BASE_URL + path, options);
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError("تعذّر الاتصال بالخادم. تحقق من اتصال الشبكة وحالة واجهة الخدمة.");
  }

  const raw = await response.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
  }

  if (!response.ok) {
    const detail = payload && typeof payload === "object"
      ? payload.detail || payload.message
      : payload;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || item.message || String(item)).join("، ")
      : typeof detail === "string" && detail.trim()
        ? detail
        : `تعذّر إكمال الطلب (HTTP ${response.status}).`;
    throw new ApiError(message, response.status, payload);
  }

  if (payload === null) return null;
  return payload;
}

export const api = {
  baseUrl: API_BASE_URL,
  health: (options) => request("/health", options),
  summary: (options) => request("/graph/summary", options),
  graph: graphRequest,
  changes: (options) => request("/graph/changes", options),
  timelineEvolution: ({ legislation_title = "", article_number = "" } = {}, options) => {
    const params = new URLSearchParams();
    if (typeof legislation_title === "string" && legislation_title.trim()) {
      params.set("legislation_title", legislation_title.trim());
    }
    if (typeof article_number === "string" && article_number.trim()) {
      params.set("article_number", article_number.trim());
    }
    const query = params.toString();
    return request(`/timeline/evolution${query ? `?${query}` : ""}`, options);
  },
  impact: (nodeId, options) => request(`/graph/impact/${encodeURIComponent(nodeId)}`, options),
  articles: (query = "", options) => request(`/articles?q=${encodeURIComponent(query)}`, options),
  article: (identifier, options) => request(`/articles/${encodeURIComponent(identifier)}`, options),
  ask: (payload, options) => request("/ask", { ...options, method: "POST", body: payload }),
  audit: (payload, options) => request("/audit", { ...options, method: "POST", body: payload }),
  ingestText: (payload, options) => request("/ingest/text", { ...options, method: "POST", body: payload }),
  ingestFile: (file, options) => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/ingest/file", { ...options, method: "POST", body: formData });
  },
  rebuildEmbeddings: (options) => request("/embeddings/rebuild", { ...options, method: "POST" })
};

export function getErrorMessage(error, fallback = "حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.") {
  return error instanceof Error && error.message ? error.message : fallback;
}
