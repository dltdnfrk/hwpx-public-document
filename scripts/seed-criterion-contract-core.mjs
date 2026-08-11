import { createHash } from "node:crypto";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { normalizeCriterion, projectRoot } from "./seed-artifacts-lib.mjs";

export { normalizeCriterion, projectRoot };

export const APPROVED_SEED_SHA256 = "6193eb71e1183a57c6fcd3c1accff64bdbc815fda587bd433171f110ce8ab310";

export const criterionContractPaths = {
  "AC-01": [
    "artifacts/provenance/upstream-lock.json",
    "artifacts/provenance/sbom.spdx.json",
    "artifacts/provenance/THIRD_PARTY_NOTICES.md",
    "artifacts/provenance/genoffice-docs-port.json",
    "artifacts/provenance/genoffice-runtime-manifest.json",
    "artifacts/provenance/genoffice-runtime-input-lock.json",
    "artifacts/provenance/foundation-runtime.json",
  ],
  "AC-02": ["artifacts/document-model/schema.json", "artifacts/document-model/recovery-matrix.json"],
  "AC-03": ["artifacts/templates/catalog-manifest.json", "artifacts/templates/update-rollback-evidence.json"],
  "AC-04": ["artifacts/privacy/provider-boundary-evidence.json", "artifacts/ai/proposal-lifecycle-evidence.json"],
  "AC-05": [
    "artifacts/formats/authoring-capability-manifest.json",
    "artifacts/formats/format-capability-matrix.json",
    "artifacts/formats/loss-reports.jsonl",
    "artifacts/formats/export-validation-evidence.json",
  ],
  "AC-06": ["artifacts/export/batch-lifecycle-evidence.json", "artifacts/export/batch-result-manifest.json"],
  "AC-07": [
    "artifacts/compatibility/corpus-manifest.json",
    "artifacts/compatibility/observations.jsonl",
    "artifacts/compatibility/verdict-summary.json",
  ],
  "AC-08": [
    "artifacts/accessibility/automated-results.json",
    "artifacts/accessibility/manual-scenarios.json",
    "artifacts/ui/reference-comparison.json",
  ],
  "AC-09": ["artifacts/performance/environment.json", "artifacts/performance/results.json"],
  "AC-10": ["artifacts/release/local-functional-candidate.json", "artifacts/release/evidence-index.json"],
};

export const formats = ["hwpx", "hwp", "docx", "markdown"];
export const approvedProviders = ["anthropic", "gemini", "openai", "openai-compatible"];
export const requiredClientOperations = {
  hwpx: ["polaris-office-reopen", "hancom-official-reopen"],
  hwp: ["polaris-office-reopen", "hancom-official-reopen"],
  docx: ["microsoft-word-reopen", "genoffice-docs-reopen"],
  markdown: ["commonmark-validate", "approved-rendering"],
};

export function check(id, passed, detail) {
  return { id, passed: passed === true, detail };
}

export function result(criterion, checks, blockers, successSummary) {
  const failed = checks.filter((entry) => !entry.passed);
  const verdict = failed.length > 0 ? "fail" : blockers.length > 0 ? "blocked" : "pass";
  const summary = verdict === "pass"
    ? successSummary
    : verdict === "blocked"
      ? `${successSummary} Required external observations remain blocked.`
      : `${failed.length} criterion-specific check(s) failed.`;
  return { criterion, verdict, summary, blockers: verdict === "fail" ? [] : blockers, checks };
}

export function readerAt(root) {
  const rootPath = realpathSync(resolve(root));
  const safe = (path) => {
    if (typeof path !== "string" || path.length === 0 || isAbsolute(path) || path.split(/[\\/]/u).includes("..")) {
      throw new Error(`unsafe project-relative path: ${String(path)}`);
    }
    const target = resolve(rootPath, path);
    const lexical = relative(rootPath, target);
    if (lexical.startsWith("..") || isAbsolute(lexical)) throw new Error(`path escapes root: ${path}`);
    const physical = realpathSync(target);
    const physicalRelative = relative(rootPath, physical);
    if (physicalRelative.startsWith("..") || isAbsolute(physicalRelative)) throw new Error(`symlink escapes root: ${path}`);
    if (!statSync(physical).isFile()) throw new Error(`evidence is not a file: ${path}`);
    return physical;
  };
  const bytes = (path) => readFileSync(safe(path));
  const text = (path) => bytes(path).toString("utf8");
  const json = (path) => JSON.parse(text(path));
  const records = (path) => {
    const raw = text(path).trim();
    if (raw.length === 0) return [];
    if (raw.startsWith("[")) return JSON.parse(raw);
    return raw.split(/\r?\n/u).filter(Boolean).map((line) => JSON.parse(line));
  };
  const sha256 = (path) => createHash("sha256").update(bytes(path)).digest("hex");
  const size = (path) => statSync(safe(path)).size;
  return { rootPath, safe, text, json, records, sha256, size };
}

function evidenceRecords(value, found = [], excludedKeys = new Set()) {
  if (Array.isArray(value)) {
    for (const entry of value) evidenceRecords(entry, found, excludedKeys);
  } else if (value !== null && typeof value === "object") {
    if (typeof value.path === "string" && typeof value.sha256 === "string") found.push(value);
    for (const [key, entry] of Object.entries(value)) {
      if (!excludedKeys.has(key)) evidenceRecords(entry, found, excludedKeys);
    }
  }
  return found;
}

export function identityCheck(snapshot, reader, minimum, excludedKeys = []) {
  const records = evidenceRecords(snapshot, [], new Set(excludedKeys));
  const errors = [];
  for (const record of records) {
    try {
      const digest = reader.sha256(record.path);
      if (record.sha256 !== digest && record.sha256 !== `sha256:${digest}`) errors.push(`hash drift: ${record.path}`);
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    }
  }
  const passed = records.length >= minimum && errors.length === 0;
  return check("evidence.identity", passed, passed ? `${records.length} evidence identities verified` : errors.join("; ") || `expected at least ${minimum} evidence records`);
}

export function loadSnapshot(criterion, reader) {
  const paths = criterionContractPaths[criterion];
  const entries = paths.map((path) => [path, path.endsWith(".jsonl") ? reader.records(path) : path.endsWith(".json") ? reader.json(path) : reader.text(path)]);
  return Object.fromEntries(entries);
}

const valueAt = (source, path) => path.split(".").reduce((value, key) => value?.[key], source);

export function booleanChecks(prefix, source, paths) {
  return paths.map((path) => check(`${prefix}.${path}`, valueAt(source, path) === true, `${path} must be true`));
}
