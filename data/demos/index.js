import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Load a demo data file by name.
 * @param {string} name - filename without extension (e.g. "indeed-real")
 * @returns {object} parsed JSON data
 */
export function loadDemo(name) {
  const filePath = join(__dirname, `${name}.json`);
  return JSON.parse(readFileSync(filePath, "utf-8"));
}

/** Indeed: part-time retail in Renton, WA */
export function getIndeedRetailDemo() {
  return loadDemo("indeed-real");
}

/** Indeed: software engineer in Seattle, WA */
export function getIndeedSoftwareEngineerDemo() {
  return loadDemo("software-engineer-real");
}

/** LinkedIn: remote customer service */
export function getLinkedInCustomerServiceDemo() {
  return loadDemo("customer-service-linkedin-real");
}

export default { loadDemo, getIndeedRetailDemo, getIndeedSoftwareEngineerDemo, getLinkedInCustomerServiceDemo };
