/**
 * Company data lookup — uses Claude to provide balanced company info
 * including culture, pay, ratings, and work environment.
 */

import Anthropic from "@anthropic-ai/sdk";

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

/**
 * @param {string} companyName
 * @param {string} jobTitle - optional, for salary context
 * @param {Array} priorMessages - conversation history
 * @returns {Promise<{ text: string }>}
 */
export async function getCompanyData(companyName, jobTitle, priorMessages = []) {
  const jobContext = jobTitle ? ` for the role of ${jobTitle}` : "";

  const prompt = `You are a helpful job search assistant. Give a balanced, 
factual summary of what it's like to work at ${companyName}${jobContext}.

Include:
- Overall employee sentiment (positive and negative)
- Work culture and environment
- Pay and benefits (give typical ranges if known)
- Work-life balance
- Career growth opportunities
- Any well-known challenges employees face

Keep it honest and balanced — mention both positives and negatives.
Write in plain, simple language for someone who may be a first-time job seeker.
Keep the response concise — 5-8 bullet points max.
End with a one-sentence overall recommendation.`;

  const response = await anthropic.messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 800,
    messages: [
      ...priorMessages.slice(-4),
      { role: "user", content: prompt }
    ]
  });

  return { text: response.content[0].text };
}

export default { getCompanyData };
