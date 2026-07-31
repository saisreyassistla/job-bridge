/**
 * /report-doc command — runs the full RAG pipeline on a question and
 * posts a detailed per-stage chunk analysis back to Slack.
 *
 * Usage: /report-doc What are Amazon leadership principles?
 */

const API_SERVER_URL = process.env.API_SERVER_URL || "http://localhost:3002";

export default function registerReportDocCommand(app) {
  app.command("/report-doc", async ({ command, ack, respond }) => {
    await ack();

    const question = command.text?.trim();
    if (!question) {
      await respond({
        response_type: "ephemeral",
        text: "Usage: `/report-doc <your question>`\nExample: `/report-doc What are Amazon leadership principles?`",
      });
      return;
    }

    await respond({
      response_type: "ephemeral",
      text: `:hourglass_flowing_sand: Running pipeline analysis for: _"${question}"_...`,
    });

    try {
      const res = await fetch(`${API_SERVER_URL}/api/rag/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) throw new Error(`Report server returned ${res.status}`);

      const report = await res.json();
      const blocks = buildReportBlocks(question, report);

      await respond({
        response_type: "ephemeral",
        text: `Document analysis report for: "${question}"`,
        blocks,
      });
    } catch (err) {
      console.error("Report command failed:", err);
      await respond({
        response_type: "ephemeral",
        text: `Sorry, couldn't generate the report. Make sure \`pnpm rag\` is running and documents are ingested.\nError: ${err.message}`,
      });
    }
  });
}

function buildReportBlocks(question, report) {
  const blocks = [];

  blocks.push({
    type: "header",
    text: { type: "plain_text", text: "📊 Document Analysis Report", emoji: true },
  });

  blocks.push({
    type: "section",
    text: {
      type: "mrkdwn",
      text: `*Query:* ${question}\n*Rewritten:* ${report.rewritten_query || "—"}`,
    },
  });

  const s = report.stats || {};
  const l = report.latency_ms || {};

  blocks.push({
    type: "section",
    fields: [
      { type: "mrkdwn", text: `*BM25 retrieved*\n${s.bm25_count || 0} chunks` },
      { type: "mrkdwn", text: `*Dense retrieved*\n${s.dense_count || 0} chunks` },
      { type: "mrkdwn", text: `*After RRF*\n${s.rrf_count || 0} chunks` },
      { type: "mrkdwn", text: `*After reranking*\n${s.reranked_count || 0} chunks` },
      { type: "mrkdwn", text: `*BM25 ∩ Dense overlap*\n${s.overlap_bm25_dense || 0} chunks` },
      { type: "mrkdwn", text: `*Reranker*\n${s.reranker_type || "cross-encoder"}` },
    ],
  });

  blocks.push({ type: "divider" });

  // BM25 top 5
  const bm25 = (report.stages?.bm25 || []).slice(0, 5);
  if (bm25.length) {
    blocks.push({ type: "section", text: { type: "mrkdwn", text: "*🔵 BM25 — Top 5 lexical matches*" } });
    bm25.forEach((chunk, i) => {
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*${i + 1}.* [Score: \`${chunk.score?.toFixed(3)}\`] *${chunk.section || "General"}* (p.${chunk.page})\n>${chunk.text.slice(0, 140)}…`,
        },
      });
    });
    blocks.push({ type: "divider" });
  }

  // Dense top 5
  const dense = (report.stages?.dense || []).slice(0, 5);
  if (dense.length) {
    blocks.push({ type: "section", text: { type: "mrkdwn", text: "*🟢 Dense — Top 5 semantic matches*" } });
    dense.forEach((chunk, i) => {
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*${i + 1}.* [Cosine: \`${chunk.score?.toFixed(3)}\`] *${chunk.section || "General"}* (p.${chunk.page})\n>${chunk.text.slice(0, 140)}…`,
        },
      });
    });
    blocks.push({ type: "divider" });
  }

  // RRF top 5
  const rrf = (report.stages?.rrf || []).slice(0, 5);
  if (rrf.length) {
    blocks.push({ type: "section", text: { type: "mrkdwn", text: "*🟡 RRF — Top 5 fused results*" } });
    rrf.forEach((chunk, i) => {
      const bm25r  = chunk.bm25_rank  ? `BM25 #${chunk.bm25_rank}`  : "BM25 —";
      const denser = chunk.dense_rank ? `Dense #${chunk.dense_rank}` : "Dense —";
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*${i + 1}.* [RRF: \`${chunk.score?.toFixed(4)}\`] ${bm25r} · ${denser}\n*${chunk.section || "General"}* (p.${chunk.page})\n>${chunk.text.slice(0, 120)}…`,
        },
      });
    });
    blocks.push({ type: "divider" });
  }

  // Reranked top 5
  const reranked = report.stages?.reranked || [];
  if (reranked.length) {
    blocks.push({ type: "section", text: { type: "mrkdwn", text: "*🔴 Reranked — Final top chunks*" } });
    reranked.forEach((chunk) => {
      const delta    = chunk.rank_delta;
      const deltaStr = delta === null || delta === undefined ? ""
        : delta > 0 ? ` ↑${delta}` : delta < 0 ? ` ↓${Math.abs(delta)}` : " —";
      const rrfStr = chunk.rrf_rank ? `RRF #${chunk.rrf_rank}` : "new entry";
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*#${chunk.rank}${deltaStr}* [Score: \`${chunk.score?.toFixed(3)}\`] from ${rrfStr}\n*${chunk.section || "General"}* (p.${chunk.page})\n>${chunk.text.slice(0, 140)}…`,
        },
      });
    });
    blocks.push({ type: "divider" });
  }

  // Generated answer
  if (report.answer) {
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*✅ Generated answer*\n${report.answer.slice(0, 600)}${report.answer.length > 600 ? "…" : ""}`,
      },
    });
    blocks.push({ type: "divider" });
  }

  // Latency
  if (l.total) {
    const stages = [
      ["Query processing", l.query_processing],
      ["BM25 retrieval",   l.bm25],
      ["Dense retrieval",  l.dense],
      ["RRF fusion",       l.rrf],
      ["Reranking",        l.reranking],
      ["Context + prompt", l.context_prompt],
      ["Generation",       l.generation],
    ];
    const latencyText = stages
      .filter(([, v]) => v)
      .map(([label, v]) => `${label}: \`${v}ms\``)
      .join("  ·  ");

    blocks.push({
      type: "context",
      elements: [{
        type: "mrkdwn",
        text: `⏱ *Latency* — ${latencyText}  ·  *Total: \`${l.total}ms\`*`,
      }],
    });
  }

  return blocks;
}
