import { getJobDetails } from "./tools/job-details.js";
import { getCompanyData } from "./tools/company-data.js";
import { buildInterviewPrepPrompt } from "./prompts/interview-prep.js";
import { buildResumePrompt } from "./prompts/resume-builder.js";
import { callWithIndeedMCP, parseMcpResponse } from "./tools/mcp-client.js";
import { SYSTEM_PROMPT } from "./prompts/system-prompt.js";
import { queryRAG, formatCitations } from "./tools/rag-client.js";
import { hasDocumentContext, saveUserSearchResults, getUserSearchResults,
  getContext,
  saveSearchResults,
  resolveJobReference,
  saveResume,
  getResume,
  setActiveFlow,
  getActiveFlow,
  setChannelId
} from "../state/conversation-context.js";
import { fetchSupplementalListings } from "../server/apify-client.js";
import { formatJobResults, formatPlainText } from "../utils/formatting.js";

/**
 * Intent classifier that respects active conversation flows.
 * If user is mid-resume or mid-interview-prep, their replies stay in
 * that flow unless they explicitly ask for something else.
 */
async function classifyIntent(message, context, threadId) {
  const lower = message.toLowerCase();
  const activeFlow = await getActiveFlow(threadId);

  // Reset trigger — clears active flow
  if (/^(start over|reset|cancel|stop|nevermind|never mind|exit|quit)$/i.test(lower.trim())) {
    await setActiveFlow(threadId, null);
    return "reset";
  }

  // Company lookup always overrides active flows
  if (/work at|what.*(like|about).*work|good place to work|place to work|company.*review|culture|rating|salary at|pay at|is .*good|how is|as a company|as an employer|tell me about.*company/.test(lower)) {
    await setActiveFlow(threadId, null);
    return "company_lookup";
  }

  // If thread has an uploaded document, route to RAG unless it's
  // clearly a job search request
  // Check both threadId and channelId (DMs use channel as context key)
  if (await hasDocumentContext(threadId) || (context.channelId && await hasDocumentContext(context.channelId))) {
    const isExplicitJobSearch =
      /^(find|search|look for|get me|show me).*jobs?\b/i.test(lower) ||
      /^i('m| am) looking for.*jobs?\b/i.test(lower) ||
      /jobs? near|jobs? in|hiring near|remote jobs?/i.test(lower);
    const isResumeRequest =
      /don.?t have a resume|build.*resume|make.*resume/i.test(lower);
    const isCompanyLookup =
      /work at|good place to work|as a company|as an employer/i.test(lower);
    if (!isExplicitJobSearch && !isResumeRequest && !isCompanyLookup) {
      return "doc_followup";
    }
  }

  // Explicit intent keywords always override active flow
  if (/don'?t have a resume|build.*resume|make.*resume|help.*resume|resume.*help|create.*resume|need.*resume|write.*resume/.test(lower)) {
    return "resume_builder";
  }
  if (/mock interview|prepare.*interview|interview prep|practice.*question|help me prepare|get ready for/i.test(lower)) {
    return "interview_prep";
  }
  if (/work at|what.*(like|about).*work|good place to work|place to work|company.*review|culture|rating|salary at|pay at|is .* good|how is .* as.*employer/.test(lower)) {
    return "company_lookup";
  }
  // RAG: knowledge questions backed by ingested documents
  console.log("Intent debug:", lower.slice(0, 60), "| activeFlow:", activeFlow);
  if (/what (are|is|does|did|were)|how (do|does|did|to|many|much)|explain|tell me about|describe|list|define|show me|give me|what.*principle|leadership principle|amazon principle/i.test(lower) &&
      !/jobs?|position|role|hiring|apply|remote job|full.?time|part.?time/i.test(lower)) {
    return "rag_query";
  }
  if (context.lastResults?.length && /tell me more|more about|details on/.test(lower)) {
    return "job_details";
  }
  if (context.lastResults?.length && /^#?\d$/.test(lower.trim())) {
    return "job_details";
  }
  if (/tell me more|more about #|details on #/.test(lower)) {
    return "job_details";
  }
  // Explicit job search keywords — must be a clear request to FIND jobs
  if (/^(find|search|look for|get me|show me).*jobs?\b/i.test(lower) || /^i('m| am) looking for.*jobs?\b/i.test(lower)) {
    return "job_search";
  }

  // If user is in an active flow and didn't explicitly break out, stay in it
  if (activeFlow === "resume_builder") {
    return "resume_builder";
  }
  if (activeFlow === "interview_prep") {
    return "interview_prep";
  }

  // Fallback: check conversation history for resume context
  const recentHistory = context.history || [];
  const lastFewMessages = recentHistory.slice(-4).map(m => m.content || "").join(" ").toLowerCase();
  if (lastFewMessages.includes("resume") || lastFewMessages.includes("work experience") || lastFewMessages.includes("what kind of work")) {
    return "resume_builder";
  }

  return "job_search";
}

/**
 * Main entry point - called by Slack listeners with the user's message
 * and a threadId used to track conversation context.
 */
export async function handleMessage(threadId, message, userId = null, channelId = null) {
  const context = await getContext(threadId);
  if (channelId) {
    context.channelId = channelId;
    await setChannelId(threadId, channelId);
  }
  if (!context.lastResults?.length && userId) {
    const userResults = await getUserSearchResults(userId);
    if (userResults.length) await saveSearchResults(threadId, userResults);
  }
  const intent = await classifyIntent(message, context, threadId);

  switch (intent) {
    case "reset":
      await setActiveFlow(threadId, null);
      return { text: "No problem! What would you like to do? I can help you find jobs, look up companies, build a resume, or prepare for an interview." };

    case "job_search":
      await setActiveFlow(threadId, null);
      return handleJobSearch(threadId, message, context, userId);

    case "job_details": {
      await setActiveFlow(threadId, null);
      const jobRef = await resolveJobReference(threadId, message);
      if (!jobRef) {
        return { text: "I don't have any previous job results to reference. Search for jobs first (e.g. \"find me retail jobs in Seattle\"), then say \"tell me more about #1\"." };
      }
      const result = await getJobDetails(jobRef, context.history);
      return { text: result.text };
    }

    case "company_lookup": {
      await setActiveFlow(threadId, null);
      const companyName = extractCompanyName(message);
      const result = await getCompanyData(companyName, context.lastJobTitle, context.history);
      return { text: result.text };
    }

    case "interview_prep":
      await setActiveFlow(threadId, "interview_prep");
      return handleInterviewPrep(threadId, message, context);

    case "resume_builder":
      await setActiveFlow(threadId, "resume_builder");
      return handleResumeBuilder(threadId, message, context);

    case "rag_query":
      await setActiveFlow(threadId, null);
      return handleRAGQuery(message);

    default:
      return { text: "Sorry, I'm not sure how to help with that yet. Try asking me to find a job, look up a company, or help with your resume." };
  }
}

/**
 * Job search — calls Apify Indeed scraper.
 */
async function handleJobSearch(threadId, message, context, userId = null) {
  const jobs = await fetchSupplementalListings(message);

  if (jobs.length === 0) {
    return {
      text: "I couldn't find any jobs matching that search right now. Try being more specific with the job title or location, like \"cashier in Seattle, WA\"."
    };
  }

  await saveSearchResults(threadId, jobs);
  if (userId) await saveUserSearchResults(userId, jobs);


  const followUp = "\n\n💡 *What's next?*\n• Say \"tell me more about #2\" to get details on a job\n• Say \"help me with my resume\" to create a resume tailored to these jobs\n• Say \"help me prepare for an interview\" after picking a job";

  const plainText = formatPlainText(jobs) + followUp;

  return {
    text: plainText,
    blocks: formatJobResults(jobs)
  };
}

/**
 * Resume builder — stays in this flow until user explicitly asks for
 * something else. Passes full conversation history so Claude continues
 * the Q&A naturally.
 */
async function handleResumeBuilder(threadId, message, context) {
  const prompt = buildResumePrompt(context.lastResults || []);

  const resumeSystemPrompt = `You are a resume-building assistant. Your ONLY job right now is to help the user build their resume. 
Do NOT search for jobs. Do NOT look up companies. Do NOT offer to do other things.
Stay focused: gather their info step by step, then generate a clean resume.
Be warm and encouraging throughout.

${prompt}`;

  const response = await callWithIndeedMCP(
    [...context.history, { role: "user", content: message }],
    resumeSystemPrompt
  );

  const responseText = parseMcpResponse(response).text;

  // Only exit the flow when user explicitly asks for something else
  // (handled by the intent classifier's explicit keyword checks)
  // Save resume content if it looks complete
  const hasResumeStructure = 
    (responseText.includes("[YOUR NAME]") || responseText.includes("[Your Name]")) &&
    responseText.includes("Experience") &&
    responseText.includes("Skills");
  
  if (hasResumeStructure) {
    await saveResume(threadId, responseText);
  }

  return { text: responseText };
}

/**
 * Interview prep — uses job details + user's resume for personalized
 * questions. Stays in flow for mock interview back-and-forth.
 */
async function handleInterviewPrep(threadId, message, context) {
  const job = context.lastViewedJob;
  const resume = await getResume(threadId);

  if (!job && !context.lastResults?.length) {
    await setActiveFlow(threadId, null);
    return {
      text: "Let's find a job first so I can help you prepare for that specific interview! Tell me what kind of job you're looking for and where."
    };
  }

  const targetJob = job || (context.lastResults?.[0] || {});
  const prompt = buildInterviewPrepPrompt(targetJob, resume);

  const response = await callWithIndeedMCP(
    [...context.history, { role: "user", content: message }],
    SYSTEM_PROMPT + "\n\n" + prompt
  );

  const responseText = parseMcpResponse(response).text;

  let prefix = "";
  if (resume && targetJob.title) {
    prefix = `📋 *Preparing you for: ${targetJob.title} at ${targetJob.company || "the company"}*\n_Using your resume to personalize the questions._\n\n`;
  } else if (targetJob.title) {
    prefix = `📋 *Preparing you for: ${targetJob.title} at ${targetJob.company || "the company"}*\n\n`;
  }

  return { text: prefix + responseText };
}

/**
 * RAG query — routes knowledge questions through the Hybrid RAG pipeline
 * (Python FastAPI server) and returns a grounded answer with citations.
 * Falls back to a plain Claude response if the RAG server is unreachable.
 */
async function handleRAGQuery(message) {
  const ragResult = await queryRAG(message);

  if (ragResult?.answer) {
    const citations = formatCitations(ragResult.citations);
    return { text: ragResult.answer + citations };
  }

  // Fallback: answer directly with Claude (no RAG grounding)
  const response = await callWithIndeedMCP(
    [{ role: "user", content: message }],
    SYSTEM_PROMPT
  );
  return { text: parseMcpResponse(response).text };
}

function extractCompanyName(message) {
  const match = message.match(/(?:at|for)\s+([A-Z][\w&.\- ]+)/);
  return match ? match[1].trim() : message;
}

export default { handleMessage };
