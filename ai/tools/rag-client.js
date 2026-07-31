/**
 * RAG client — calls the Express proxy (/api/rag/query) which in turn
 * calls the Python Hybrid RAG FastAPI server (rag/api/server.py).
 *
 * Used by ai/index.js when a user asks a knowledge question that would
 * benefit from grounded document retrieval (e.g. "what does this company's
 * employee handbook say about PTO?", or career-guidance questions backed
 * by ingested documents).
 */

const API_SERVER_URL = process.env.API_SERVER_URL || "http://localhost:3001";

/**
 * Query the Hybrid RAG pipeline with a natural-language question.
 *
 * @param {string} question
 * @returns {Promise<{ answer: string, citations: Array } | null>}
 *   Returns null if the RAG server is unreachable (caller falls back gracefully).
 */
export async function queryRAG(question) {
  try {
    const res = await fetch(`${API_SERVER_URL}/api/rag/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    if (!res.ok) {
      console.warn("RAG query returned non-OK status:", res.status);
      return null;
    }

    return await res.json(); // { answer, citations }
  } catch (err) {
    console.warn("RAG server unreachable, skipping RAG:", err.message);
    return null;
  }
}

/**
 * Format RAG citations into a compact Slack-readable string.
 *
 * @param {Array<{ index, source, page, section }>} citations
 * @returns {string}
 */
export function formatCitations(citations) {
  if (!citations?.length) return "";
  const lines = citations.map((c) => {
    const page = c.page ? ` p.${c.page}` : "";
    const section = c.section ? ` — ${c.section}` : "";
    return `[${c.index}] ${c.source}${page}${section}`;
  });
  return "\n\n_Sources:_\n" + lines.join("\n");
}

export default { queryRAG, formatCitations };
