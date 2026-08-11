import {
  check,
  criterionContractPaths,
  formats,
  identityCheck,
  requiredClientOperations,
  result,
} from "./seed-criterion-contract-core.mjs";

const operationOwners = {
  "hancom-official-reopen": "hancom-official",
  "polaris-office-reopen": "polaris-office",
  "genoffice-docs-reopen": "genoffice-docs",
  "microsoft-word-reopen": "microsoft-word",
  "approved-rendering": "public-document-rendering-authority",
  "commonmark-validate": "commonmark-validator",
};
const blockerCodes = ["console-locked", "required-client-unavailable", "authority-approval-pending", "client-state-conflict", "client-automation-timeout"];
const environmentFields = ["clientName", "clientVersion", "clientBuild", "osVersion", "osBuild", "timestamp"];
const pairKey = (value) => `${value.fixtureID}/${value.format}`;
const clientKey = (value) => `${pairKey(value)}/${value.operation}`;

function recordValid(record, reader) {
  if (typeof record?.path !== "string" || typeof record.sha256 !== "string") return false;
  try {
    return `sha256:${reader.sha256(record.path)}` === record.sha256;
  } catch {
    return false;
  }
}

function observationEvidenceState(observation, reader) {
  const record = observation.evidence ?? (
    typeof observation.evidencePath === "string" && typeof observation.evidenceHash === "string"
      ? { path: observation.evidencePath, sha256: observation.evidenceHash }
      : undefined
  );
  if (record === undefined) return "blocked";
  if (observation.evidenceHash !== undefined && observation.evidenceHash !== record.sha256) return "fail";
  return recordValid(record, reader) ? "pass" : "fail";
}

function environmentComplete(observation, requiredFonts) {
  return environmentFields.every((field) => typeof observation[field] === "string" && observation[field].length > 0)
    && Array.isArray(observation.fonts) && observation.fonts.length > 0
    && requiredFonts.every((font) => observation.fonts.includes(font));
}

function boundArtifact(observation, artifacts) {
  const candidates = observation.fixtureID === undefined
    ? [...artifacts.values()].filter((artifact) => artifact.format === observation.format)
    : [artifacts.get(pairKey(observation))];
  const matches = candidates.filter((artifact) => artifact !== undefined
    && artifact.fixtureHash === observation.fixtureHash
    && artifact.artifactHash === observation.artifactHash);
  return matches.length === 1 ? matches[0] : undefined;
}

function visualState(observation, artifacts, corpus, reader) {
  const artifact = boundArtifact(observation, artifacts);
  if (artifact === undefined) return "fail";
  const evidenceState = observationEvidenceState(observation, reader);
  if (evidenceState === "fail") return "fail";
  const tolerance = corpus.visualTolerances ?? {};
  const complete = environmentComplete(observation, corpus.requiredFonts ?? [])
    && typeof observation.toolID === "string" && observation.toolID.length > 0
    && Number.isInteger(observation.expectedPageCount)
    && Number.isInteger(observation.observedPageCount)
    && Array.isArray(observation.missingAuthoredElementIDs)
    && Array.isArray(observation.unexpectedBlankPageNumbers)
    && typeof observation.textBoundsCoverage === "number"
    && evidenceState === "pass";
  if (!complete) return "blocked";
  const failed = observation.expectedPageCount <= 0
    || observation.observedPageCount <= 0
    || Math.abs(observation.observedPageCount - observation.expectedPageCount) > tolerance.pageCountDelta
    || observation.missingAuthoredElementIDs.length > tolerance.missingTextElements
    || observation.unexpectedBlankPageNumbers.length > tolerance.unexpectedBlankPages
    || !Number.isFinite(observation.textBoundsCoverage)
    || observation.textBoundsCoverage < 0 || observation.textBoundsCoverage > 1
    || observation.textBoundsCoverage < tolerance.minimumTextBoundsCoverage;
  return failed ? "fail" : "pass";
}

function clientState(observation, artifacts, corpus, reader) {
  const artifact = boundArtifact(observation, artifacts);
  if (artifact === undefined || operationOwners[observation.operation] !== observation.clientID
    || !requiredClientOperations[observation.format]?.includes(observation.operation)) return "fail";
  const evidenceState = observationEvidenceState(observation, reader);
  if (evidenceState === "fail") return "fail";
  const complete = environmentComplete(observation, corpus.requiredFonts ?? [])
    && typeof observation.opened === "boolean"
    && Number.isInteger(observation.extensionWarningCount)
    && Number.isInteger(observation.expectedTextCount)
    && Number.isInteger(observation.observedTextCount)
    && Number.isInteger(observation.expectedPageCount)
    && Number.isInteger(observation.observedPageCount)
    && Number.isInteger(observation.unexpectedBlankPageCount)
    && evidenceState === "pass";
  if (!complete) return "blocked";
  const expectedElements = artifact.validation.orderedElements.length;
  const failed = observation.opened === false
    || observation.extensionWarningCount !== 0
    || observation.expectedTextCount !== expectedElements
    || observation.observedTextCount !== observation.expectedTextCount
    || observation.expectedPageCount <= 0 || observation.observedPageCount <= 0
    || Math.abs(observation.observedPageCount - observation.expectedPageCount) > corpus.visualTolerances.pageCountDelta
    || observation.unexpectedBlankPageCount > corpus.visualTolerances.unexpectedBlankPages;
  return failed ? "fail" : "pass";
}

function blockerClass(blocker) {
  const derived = blocker.operation === "visual-inspection"
    ? "visual"
    : requiredClientOperations[blocker.format]?.includes(blocker.operation) === true ? "client" : undefined;
  return blocker.verdictClass === undefined || blocker.verdictClass === derived ? derived : undefined;
}

function blockerValid(blocker, artifacts, reader) {
  const artifact = boundArtifact(blocker, artifacts);
  const classification = blockerClass(blocker);
  if (artifact === undefined || blocker.status !== "BLOCKED" || !blockerCodes.includes(blocker.code)
    || (blocker.blockerID !== undefined && (typeof blocker.blockerID !== "string" || blocker.blockerID.length === 0))
    || typeof blocker.observedAt !== "string" || blocker.observedAt.length === 0
    || typeof blocker.detail !== "string" || blocker.detail.length === 0
    || !Array.isArray(blocker.evidence) || blocker.evidence.length === 0
    || !blocker.evidence.every((record) => recordValid(record, reader))) return false;
  return classification !== undefined;
}

const blockerPair = (blocker, artifacts) => {
  const artifact = boundArtifact(blocker, artifacts);
  return artifact === undefined ? "" : pairKey(artifact);
};
const blockerClient = (blocker, artifacts) => `${blockerPair(blocker, artifacts)}/${blocker.operation}`;

function artifactValid(artifact, reader) {
  const validation = artifact.validation ?? {};
  const elements = validation.orderedElements ?? [];
  const elementIDs = elements.map((entry) => entry.elementID);
  const orders = elements.map((entry) => entry.order);
  return artifact.byteCount > 0
    && artifact.artifactHash === artifact.artifactEvidence?.sha256
    && artifact.byteCount === reader.size(artifact.artifactEvidence?.path)
    && validation.structuralValid === true && validation.semanticValid === true
    && validation.evidenceSource === "artifact-derived"
    && typeof validation.validator === "string" && validation.validator.length > 0
    && elements.length > 0
    && elements.every((entry) => typeof entry.elementID === "string" && typeof entry.kind === "string" && Number.isInteger(entry.order) && typeof entry.textHash === "string")
    && new Set(elementIDs).size === elements.length && new Set(orders).size === elements.length;
}

export function evaluateAc07(snapshot, reader) {
  const corpus = snapshot[criterionContractPaths["AC-07"][0]];
  const clientObservations = snapshot[criterionContractPaths["AC-07"][1]];
  const summary = snapshot[criterionContractPaths["AC-07"][2]];
  const fixtures = new Map((corpus.fixtures ?? []).map((fixture) => [fixture.id, fixture]));
  const dispositions = summary.dispositions ?? [];
  const artifacts = summary.artifacts ?? [];
  const artifactMap = new Map(artifacts.map((artifact) => [pairKey(artifact), artifact]));
  const expectedPairs = [...fixtures.values()].flatMap((fixture) => formats.map((format) => `${fixture.id}/${format}`));
  const dispositionPairs = new Set(dispositions.map(pairKey));
  const validatedPairs = new Set(dispositions.filter((entry) => entry.disposition === "artifact-validated").map(pairKey));
  const artifactPairs = new Set(artifacts.map(pairKey));
  const visualObservations = summary.visualObservations ?? [];
  const blockers = summary.externalBlockers ?? [];
  const visualStates = visualObservations.map((entry) => [entry, visualState(entry, artifactMap, corpus, reader)]);
  const clientStates = clientObservations.map((entry) => [entry, clientState(entry, artifactMap, corpus, reader)]);
  const visualPassed = new Set(visualStates.filter(([, state]) => state === "pass").map(([entry]) => pairKey(entry)));
  const clientPassed = new Set(clientStates.filter(([, state]) => state === "pass").map(([entry]) => clientKey(entry)));
  const requiredVisual = [...artifactPairs];
  const requiredClient = artifacts.flatMap((artifact) => requiredClientOperations[artifact.format].map((operation) => `${pairKey(artifact)}/${operation}`));
  const validBlockers = blockers.filter((entry) => blockerValid(entry, artifactMap, reader));
  const missingVisual = requiredVisual.filter((key) => !visualPassed.has(key));
  const missingClient = requiredClient.filter((key) => !clientPassed.has(key));
  const visualBlocked = new Set(validBlockers.filter((entry) => blockerClass(entry) === "visual").map((entry) => blockerPair(entry, artifactMap)));
  const clientBlocked = new Set(validBlockers.filter((entry) => blockerClass(entry) === "client").map((entry) => blockerClient(entry, artifactMap)));
  const checks = [
    check("compatibility.corpus", corpus.status === "frozen" && fixtures.has("basic-client-interoperability") && fixtures.has("authoring-universe") && [...fixtures.values()].every((fixture) => formats.every((format) => fixture.formats?.includes(format))) && (corpus.requiredFonts ?? []).length > 0, "frozen two-fixture four-format corpus"),
    check("compatibility.dispositions", expectedPairs.length === dispositionPairs.size && expectedPairs.every((pair) => dispositionPairs.has(pair)) && dispositions.every((entry) => entry.fixtureHash === fixtures.get(entry.fixtureID)?.projectHash && (entry.disposition === "artifact-validated" ? entry.capabilityGaps?.length === 0 : entry.disposition === "semantic-loss-blocked" && entry.capabilityGaps?.length > 0)), "every fixture-format pair has an evidence-derived disposition"),
    check("compatibility.artifact-coverage", validatedPairs.size === artifactPairs.size && [...validatedPairs].every((pair) => artifactPairs.has(pair)), "artifact set exactly matches validated dispositions"),
    check("compatibility.artifacts", artifacts.length > 0 && artifacts.every((artifact) => artifactValid(artifact, reader)), "artifacts bind bytes and nested artifact-derived validation facts"),
    check("compatibility.blockers", validBlockers.length === blockers.length, "all external blockers are evidence-bound structured records"),
    check("compatibility.visual-failures", !visualStates.some(([, state]) => state === "fail"), "no raw visual assertion failed"),
    check("compatibility.visual-coverage", missingVisual.every((key) => visualBlocked.has(key)), "missing raw visual observations have exact structured blockers"),
    check("compatibility.client-failures", !clientStates.some(([, state]) => state === "fail"), "no raw client assertion failed"),
    check("compatibility.client-coverage", missingClient.every((key) => clientBlocked.has(key)), "missing raw client observations have exact structured blockers"),
    identityCheck(snapshot, reader, 5),
  ];
  const activeBlockers = validBlockers.filter((entry) => blockerClass(entry) === "visual" ? missingVisual.includes(blockerPair(entry, artifactMap)) : missingClient.includes(blockerClient(entry, artifactMap)));
  return result("AC-07", checks, [...new Set(activeBlockers.map((entry) => entry.detail))], "Frozen-corpus structural, semantic, visual, and client checks passed.");
}
