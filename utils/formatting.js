/**
 * Formats a list of job results as Slack Block Kit blocks - one
 * "section" block per job, with the title as a clickable apply link.
 *
 * @param {Array<{title: string, applyUrl: string, company?: string,
 *   location?: string, source?: string}>} jobs
 * @returns {Array} Slack Block Kit blocks
 */
export function formatJobResults(jobs) {
  if (!jobs.length) {
    return [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: "I couldn't find any matching jobs right now. Want to try a different location or job title?"
        }
      }
    ];
  }

  const blocks = [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `Here's what I found (${jobs.length} result${jobs.length === 1 ? "" : "s"}):`
      }
    },
    { type: "divider" }
  ];

  jobs.forEach((job, index) => {
    const lines = [`*${index + 1}. <${job.applyUrl}|${job.title}>*`];
    if (job.company) lines.push(job.company);
    if (job.location) lines.push(job.location);
    if (job.source === "linkedin") lines.push("_via LinkedIn_");

    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: lines.join("\n") }
    });
  });

  blocks.push({
    type: "context",
    elements: [
      {
        type: "mrkdwn",
        text: "Tap a title to apply, or ask me \"tell me more about #2\" for details on any listing."
      }
    ]
  });

  return blocks;
}

/**
 * Plain-text fallback (used for notifications, accessibility, or
 * clients that don't render Block Kit).
 *
 * @param {Array<{title: string, applyUrl: string, company?: string}>} jobs
 * @returns {string}
 */
export function formatPlainText(jobs) {
  if (!jobs.length) {
    return "I couldn't find any matching jobs right now. Want to try a different location or job title?";
  }

  const lines = jobs.map((job, index) => {
    const company = job.company ? ` at ${job.company}` : "";
    return `${index + 1}. ${job.title}${company} - ${job.applyUrl}`;
  });

  return `Here's what I found:\n${lines.join("\n")}`;
}

export default { formatJobResults, formatPlainText };
