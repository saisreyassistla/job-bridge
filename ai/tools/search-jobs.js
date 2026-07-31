import { callWithIndeedMCP, parseMcpResponse } from "./mcp-client.js";
import { SYSTEM_PROMPT } from "../prompts/system-prompt.js";

/**
 * Asks Claude (with the Indeed MCP server attached) to search for jobs
 * matching the user's criteria. The model decides how to call
 * search_jobs based on the natural-language request.
 *
 * @param {string} userMessage - natural-language job search request
 * @param {Array} priorMessages - prior conversation turns for context
 * @returns {Promise<{ text: string, toolCalls: Array, toolResults: Array }>}
 */
export async function searchJobs(userMessage, priorMessages = []) {
  const messages = [
    ...priorMessages,
    { role: "user", content: userMessage }
  ];

  const response = await callWithIndeedMCP(messages, SYSTEM_PROMPT);
  return parseMcpResponse(response);
}

export default searchJobs;
