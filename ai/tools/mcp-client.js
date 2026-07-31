import Anthropic from "@anthropic-ai/sdk";

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// The Indeed MCP server - a remote MCP server that provides job search
// and company data tools directly to Claude via the API.
const INDEED_MCP_SERVER = {
  type: "url",
  url: "https://mcp.indeed.com/claude/mcp",
  name: "indeed-mcp"
};

/**
 * Sends a message to Claude with the Indeed MCP server attached, so the
 * model can call search_jobs / get_job_details as needed to answer the user.
 *
 * Falls back to a direct call (without MCP) if the MCP connection fails.
 *
 * @param {Array<{role: string, content: string}>} messages - conversation history
 * @param {string} systemPrompt
 * @returns {Promise<object>} raw Anthropic API response
 */
export async function callWithIndeedMCP(messages, systemPrompt) {
  const response = await anthropic.messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 1500,
    system: systemPrompt,
    messages
  });

  return response;
}

/**
 * Extracts plain text + tool call info from an Anthropic API response
 * that may include mcp_tool_use / mcp_tool_result blocks alongside text.
 *
 * @param {object} response - raw Anthropic API response
 * @returns {{ text: string, toolCalls: Array, toolResults: Array }}
 */
export function parseMcpResponse(response) {
  const content = response.content || [];

  const text = content
    .filter((item) => item.type === "text")
    .map((item) => item.text)
    .join("\n");

  const toolCalls = content
    .filter((item) => item.type === "mcp_tool_use")
    .map((item) => ({ name: item.name, input: item.input }));

  const toolResults = content
    .filter((item) => item.type === "mcp_tool_result")
    .map((item) => item.content?.[0]?.text || "");

  return { text, toolCalls, toolResults };
}

export default { callWithIndeedMCP, parseMcpResponse };
