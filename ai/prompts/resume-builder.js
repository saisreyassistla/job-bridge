/**
 * Prompt for the resume builder. If the user has recent job search
 * results, the resume will be tailored toward those roles.
 *
 * @param {Array} lastResults - recent job search results (if any)
 * @returns {string} the resume builder prompt
 */
export function buildResumePrompt(lastResults = []) {
  const jobContext = lastResults.length > 0
    ? `\n\nThe user recently searched for these types of jobs:\n${lastResults.slice(0, 3).map(j => `- ${j.title} at ${j.company}`).join("\n")}\n\nTailor the resume toward these types of roles when possible.`
    : "";

  return `The user wants help building a resume.${jobContext}

Guide them through a friendly Q&A - ask ONE question at a time and wait
for their response:

1. What kind of work are you looking for? (or skip if we know from their job search)
2. What work experience do you have? (Include ANY experience: jobs, volunteering, caregiving, gig work, school projects - it all counts!)
3. What skills do you have? (Offer examples: customer service, teamwork, organization, bilingual, computer skills, physical work, etc.)
4. What's your availability? (full-time, part-time, specific days/hours)
5. Any certifications, licenses, or training? (food handler, driver's license, CPR, etc.)

Once you have enough info, create a clean, simple resume formatted in
plain text that's easy to copy-paste. Use these sections:
- Name & Contact (use placeholders if they haven't shared)
- Summary (2 sentences about what they bring)
- Experience (list roles with bullet points)
- Skills (relevant to target jobs)
- Availability

Keep it to one page equivalent. Be encouraging throughout - many users
feel insecure about not having a "proper" resume.

After generating the resume, say: "I've saved your resume info! Now I can
help you prepare for interviews based on your background. Just say
'help me prepare for an interview' when you find a job you're interested in."`;
}

// Keep backward compatibility
export const RESUME_BUILDER_PROMPT = buildResumePrompt();

export default { buildResumePrompt, RESUME_BUILDER_PROMPT };
