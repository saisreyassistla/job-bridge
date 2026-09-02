import { test } from "node:test";
import assert from "node:assert";
import {
  saveSearchResults,
  resolveJobReference,
  clearContext
} from "../state/conversation-context.js";

test("resolves ordinal references to job IDs", async () => {
  const threadId = "test-thread-1";
  await clearContext(threadId);

  await saveSearchResults(threadId, [
    { title: "Warehouse Associate", applyUrl: "https://example.com/1", jobId: "job1" },
    { title: "Stock Clerk", applyUrl: "https://example.com/2", jobId: "job2" }
  ]);

  assert.strictEqual(await resolveJobReference(threadId, "tell me more about the second one"), "job2");
  assert.strictEqual(await resolveJobReference(threadId, "what about #1"), "job1");
});

test("returns null when there are no prior results", async () => {
  const threadId = "test-thread-2";
  await clearContext(threadId);

  assert.strictEqual(await resolveJobReference(threadId, "tell me more about the second one"), null);
});

test("resolves bare number references", async () => {
  const threadId = "test-thread-3";
  await clearContext(threadId);

  await saveSearchResults(threadId, [
    { title: "A", applyUrl: "https://example.com/a", jobId: "jobA" },
    { title: "B", applyUrl: "https://example.com/b", jobId: "jobB" },
    { title: "C", applyUrl: "https://example.com/c", jobId: "jobC" }
  ]);

  assert.strictEqual(await resolveJobReference(threadId, "tell me about 3"), "jobC");
});
