/**
 * Apify client module — uses direct fetch calls to Apify API
 * (same pattern as the Reddit scraper project).
 */

const APIFY_TOKEN = process.env.APIFY_TOKEN;
const API_SERVER_URL = process.env.API_SERVER_URL || "http://localhost:3001";
const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 60000;

/**
 * Given a natural-language job search message, extracts search params,
 * calls the API server to start an Indeed scrape, and long-polls for
 * results. Returns an empty array on timeout or failure.
 *
 * @param {string} message
 * @returns {Promise<Array>} normalized job listings
 */
export async function fetchSupplementalListings(message) {
  const { search, location } = extractSearchParams(message);

  try {
    const startRes = await fetch(`${API_SERVER_URL}/api/jobs/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ search, location }),
    });

    if (!startRes.ok) {
      console.error("Failed to start search:", startRes.status);
      return [];
    }

    const { jobId } = await startRes.json();
    if (!jobId) return [];

    // Poll for results
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      const resultsRes = await fetch(`${API_SERVER_URL}/api/jobs/results/${jobId}`);

      if (resultsRes.ok) {
        const data = await resultsRes.json();
        return data.jobs || [];
      }

      // If 500, the run failed
      if (resultsRes.status === 500) {
        return [];
      }

      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }

    return []; // timed out
  } catch (err) {
    console.error("Supplemental search failed:", err.message);
    return [];
  }
}

/**
 * Simple extraction of job title + location from a natural-language message.
 */
function extractSearchParams(message) {
  const nearMatch = message.match(/(?:near|in)\s+([A-Za-z\s,]+?)(?:[.,!?]|$)/i);
  const location = nearMatch ? nearMatch[1].trim() : "";

  const search = message
    .replace(/(?:near|in)\s+[A-Za-z\s,]+/i, "")
    .replace(/i'?m looking for|i need|find me|search for/i, "")
    .trim();

  return { search: search || message, location };
}

export default { fetchSupplementalListings };
