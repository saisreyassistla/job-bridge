import { handleMessage } from "../../ai/index.js";
import { appendHistory } from "../../state/conversation-context.js";

/**
 * Registers the /find-job slash command. Since slash commands don't
 * have a natural "thread", each invocation uses a context keyed by
 * the user + channel so repeated quick searches don't share state
 * across unrelated users.
 *
 * @param {import("@slack/bolt").App} app
 */
export default function registerFindJobCommand(app) {
  app.command("/find-job", async ({ command, ack, respond }) => {
    await ack();

    const query = command.text?.trim();

    if (!query) {
      await respond({
        text: "Tell me what you're looking for, e.g. `/find-job warehouse jobs in Tacoma, WA`",
        response_type: "ephemeral"
      });
      return;
    }

    const threadId = `slash-${command.user_id}-${command.channel_id}`;

    await appendHistory(threadId, "user", query);

    const { text, blocks } = await handleMessage(threadId, query);

    await appendHistory(threadId, "assistant", text);

    await respond({
      text,
      blocks,
      response_type: "in_channel"
    });
  });
}
