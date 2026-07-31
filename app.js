import "dotenv/config";
import { App } from "@slack/bolt";
import registerAssistantListeners from "./listeners/assistant/index.js";
import registerAppMentionListener from "./listeners/events/app-mention.js";
import registerFileSharedListener from "./listeners/events/file-shared.js";
import registerFindJobCommand from "./listeners/commands/find-job.js";
import registerReportDocCommand from "./listeners/commands/report-doc.js";
import registerAppHome from "./listeners/app-home/index.js";

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  appToken: process.env.SLACK_APP_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: true
});

registerAssistantListeners(app);
registerAppMentionListener(app);
registerFileSharedListener(app);
registerFindJobCommand(app);
registerReportDocCommand(app);
registerAppHome(app);

(async () => {
  await app.start();
  console.log("⚡️ JobBridge is running!");
})();

export default app;
