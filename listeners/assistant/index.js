import { handleMessage } from "../../ai/index.js";
import { appendHistory } from "../../state/conversation-context.js";
import { WELCOME_MESSAGE } from "./welcome.js";

/**
 * Registers listeners for Slack's AI Assistant view - this powers the
 * primary DM-based interaction with JobBridge.
 *
 * @param {import("@slack/bolt").App} app
 */
export default function registerAssistantListeners(app) {
  // Fired when a user opens a new assistant thread (e.g. clicking
  // "JobBridge" in the sidebar for the first time).
  app.event("assistant_thread_started", async ({ event, client }) => {
    const { channel_id, thread_ts } = event.assistant_thread;

    await client.chat.postMessage({
      channel: channel_id,
      thread_ts,
      text: WELCOME_MESSAGE
    });
  });

  // Fired for each message in a DM with the assistant.
  app.message(async ({ message, client, say }) => {
    // Ignore messages from bots (including JobBridge itself) and
    // message edits/deletes.
    if (message.subtype || message.bot_id) return;

    const threadId  = message.thread_ts || message.ts;
    const contextKey = message.channel;  // Use channel as context key for DM document lookup
    const userText = message.text || "";

    // Show a "thinking" status while the agent works.
    await client.assistant.threads.setStatus({
      channel_id: message.channel,
      thread_ts: threadId,
      status: "is searching..."
    });

    appendHistory(threadId, "user", userText);

    try {
      const userId = message.user;
      const { text, blocks } = await handleMessage(contextKey, userText, userId);

      appendHistory(threadId, "assistant", text);

      await say({
        text,
        blocks,
        thread_ts: threadId
      });
    } catch (err) {
      console.error("Error handling message:", err);
      await say({
        text: `Sorry, something went wrong: ${err.message || "unknown error"}. Please try again.`,
        thread_ts: threadId
      });
    }
  });
}
