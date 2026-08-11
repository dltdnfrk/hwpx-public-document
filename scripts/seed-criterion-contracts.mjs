import {
  APPROVED_SEED_SHA256,
  check,
  criterionContractPaths,
  loadSnapshot,
  normalizeCriterion,
  projectRoot,
  readerAt,
  result,
} from "./seed-criterion-contract-core.mjs";
import { deriveAc10Outcome, evaluateAc10 } from "./seed-criterion-evaluator-ac10.mjs";
import { evaluatorsAc01ToAc05 } from "./seed-criterion-evaluators-ac01-ac05.mjs";
import { evaluatorsAc06ToAc09 } from "./seed-criterion-evaluators-ac06-ac09.mjs";

export { APPROVED_SEED_SHA256, criterionContractPaths, deriveAc10Outcome };

const evaluators = {
  ...evaluatorsAc01ToAc05,
  ...evaluatorsAc06ToAc09,
};

export function evaluateCriterionAtRoot(rawCriterion, root = projectRoot) {
  const criterion = normalizeCriterion(rawCriterion);
  let reader;
  try {
    reader = readerAt(root);
    if (criterion === "AC-10") {
      const preceding = Array.from({ length: 9 }, (_, index) => evaluateCriterionAtRoot(`AC-${String(index + 1).padStart(2, "0")}`, root));
      return evaluateAc10(loadSnapshot(criterion, reader), reader, preceding);
    }
    return evaluators[criterion](loadSnapshot(criterion, reader), reader);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return result(criterion, [check("contract.load", false, detail)], [], "Criterion contracts loaded and passed.");
  }
}

export function evaluateAllCriteriaAtRoot(root = projectRoot) {
  const preceding = Array.from({ length: 9 }, (_, index) => evaluateCriterionAtRoot(`AC-${String(index + 1).padStart(2, "0")}`, root));
  const reader = readerAt(root);
  return [...preceding, evaluateAc10(loadSnapshot("AC-10", reader), reader, preceding)];
}

export function compareAcceptanceProjection(receipt, evaluation) {
  const errors = [];
  if (receipt.criterion !== evaluation.criterion) errors.push(`criterion mismatch: ${String(receipt.criterion)}`);
  if (receipt.verdict !== evaluation.verdict) errors.push(`verdict mismatch: stored ${String(receipt.verdict)}, recomputed ${evaluation.verdict}`);
  if (receipt.summary !== undefined && receipt.summary !== evaluation.summary) errors.push("summary mismatch");
  if (receipt.blockers !== undefined && JSON.stringify(receipt.blockers) !== JSON.stringify(evaluation.blockers)) errors.push("blocker mismatch");
  if (receipt.evaluation !== undefined && JSON.stringify(receipt.evaluation) !== JSON.stringify(evaluation)) errors.push("evaluation projection mismatch");
  return errors;
}
