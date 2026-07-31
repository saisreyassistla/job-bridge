/**
 * Merges job results from multiple sources. Since synthesis is now
 * handled in server/index.js (matching the Reddit project pattern),
 * this module provides a simple merge utility.
 */

/**
 * Merges and deduplicates jobs from multiple sources by title+company.
 *
 * @param {Array} primaryJobs - jobs from the primary source
 * @param {Array} supplementalJobs - jobs from supplemental sources
 * @returns {Promise<Array>} merged job list
 */
export async function mergeAndRankJobs(primaryJobs, supplementalJobs) {
  if (!supplementalJobs.length) return primaryJobs;
  if (!primaryJobs.length) return supplementalJobs;

  // Simple dedup: if same title+company exists, keep the primary one
  const seen = new Set(
    primaryJobs.map((j) => `${(j.title || "").toLowerCase()}|${(j.company || "").toLowerCase()}`)
  );

  const unique = supplementalJobs.filter((j) => {
    const key = `${(j.title || "").toLowerCase()}|${(j.company || "").toLowerCase()}`;
    return !seen.has(key);
  });

  return [...primaryJobs, ...unique].slice(0, 15);
}

export default { mergeAndRankJobs };
