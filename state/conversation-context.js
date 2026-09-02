import { createClient } from "redis";

const REDIS_URL = process.env.REDIS_URL;
const STATE_PREFIX = process.env.STATE_PREFIX || "jobbridge";
const MAX_HISTORY = 10;
const memoryContexts = new Map();
const memoryUserContexts = new Map();
let redisPromise;

function defaultContext() {
  return {
    history: [], lastResults: [], lastViewedJob: null, lastJobTitle: null,
    userResume: null, activeFlow: null, documents: []
  };
}

async function redis() {
  if (!REDIS_URL) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("REDIS_URL is required in production");
    }
    return null;
  }
  if (!redisPromise) {
    const client = createClient({ url: REDIS_URL });
    client.on("error", (error) => console.error("Redis state error:", error.message));
    redisPromise = client.connect().then(() => client);
  }
  return redisPromise;
}

const contextKey = (threadId) => `${STATE_PREFIX}:context:${threadId}`;
const userKey = (userId) => `${STATE_PREFIX}:user:${userId}`;

export async function getContext(threadId) {
  const client = await redis();
  if (client) {
    const stored = await client.get(contextKey(threadId));
    return stored ? JSON.parse(stored) : defaultContext();
  }
  if (!memoryContexts.has(threadId)) memoryContexts.set(threadId, defaultContext());
  return memoryContexts.get(threadId);
}

async function saveContext(threadId, context) {
  const client = await redis();
  if (client) await client.set(contextKey(threadId), JSON.stringify(context), { EX: 86400 });
  else memoryContexts.set(threadId, context);
}

export async function appendHistory(threadId, role, content) {
  const context = await getContext(threadId);
  context.history = [...context.history, { role, content }].slice(-MAX_HISTORY);
  await saveContext(threadId, context);
}

export async function saveSearchResults(threadId, jobs) {
  const context = await getContext(threadId);
  context.lastResults = jobs;
  if (jobs[0]?.title) context.lastJobTitle = jobs[0].title;
  await saveContext(threadId, context);
}

export async function resolveJobReference(threadId, message) {
  const context = await getContext(threadId);
  if (!context.lastResults?.length) return null;
  const ordinalMap = {
    first: 0, second: 1, third: 2, fourth: 3, fifth: 4,
    "1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4,
    "#1": 0, "#2": 1, "#3": 2, "#4": 3, "#5": 4,
    one: 0, two: 1, three: 2, four: 3, five: 4
  };
  const lower = message.toLowerCase();
  let index = Object.entries(ordinalMap).find(([key]) => lower.includes(key))?.[1];
  if (index === undefined) {
    const match = lower.match(/\b(\d)\b/);
    index = match ? Number(match[1]) - 1 : undefined;
  }
  const job = index === undefined ? null : context.lastResults[index];
  if (!job) return null;
  context.lastViewedJob = job;
  await saveContext(threadId, context);
  return job.jobId || job.applyUrl;
}

export async function clearContext(threadId) {
  const client = await redis();
  if (client) await client.del(contextKey(threadId));
  else memoryContexts.delete(threadId);
}

export async function saveResume(threadId, resumeText) {
  const context = await getContext(threadId);
  context.userResume = resumeText;
  await saveContext(threadId, context);
}

export async function getResume(threadId) {
  return (await getContext(threadId)).userResume;
}

export async function setActiveFlow(threadId, flow) {
  const context = await getContext(threadId);
  context.activeFlow = flow;
  await saveContext(threadId, context);
}

export async function getActiveFlow(threadId) {
  return (await getContext(threadId)).activeFlow;
}

export async function setChannelId(threadId, channelId) {
  const context = await getContext(threadId);
  context.channelId = channelId;
  await saveContext(threadId, context);
}

export async function hasDocumentContext(threadId) {
  return Boolean((await getContext(threadId)).documents?.length);
}

export async function saveDocumentChunks(threadId, docMeta) {
  const context = await getContext(threadId);
  context.documents = [...(context.documents || []), docMeta];
  await saveContext(threadId, context);
}

export async function getDocuments(threadId) {
  return (await getContext(threadId)).documents || [];
}

export async function saveUserSearchResults(userId, jobs) {
  const value = { lastResults: jobs, savedAt: Date.now() };
  const client = await redis();
  if (client) await client.set(userKey(userId), JSON.stringify(value), { EX: 1800 });
  else memoryUserContexts.set(userId, value);
}

export async function getUserSearchResults(userId) {
  const client = await redis();
  const stored = client ? await client.get(userKey(userId)) : memoryUserContexts.get(userId);
  if (!stored) return [];
  const context = typeof stored === "string" ? JSON.parse(stored) : stored;
  return Date.now() - context.savedAt <= 30 * 60 * 1000 ? context.lastResults || [] : [];
}

export default {
  getContext, appendHistory, saveSearchResults, resolveJobReference, clearContext,
  saveResume, getResume, setActiveFlow, getActiveFlow, hasDocumentContext,
  setChannelId, saveDocumentChunks, getDocuments, saveUserSearchResults,
  getUserSearchResults
};
