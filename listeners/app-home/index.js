import { WELCOME_MESSAGE } from "../assistant/welcome.js";

/**
 * Publishes a simple App Home view shown when a user opens JobBridge's
 * Home tab - mirrors the welcome message with a prompt to start a DM.
 *
 * @param {import("@slack/bolt").App} app
 */
export default function registerAppHome(app) {
  app.event("app_home_opened", async ({ event, client }) => {
    await client.views.publish({
      user_id: event.user,
      view: {
        type: "home",
        blocks: [
          {
            type: "section",
            text: { type: "mrkdwn", text: WELCOME_MESSAGE }
          },
          { type: "divider" },
          {
            type: "context",
            elements: [
              {
                type: "mrkdwn",
                text: "Send me a direct message to get started, or use `/find-job` in any channel."
              }
            ]
          }
        ]
      }
    });
  });
}
