import { handleMessage } from "../../ai/index.js";
import { appendHistory } from "../../state/conversation-context.js";

/**
 * Registers a listener for @JobBridge mentions in channels - e.g. a
 * shared #job-search channel where multiple community members might
 * post requests.
 *
 * @param {import("@slack/bolt").App} app
 */
export default function registerAppMentionListener(app) {
  app.event("app_mention", async ({ event, client, say }) => {
    const threadId = event.thread_ts || event.ts;

    // Strip the @mention from the message text.
    const userText = event.text.replace(/<@[^>]+>\s*/, "").trim();

    if (!userText) {
      await say({
        text: "Hi! Tell me what kind of job you're looking for and where, and I'll search for you.",
        thread_ts: threadId
      });
      return;
    }

    appendHistory(threadId, "user", userText);

    const { text, blocks } = await handleMessage(threadId, userText);

    appendHistory(threadId, "assistant", text);

    await say({
      text,
      blocks,
      thread_ts: threadId
    });
  });
}
