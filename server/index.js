import "dotenv/config";
import express from "express";
import Anthropic from "@anthropic-ai/sdk";

const app = express();
app.use(express.json());

const PORT = process.env.API_SERVER_PORT || 3001;
const APIFY_TOKEN = process.env.APIFY_TOKEN;
const SERVICE_API_KEY = process.env.SERVICE_API_KEY;
const UPSTREAM_TIMEOUT_MS = Number(process.env.UPSTREAM_TIMEOUT_MS || 30000);
const APIFY_POLL_TIMEOUT_MS = Number(process.env.APIFY_POLL_TIMEOUT_MS || 120000);
const JOB_QUERY_TTL_MS = Number(process.env.JOB_QUERY_TTL_MS || 15 * 60 * 1000);
const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// jobId → original query, so GET /results/:jobId doesn't need the query in the URL
const jobQueries = new Map();

function requireServiceKey(req, res, next) {
  if (!SERVICE_API_KEY) {
    return res.status(503).json({ error: "Service authentication is not configured" });
  }
  if (req.get("x-service-key") !== SERVICE_API_KEY) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
}

function fetchWithTimeout(url, options = {}, timeoutMs = UPSTREAM_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal })
    .finally(() => clearTimeout(timeout));
}

/**
 * POST /api/jobs/search
 * body: { search: string, location: string }
 * Starts the Indeed scraper actor on Apify and returns a jobId for polling.
 */
app.post("/api/jobs/search", requireServiceKey, async (req, res) => {
  const search = typeof req.body.search === "string" ? req.body.search.trim() : "";
  const location = typeof req.body.location === "string" ? req.body.location.trim() : "";

  if (!search || search.length > 200) {
    return res.status(400).json({ error: "search is required" });
  }
  if (!APIFY_TOKEN) {
    return res.status(503).json({ error: "Job search is not configured" });
  }

  try {
    const r = await fetchWithTimeout(
      `https://api.apify.com/v2/acts/misceres~indeed-scraper/runs?token=${APIFY_TOKEN}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          position: search,
          location: location || "",
          country: process.env.INDEED_MCP_COUNTRY_DEFAULT || "US",
          maxItemsPerSearch: parseInt(process.env.APIFY_MAX_RESULTS || "15", 10),
          saveOnlyUniqueItems: true,
          parseCompanyDetails: false,
        }),
      }
    );

    const json = await r.json();

    if (!r.ok) {
      console.error("Apify start failed:", json);
      return res.status(502).json({ error: "Failed to start Indeed search" });
    }

    const jobId = json.data.id;
    jobQueries.set(jobId, `${search} in ${location}`);
    res.json({ jobId });
  } catch (err) {
    console.error("Failed to start Apify run:", err);
    res.status(502).json({ error: "Failed to start job search" });
  }
});

/**
 * GET /api/jobs/results/:jobId
 * Long-polls the Apify run until it reaches a terminal state,
 * then fetches results and synthesizes them with Claude.
 */
app.get("/api/jobs/results/:jobId", requireServiceKey, async (req, res) => {
  const { jobId } = req.params;
  const query = jobQueries.get(jobId) || "";
  const deadline = Date.now() + APIFY_POLL_TIMEOUT_MS;

  try {
    // Long-poll Apify until the run reaches a terminal state
    let datasetId = "";
    while (true) {
      if (Date.now() >= deadline) {
        jobQueries.delete(jobId);
        return res.status(504).json({ error: "Job search timed out" });
      }
      const r = await fetchWithTimeout(
        `https://api.apify.com/v2/actor-runs/${jobId}?token=${APIFY_TOKEN}`
      );
      const run = await r.json();
      const status = run.data.status;

      if (status === "SUCCEEDED") {
        datasetId = run.data.defaultDatasetId;
        break;
      }
      if (["FAILED", "ABORTED", "TIMED-OUT"].includes(status)) {
        jobQueries.delete(jobId);
        return res.status(500).json({ error: `Apify run ${status}` });
      }

      await new Promise((resolve) => setTimeout(resolve, 4000));
    }

    // Fetch raw scraped items
    const itemsRes = await fetchWithTimeout(
      `https://api.apify.com/v2/datasets/${datasetId}/items?token=${APIFY_TOKEN}&limit=50&clean=true`
    );
    const items = await itemsRes.json();

    // Synthesize with Claude
    const result = await synthesizeJobs(query, items);
    jobQueries.delete(jobId);
    res.json({ ...result, query });
  } catch (err) {
    console.error(`Failed to fetch results for run ${jobId}:`, err);
    res.status(502).json({ error: "Failed to fetch job results" });
  }
});

/**
 * Uses Claude to analyze and format Indeed job results into a structured
 * response for the Slack bot.
 */
async function synthesizeJobs(query, items) {
  // Normalize raw Indeed items into a readable corpus
  const corpus = items
    .slice(0, 25)
    .map(
      (item, i) =>
        `[${i + 1}] ${item.positionName || item.title || "Untitled"} at ${item.company || "Unknown"} — ${item.location || "N/A"} | Salary: ${item.salary || "Not listed"} | URL: ${item.url || item.externalApplyLink || "N/A"}`
    )
    .join("\n");

  if (!process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY === "your-anthropic-api-key") {
    // Return raw results without AI synthesis if no API key
    return {
      jobs: items.slice(0, 15).map((item) => ({
        title: item.positionName || item.title || "Untitled role",
        company: item.company || "Unknown",
        location: item.location || "",
        salary: item.salary || null,
        applyUrl: item.url || item.externalApplyLink || null,
        source: "indeed",
      })),
      summary: `Found ${items.length} jobs matching "${query}".`,
    };
  }

  try {
    const msg = await anthropic.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 2048,
      messages: [
        {
          role: "user",
          content: `You are a helpful job search assistant. Analyze these Indeed job listings for the query "${query}".

Return raw JSON only (no markdown fences) matching this exact shape:
{
  "jobs": [
    {
      "title": "...",
      "company": "...",
      "location": "...",
      "salary": "... or null",
      "applyUrl": "...",
      "whyGoodFit": "1 sentence in plain language about why this is relevant",
      "source": "indeed"
    }
  ],
  "summary": "2-3 sentence plain-language summary of results for a first-time job seeker"
}

Rules:
- Return the top 8 most relevant jobs
- Write in simple, encouraging language (the user may be a first-time job seeker)
- If salary is not listed, set it to null
- Keep applyUrl exactly as given

DATA:
${corpus}`,
        },
      ],
    });

    const text = msg.content[0].type === "text" ? msg.content[0].text : "{}";
    const clean = text.replace(/^```json\n?/, "").replace(/\n?```$/, "").trim();
    return JSON.parse(clean);
  } catch (err) {
    console.error("Synthesis failed, returning raw results:", err.message);
    // Fallback: return raw results without AI synthesis
    return {
      jobs: items.slice(0, 8).map((item) => ({
        title: item.positionName || item.title || "Untitled role",
        company: item.company || "Unknown",
        location: item.location || "",
        salary: item.salary || null,
        applyUrl: item.url || item.externalApplyLink || null,
        source: "indeed",
      })),
      summary: `Found ${items.length} jobs matching "${query}".`,
    };
  }
}

app.get("/health", (req, res) => res.json({ status: "ok" }));

app.listen(PORT, () => {
  console.log(`JobBridge API server listening on port ${PORT}`);
});

export default app;


// ─────────────────────────────────────────────────────────────────────────────
// RAG proxy — forwards queries to the Python RAG FastAPI server (rag/api/server.py)
// so the Slack bot has a single Node API to talk to.
// ─────────────────────────────────────────────────────────────────────────────

const RAG_SERVER_URL = process.env.RAG_SERVER_URL || "http://localhost:8000";

/**
 * POST /api/rag/query
 * body: { question: string }
 * Proxies to the Python RAG server and returns answer + citations.
 */
app.post("/api/rag/query", requireServiceKey, async (req, res) => {
  const question = typeof req.body.question === "string" ? req.body.question.trim() : "";
  if (!question || question.length > 2000) {
    return res.status(400).json({ error: "question is required" });
  }

  try {
    const r = await fetchWithTimeout(`${RAG_SERVER_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    if (!r.ok) {
      const err = await r.text();
      console.error("RAG server error:", err);
      return res.status(502).json({ error: "RAG server returned an error" });
    }

    const data = await r.json();
    res.json(data); // { answer, citations }
  } catch (err) {
    console.error("RAG proxy failed:", err.message);
    res.status(502).json({ error: "Could not reach RAG server" });
  }
});

/**
 * POST /api/rag/ingest
 * Streams a multipart file upload to the Python RAG ingest endpoint.
 */
app.post("/api/rag/ingest", requireServiceKey, async (req, res) => {
  const contentType = req.headers["content-type"];
  if (!contentType?.startsWith("multipart/form-data")) {
    return res.status(400).json({ error: "multipart file upload is required" });
  }

  try {
    const r = await fetchWithTimeout(`${RAG_SERVER_URL}/ingest`, {
      method: "POST",
      headers: { "content-type": contentType },
      body: req,
      duplex: "half",
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      return res.status(502).json({ error: data.detail || "RAG ingestion failed" });
    }
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "Could not reach RAG server. Is `npm run rag` running?" });
  }
});

/**
 * GET /api/rag/health
 */
app.get("/api/rag/health", async (req, res) => {
  try {
    const r = await fetchWithTimeout(`${RAG_SERVER_URL}/health`);
    const data = await r.json();
    res.status(data.ready ? 200 : 503).json({ rag: data.ready ? "ok" : "starting", ...data });
  } catch (err) {
    res.status(502).json({ error: "RAG server not reachable" });
  }
});

/**
 * POST /api/rag/report
 */
app.post("/api/rag/report", requireServiceKey, async (req, res) => {
  const question = typeof req.body.question === "string" ? req.body.question.trim() : "";
  if (!question || question.length > 2000) return res.status(400).json({ error: "question is required" });
  try {
    const r = await fetchWithTimeout(`${RAG_SERVER_URL}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!r.ok) throw new Error(`RAG server returned ${r.status}`);
    const data = await r.json();
    res.json(data);
  } catch (err) {
    console.error("RAG report proxy failed:", err.message);
    res.status(502).json({ error: "Could not reach RAG server" });
  }
});
