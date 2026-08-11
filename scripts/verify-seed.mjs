import { evidence, normalizeCriterion, readJSON, sha256 } from "./seed-artifacts-lib.mjs";
import {
  APPROVED_SEED_SHA256,
  compareAcceptanceProjection,
  criterionContractPaths,
  evaluateCriterionAtRoot,
} from "./seed-criterion-contracts.mjs";

function fail(message, exitCode = 1) {
  console.error(message);
  process.exitCode = exitCode;
}

let criterion;
try {
  criterion = normalizeCriterion(process.argv[2]);
} catch (error) {
  fail(error.message);
  process.exit();
}

const acceptancePath = `artifacts/acceptance/${criterion}.json`;
let receipt;
try {
  receipt = readJSON(acceptancePath);
} catch (error) {
  const detail = error instanceof Error ? error.message : String(error);
  fail(`${criterion} FAIL: run npm run materialize:seed first (${detail}).`);
  process.exit();
}
const errors = [];
if (receipt.schemaVersion !== 1) errors.push("unsupported acceptance schema");
if (receipt.criterion !== criterion) errors.push(`criterion mismatch: ${receipt.criterion}`);
const approvedSeed = evidence(".ouroboros/seeds/seed_219732b73d5d.yaml");
if (approvedSeed.sha256 !== `sha256:${APPROVED_SEED_SHA256}` || receipt.seed?.sha256 !== approvedSeed.sha256) {
  errors.push("approved Seed hash changed");
}

for (const record of [...(receipt.sourceEvidence ?? []), ...(receipt.contracts ?? [])]) {
  if (!record?.path || !record?.sha256) {
    errors.push("malformed evidence record");
    continue;
  }
  try {
    const actual = `sha256:${sha256(record.path)}`;
    if (actual !== record.sha256) errors.push(`hash drift: ${record.path}`);
  } catch {
    errors.push(`missing evidence: ${record.path}`);
  }
}

const expectedContractPaths = criterionContractPaths[criterion];
const storedContractPaths = (receipt.contracts ?? []).map((record) => record.path);
if (new Set(storedContractPaths).size !== storedContractPaths.length || JSON.stringify(storedContractPaths) !== JSON.stringify(expectedContractPaths)) {
  errors.push("acceptance contract set differs from the approved criterion contract");
}

const evaluation = evaluateCriterionAtRoot(criterion);
if (receipt.evaluation === undefined) errors.push("missing recomputed evaluation projection");
errors.push(...compareAcceptanceProjection(receipt, evaluation));

if (errors.length > 0) {
  fail(`${criterion} FAIL\n- ${errors.join("\n- ")}`);
} else if (evaluation.verdict === "blocked") {
  fail(`${criterion} BLOCKED\n- ${evaluation.blockers.join("\n- ")}`, 2);
} else if (evaluation.verdict === "fail") {
  const failedChecks = evaluation.checks.filter((entry) => !entry.passed).map((entry) => `${entry.id}: ${entry.detail}`);
  fail(`${criterion} FAIL\n- ${failedChecks.join("\n- ")}`);
} else {
  console.log(`${criterion} PASS`);
}
