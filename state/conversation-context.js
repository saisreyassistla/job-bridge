/**
 * In-memory conversation context, keyed by Slack thread ID. Tracks the
 * last set of search results so users can refer to "the second one",
 * the last company/job title discussed, and recent message history for
 * passing to Claude as conversational context.
 *
 * For a production deployment this should be backed by a real store
 * (Redis, DynamoDB, etc.) since in-memory state won't survive restarts
 * or work across multiple server instances.
 */

const contexts = new Map();

const MAX_HISTORY = 10;

function defaultContext() {
  return {
    history: [],
    lastResults: [],
    lastViewedJob: null,
    lastJobTitle: null,
    userResume: null,
    activeFlow: null  // "resume_builder" | "interview_prep" | null
  };
}

/**
 * @param {string} threadId
 * @returns {object} context object (created if it doesn't exist)
 */
export function getContext(threadId) {
  if (!contexts.has(threadId)) {
    contexts.set(threadId, defaultContext());
  }
  return contexts.get(threadId);
}

/**
 * Appends a turn to the conversation history, trimming to MAX_HISTORY.
 */
export function appendHistory(threadId, role, content) {
  const context = getContext(threadId);
  context.history.push({ role, content });
  if (context.history.length > MAX_HISTORY) {
    context.history = context.history.slice(-MAX_HISTORY);
  }
}

/**
 * Stores the most recent search results so follow-up references
 * ("the second one") can be resolved.
 *
 * @param {string} threadId
 * @param {Array<{title: string, applyUrl: string, jobId?: string}>} jobs
 */
export function saveSearchResults(threadId, jobs) {
  const context = getContext(threadId);
  context.lastResults = jobs;
  if (jobs.length > 0 && jobs[0].title) {
    context.lastJobTitle = jobs[0].title;
  }
}

/**
 * Resolves a natural-language reference like "the second one" or "#2"
 * to a job_id from the last search results.
 *
 * @param {string} threadId
 * @param {string} message
 * @returns {string|null} job_id, or null if it can't be resolved
 */
export function resolveJobReference(threadId, message) {
  const context = getContext(threadId);
  if (!context.lastResults?.length) return null;

  // Order matters: more specific ordinal words are checked before plain
  // number words, since e.g. "the second one" contains "one" as a
  // substring and we want "second" to win.
  const ordinalMap = {
    first: 0, second: 1, third: 2, fourth: 3, fifth: 4,
    "1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4,
    "#1": 0, "#2": 1, "#3": 2, "#4": 3, "#5": 4,
    one: 0, two: 1, three: 2, four: 3, five: 4
  };

  const lower = message.toLowerCase();

  for (const [key, index] of Object.entries(ordinalMap)) {
    if (lower.includes(key) && context.lastResults[index]) {
      const job = context.lastResults[index];
      context.lastViewedJob = job;
      return job.jobId || job.applyUrl;
    }
  }

  // Fallback: a bare number, e.g. "tell me about 3"
  const numberMatch = lower.match(/\b(\d)\b/);
  if (numberMatch) {
    const index = parseInt(numberMatch[1], 10) - 1;
    if (context.lastResults[index]) {
      const job = context.lastResults[index];
      context.lastViewedJob = job;
      return job.jobId || job.applyUrl;
    }
  }

  return null;
}

/**
 * Clears context for a thread (e.g. on a "start over" request).
 */
export function clearContext(threadId) {
  contexts.delete(threadId);
}

/**
 * Saves the user's resume text so interview prep can reference it.
 */
export function saveResume(threadId, resumeText) {
  const context = getContext(threadId);
  context.userResume = resumeText;
}

/**
 * Gets the user's saved resume (if any).
 */
export function getResume(threadId) {
  const context = getContext(threadId);
  return context.userResume;
}

/**
 * Sets the active conversational flow.
 */
export function setActiveFlow(threadId, flow) {
  const context = getContext(threadId);
  context.activeFlow = flow;
}

/**
 * Gets the active conversational flow.
 */
export function getActiveFlow(threadId) {
  const context = getContext(threadId);
  return context.activeFlow;
}

export default {
  getContext,
  appendHistory,
  saveSearchResults,
  resolveJobReference,
  clearContext,
  saveResume,
  getResume,
  setActiveFlow,
  getActiveFlow
};

/**
 * Returns true if this thread has at least one ingested document.
 */
export function hasDocumentContext(threadId) {
  const context = getContext(threadId);
  return !!(context.documents?.length);
}

/**
 * Saves metadata about an ingested document for this thread.
 */
export function saveDocumentChunks(threadId, docMeta) {
  const context = getContext(threadId);
  context.documents = context.documents || [];
  context.documents.push(docMeta);
}

/**
 * Returns list of ingested document metadata for this thread.
 */
export function getDocuments(threadId) {
  return getContext(threadId).documents || [];
}

// ── User-level context (persists across threads) ──────────────────────────────
// Keyed by userId so "tell me more about #3" works even from a new message

const userContexts = new Map();

export function saveUserSearchResults(userId, jobs) {
  userContexts.set(userId, { lastResults: jobs, savedAt: Date.now() });
}

export function getUserSearchResults(userId) {
  const ctx = userContexts.get(userId);
  if (!ctx) return [];
  // Expire after 30 minutes
  if (Date.now() - ctx.savedAt > 30 * 60 * 1000) {
    userContexts.delete(userId);
    return [];
  }
  return ctx.lastResults || [];
}
