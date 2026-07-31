/**
 * Builds the prompt for interview-prep mode. Uses both the job details
 * AND the user's resume (if available) to generate personalized questions.
 *
 * @param {object} job - the job details object
 * @param {string|null} resumeText - the user's resume (from context)
 * @returns {string} prompt text to send to the model
 */
export function buildInterviewPrepPrompt(job, resumeText = null) {
  const resumeSection = resumeText
    ? `\n\nThe user's resume/background:\n${resumeText}\n\nUse their specific experience to:\n- Suggest how they can frame their answers using their real background\n- Point out which of their skills match the job requirements\n- Identify any gaps they should be ready to address`
    : "";

  return `The user wants help preparing for an interview for this job:

Title: ${job.title || "Unknown"}
Company: ${job.company || "Unknown"}
Location: ${job.location || "Unknown"}
Description: ${job.description || "No description available"}
${resumeSection}

Generate 5 likely interview questions based on the skills,
responsibilities, and requirements mentioned in this job description.
For each question, provide:
1. The question itself
2. A brief tip on how to answer it well${resumeText ? " (personalized to their resume)" : ""}

Keep questions realistic for the role level. After listing the questions,
offer to do a mock interview: ask one question at a time, wait for the
user's answer, and give brief, encouraging feedback - one strength and
one thing to improve.

Keep the tone warm and encouraging.`;
}

export default buildInterviewPrepPrompt;
