import { callWithIndeedMCP, parseMcpResponse } from "./mcp-client.js";
import { SYSTEM_PROMPT } from "../prompts/system-prompt.js";

/**
 * Asks Claude to fetch and explain details for a specific job the user
 * referenced (e.g. "tell me more about the second one"). The calling
 * code is responsible for resolving "the second one" to a job_id using
 * state/conversation-context.js and including it in the prompt.
 *
 * @param {string} jobId - Indeed job ID resolved from conversation context
 * @param {Array} priorMessages - prior conversation turns for context
 * @returns {Promise<{ text: string, toolCalls: Array, toolResults: Array }>}
 */
export async function getJobDetails(jobId, priorMessages = []) {
  const messages = [
    ...priorMessages,
    {
      role: "user",
      content: `Get details for job_id "${jobId}" and explain it to me ` +
        `in plain language - what the pay, schedule, and requirements are.`
    }
  ];

  const response = await callWithIndeedMCP(messages, SYSTEM_PROMPT);
  return parseMcpResponse(response);
}

export default getJobDetails;
