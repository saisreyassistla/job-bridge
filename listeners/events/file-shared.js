import { appendHistory, saveDocumentChunks } from "../../state/conversation-context.js";

export default function registerFileSharedListener(app) {
  app.event("message", async ({ event, client }) => {
    if (!event.files?.length) return;
    if (event.bot_id) return;

    const threadId  = event.thread_ts || event.ts;
    const channelId = event.channel;
    // For DMs use channelId as context key so all messages in the DM find the document
    const contextKey = event.channel_type === "im" ? channelId : threadId;

    for (const file of event.files) {
      console.log("📎 File received:", file.name, file.filetype, file.url_private);

      const supported = ["pdf", "docx", "txt", "text", "plain", "html"];
      const fileType  = (file.filetype || "").toLowerCase();

      if (!supported.some((t) => fileType.includes(t))) {
        await client.chat.postMessage({
          channel: channelId,
          thread_ts: threadId,
          text: `I can read PDF, DOCX, and TXT files. I'm not able to process \`${file.filetype}\` files yet.`,
        });
        continue;
      }

      await client.chat.postMessage({
        channel: channelId,
        thread_ts: threadId,
        text: `:hourglass_flowing_sand: Reading *${file.name}*...`,
      });

      try {
        console.log("⬇️ Downloading from Slack CDN:", file.url_private_download || file.url_private);
        const fileRes = await fetch(file.url_private_download || file.url_private, {
          headers: { Authorization: `Bearer ${process.env.SLACK_BOT_TOKEN}` },
        });
        console.log("⬇️ Download status:", fileRes.status);
        if (!fileRes.ok) throw new Error(`Download failed: ${fileRes.status}`);

        const fileBuffer = Buffer.from(await fileRes.arrayBuffer());
        console.log("✅ Downloaded bytes:", fileBuffer.length);

        const RAG_URL = process.env.RAG_SERVER_URL || "http://localhost:8000";
        const SERVICE_API_KEY = process.env.SERVICE_API_KEY;
        console.log("📤 Sending to RAG:", `${RAG_URL}/ingest`);

        const formData = new FormData();
        const blob     = new Blob([fileBuffer], { type: getMimeType(fileType) });
        formData.append("file", blob, file.name);

        const ingestRes = await fetch(`${RAG_URL}/ingest`, {
          method: "POST",
          headers: { "x-service-key": SERVICE_API_KEY || "" },
          body: formData,
        });
        console.log("📤 Ingest status:", ingestRes.status);
        if (!ingestRes.ok) {
          const errText = await ingestRes.text();
          throw new Error(`Ingest failed: ${ingestRes.status} — ${errText}`);
        }

        const { chunks_added } = await ingestRes.json();

        // Save document context so follow-up questions route to RAG
        await saveDocumentChunks(contextKey, {
          fileName:    file.name,
          fileType,
          chunksAdded: chunks_added,
          ingestedAt:  new Date().toISOString(),
        });
        console.log("✅ Document context saved for key:", contextKey, "channelId:", channelId, "threadId:", threadId, "file:", file.name);
        console.log("✅ Chunks added:", chunks_added);

        const summaryRes = await fetch(`${RAG_URL}/query`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-service-key": SERVICE_API_KEY || "",
          },
          body: JSON.stringify({
            question: `Summarize the key points of the document "${file.name}" in plain language using bullet points.`,
          }),
        });

        const summary     = summaryRes.ok ? await summaryRes.json() : null;
        const summaryText = summary?.answer
          ? `:page_facing_up: *Here's what I found in ${file.name}:*\n\n${summary.answer}\n\n_Ask me anything about this document._`
          : `:white_check_mark: I've read *${file.name}* (${chunks_added} sections indexed). Ask me anything about it!`;

        await client.chat.postMessage({
          channel: channelId,
          thread_ts: threadId,
          text: summaryText,
        });

        await appendHistory(threadId, "assistant", summaryText);

      } catch (err) {
        console.error("❌ File ingestion error:", err.message);
        await client.chat.postMessage({
          channel: channelId,
          thread_ts: threadId,
          text: `Sorry, I had trouble reading *${file.name}*. Make sure the RAG server is running (\`pnpm rag\`) and try again.`,
        });
      }
    }
  });
}

function getMimeType(fileType) {
  const map = {
    pdf:   "application/pdf",
    docx:  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    txt:   "text/plain",
    text:  "text/plain",
    plain: "text/plain",
    html:  "text/html",
  };
  return map[fileType] || "application/octet-stream";
}
