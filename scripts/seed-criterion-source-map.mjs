import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import { confinedPath, evidence, projectRoot } from "./seed-artifacts-lib.mjs";

const requirements = {
  "AC-01": { files: ["foundationRuntimeReceipt", "appBinary", "rhwpBinary"] },
  "AC-02": { files: ["projectSample", "projectStoreReceipt", "migrationReceipt", "windowLifecycleReceipt"] },
  "AC-03": { files: ["templateCatalogReceipt"] },
  "AC-04": { files: ["aiGovernanceReceipt"] },
  "AC-05": { files: ["hwpFamilyReceipt", "nestedReceipt"], lists: { scenarioReceipts: 2 } },
  "AC-06": { files: ["finalManifest", "recoveryReceipt"], directories: ["recoveryArtifactRoot"], lists: { scenarioManifests: 8 } },
  "AC-07": { files: ["clientObservations", "compatibilityReceipt", "externalEvidenceIndex", "observedReceipt"], directories: ["artifactRoot", "observationRoot"] },
  "AC-08": { files: ["axeResults", "browserReceipt", "diff1280", "diff920", "verificationReceipt", "voiceOverReceipt", "keyboardReceipt", "pinnedReferenceReceipt", "pinnedReferenceSourceReceipt"], lists: { visualReviews: 2 } },
  "AC-09": { files: ["performanceReceipt"], directories: ["artifactRoot", "packagedApp"] },
  "AC-10": { files: ["archive", "archiveVerification", "releaseManifest", "sha256Inventory"] },
};

function issue(field, detail) {
  return { field, detail };
}

const valueAt = (source, path) => path.split(".").reduce((value, key) => value?.[key], source);
const missingFields = (source, fields) => fields.filter((field) => valueAt(source, field) === undefined);

function validatePath(root, field, value, kind) {
  if (typeof value !== "string" || value.length === 0) return [issue(field, "must be a non-empty project-relative path")];
  try {
    const target = confinedPath(root, value);
    const stats = statSync(target);
    if (kind === "file" && !stats.isFile()) return [issue(field, "must resolve to a regular file")];
    if (kind === "directory" && !stats.isDirectory()) return [issue(field, "must resolve to a directory")];
    return [];
  } catch (error) {
    return [issue(field, error instanceof Error ? error.message : String(error))];
  }
}

function readJSON(root, relativePath) {
  return JSON.parse(readFileSync(confinedPath(root, relativePath), "utf8"));
}

const shaAt = (root, relativePath) => `sha256:${createHash("sha256").update(readFileSync(confinedPath(root, relativePath))).digest("hex")}`;

function validateReceiptShapes(criteria, root) {
  const issues = [];
  try {
    const runtime = readJSON(root, criteria["AC-01"].foundationRuntimeReceipt);
    if (runtime.architecture !== "arm64" || runtime.codesignVerification !== "pass" || typeof runtime.rhwpBinaryHash !== "string") {
      issues.push(issue("AC-01.foundationRuntimeReceipt", "must contain arm64, passing codesign, and rhwp binary identity facts"));
    }
    const genoffice = readJSON(root, "Resources/GenOffice/runtime-manifest.json");
    const inputLock = readJSON(root, "GenOfficeFork/runtime-input-lock.json");
    if (!Array.isArray(genoffice.inputs) || !Array.isArray(genoffice.outputs) || genoffice.runtime?.offline !== true
      || genoffice.inputLock?.sourcePath !== "GenOfficeFork/runtime-input-lock.json"
      || genoffice.inputLock?.packagedPath !== "Provenance/genoffice-runtime-input-lock.json"
      || inputLock.upstreamCommit !== genoffice.upstream?.commit
      || JSON.stringify(inputLock.buildTool) !== JSON.stringify(genoffice.buildTool)
      || JSON.stringify(inputLock.inputs) !== JSON.stringify(genoffice.inputs)
      || JSON.stringify(inputLock.packages) !== JSON.stringify(genoffice.packages)) {
      issues.push(issue("AC-01.runtimeManifest", "must exactly bind the project-contained runtime input and package lock"));
    }
    for (const output of genoffice.outputs ?? []) issues.push(...validatePath(root, `AC-01.runtimeOutput/${output.path}`, join("Resources", output.path), "file"));
    issues.push(...validatePath(root, "AC-01.runtimeNode", join("Resources", genoffice.node?.sourcePath ?? ""), "file"));
  } catch (error) {
    issues.push(issue("AC-01", error instanceof Error ? error.message : String(error)));
  }
  try {
    for (const field of ["projectSample", "projectStoreReceipt", "migrationReceipt", "windowLifecycleReceipt"]) readJSON(root, criteria["AC-02"][field]);
  } catch (error) {
    issues.push(issue("AC-02", error instanceof Error ? error.message : String(error)));
  }
  try {
    const receipt = readJSON(root, criteria["AC-03"].templateCatalogReceipt);
    const missing = missingFields(receipt, ["exportSnapshotUsedRuleRevision", "immutableRevisionCreated", "lowerPrecedenceCouldNotOverride", "officialRuleHistoryRecorded", "officialRuleTitleElementEnforced", "repeatedEnforcementWasIdempotent", "unsupportedOfficialFieldRejected", "highestAppliedPrecedence", "authoritativeTitle", "exportBoundProjectTitle"]);
    if (missing.length > 0) issues.push(issue("AC-03.templateCatalogReceipt", `missing fields: ${missing.join(", ")}`));
  } catch (error) {
    issues.push(issue("AC-03", error instanceof Error ? error.message : String(error)));
  }
  try {
    const receipt = readJSON(root, criteria["AC-04"].aiGovernanceReceipt);
    const missing = missingFields(receipt, ["brandedEndpointAllowlistEnforced", "endpointValidationPrecedesPersistence", "consentRebindingRequired", "actualScopedTargetIDsEnforced", "operationSpecificCommands.missingDataMarking", "operationSpecificCommands.evidenceClaimCheck", "operationSpecificCommands.tableCellUpdate", "exactTablePathFailClosed", "tableCellOnlyMutation", "fullDiffPersisted"]);
    if (missing.length > 0) issues.push(issue("AC-04.aiGovernanceReceipt", `missing fields: ${missing.join(", ")}`));
  } catch (error) {
    issues.push(issue("AC-04", error instanceof Error ? error.message : String(error)));
  }
  try {
    for (const field of ["hwpFamilyReceipt", "nestedReceipt", ...criteria["AC-05"].scenarioReceipts.map((_, index) => `scenarioReceipts.${index}`)]) {
      const path = field.startsWith("scenarioReceipts.") ? criteria["AC-05"].scenarioReceipts[Number(field.split(".")[1])] : criteria["AC-05"][field];
      const receipt = readJSON(root, path);
      if (!Array.isArray(receipt.lossReports) || !Array.isArray(receipt.results)) {
        issues.push(issue(`AC-05.${field}`, "must contain lossReports and results arrays"));
      } else if (receipt.results.some((entry) => entry.validation?.evidenceSource !== "artifact-derived" || !Array.isArray(entry.validation?.orderedElements))) {
        issues.push(issue(`AC-05.${field}`, "published results must contain nested artifact-derived validation"));
      }
    }
  } catch (error) {
    issues.push(issue("AC-05", error instanceof Error ? error.message : String(error)));
  }
  try {
    for (const relativePath of criteria["AC-06"].scenarioManifests) readJSON(root, relativePath);
    readJSON(root, criteria["AC-06"].finalManifest);
    const recovery = readJSON(root, criteria["AC-06"].recoveryReceipt);
    const reconciled = recovery.reconciledAfterMove;
    const item = reconciled?.items?.[0];
    const expected = item?.publicationIntent?.expectedArtifactHash;
    const artifact = join(criteria["AC-06"].recoveryArtifactRoot, item?.destinationFile ?? "");
    const startup = recovery.startupRecovered ?? [];
    if (reconciled?.operationID !== "batch-ac06-crash-after-move" || reconciled?.state !== "completed" || reconciled?.cleanupState !== "clean"
      || item?.state !== "published" || expected !== item?.artifactHash || shaAt(root, artifact) !== expected
      || recovery.manifestlessOperationExists !== true || recovery.manifestlessManifestExists !== false
      || startup.length !== 1 || startup[0]?.operationID !== "batch-ac06-startup-recoverable") {
      issues.push(issue("AC-06.recoveryReceipt", "must bind post-move hash reconciliation and isolate manifestless startup recovery"));
    }
  } catch (error) {
    issues.push(issue("AC-06", error instanceof Error ? error.message : String(error)));
  }
  try {
    const submission = readJSON(root, criteria["AC-07"].clientObservations);
    if (submission === null || Array.isArray(submission) || !["visualObservations", "clientObservations", "externalBlockers"].every((field) => Array.isArray(submission[field]))) {
      issues.push(issue("AC-07.clientObservations", "must be a raw visual/client/blocker envelope"));
    }
    const observed = readJSON(root, criteria["AC-07"].observedReceipt);
    if (!Array.isArray(observed.artifacts) || observed.artifacts.length === 0 || observed.artifacts.some((artifact) => typeof artifact.relativePath !== "string" || artifact.validation?.evidenceSource !== "artifact-derived" || !Array.isArray(artifact.validation?.orderedElements))) {
      issues.push(issue("AC-07.observedReceipt", "artifacts must carry relativePath and nested artifact-derived validation"));
    }
    const compatibility = readJSON(root, criteria["AC-07"].compatibilityReceipt);
    if (JSON.stringify(projectCompatibilityLocalFacts(compatibility)) !== JSON.stringify(projectCompatibilityLocalFacts(observed))) {
      issues.push(issue("AC-07.observedReceipt", "local facts must exactly match the compatibility receipt"));
    }
    for (const artifact of compatibility.artifacts ?? []) {
      issues.push(...validatePath(root, `AC-07.artifactRoot/${artifact.relativePath}`, join(criteria["AC-07"].artifactRoot, artifact.relativePath), "file"));
    }
  } catch (error) {
    issues.push(issue("AC-07", error instanceof Error ? error.message : String(error)));
  }
  try {
    const axe = readJSON(root, criteria["AC-08"].axeResults);
    const verification = readJSON(root, criteria["AC-08"].verificationReceipt);
    const voiceOver = readJSON(root, criteria["AC-08"].voiceOverReceipt);
    if (!Array.isArray(axe) || !Array.isArray(verification.commands) || !Array.isArray(voiceOver.journeys)) {
      issues.push(issue("AC-08", "axe states, verification commands, and VoiceOver journeys must be arrays"));
    }
    readJSON(root, criteria["AC-08"].browserReceipt);
    readJSON(root, criteria["AC-08"].diff1280);
    readJSON(root, criteria["AC-08"].diff920);
    const keyboard = readJSON(root, criteria["AC-08"].keyboardReceipt);
    const reference = readJSON(root, criteria["AC-08"].pinnedReferenceReceipt);
    const referenceSource = readJSON(root, criteria["AC-08"].pinnedReferenceSourceReceipt);
    if (keyboard.journeys?.length !== 7 || keyboard.journeys.some((journey) => journey.status !== "PASS" || journey.criticalActivationInputSource !== "keyboard")
      || keyboard.programmaticStates?.outlineCurrent?.passed !== true || keyboard.programmaticStates?.formatToggles?.onAndOffObserved !== true
      || Object.values(keyboard.focusTransitions ?? {}).some((transition) => transition.activeElementMatched !== true)
      || reference.passed !== true || reference.lineage !== "pinned-genoffice-docs-fidelity-v1"
      || reference.referenceSetHash !== referenceSource.referenceSetHash || referenceSource.upstream?.commit !== "d8305ff2dc152593a1ec5639d77e6860c6a512bd") {
      issues.push(issue("AC-08", "keyboard journeys and pinned GenOffice reference must be exact and passing"));
    }
  } catch (error) {
    issues.push(issue("AC-08", error instanceof Error ? error.message : String(error)));
  }
  try {
    const performance = readJSON(root, criteria["AC-09"].performanceReceipt);
    if (!Array.isArray(performance.exportObservations) || performance.exportObservations.some((entry) => typeof entry.artifactRelativePath !== "string")) {
      issues.push(issue("AC-09.performanceReceipt", "exportObservations must carry artifactRelativePath"));
    }
    for (const observation of performance.exportObservations ?? []) {
      issues.push(...validatePath(root, `AC-09.artifactRoot/${observation.artifactRelativePath}`, join(criteria["AC-09"].artifactRoot, observation.artifactRelativePath), "file"));
    }
    const identity = performance.executionIdentity ?? {};
    for (const [relativePath, expected] of [
      [identity.bundleExecutableRelativePath, identity.executableSHA256],
      [identity.genOfficeRuntimeManifestRelativePath, identity.genOfficeRuntimeManifestSHA256],
      [identity.genOfficeBundleRelativePath, identity.genOfficeBundleSHA256],
      [identity.nodeExecutableRelativePath, identity.nodeExecutableSHA256],
      [identity.rhwpExecutableRelativePath, identity.rhwpExecutableSHA256],
    ]) {
      if (typeof relativePath !== "string" || shaAt(root, join(criteria["AC-09"].packagedApp, relativePath)) !== expected) issues.push(issue("AC-09.executionIdentity", `package identity mismatch: ${String(relativePath)}`));
    }
    if (performance.uiObservation?.status !== "pass" || performance.uiObservation?.observationSurface !== "AppKit" || performance.uiObservation?.windowVisible !== true || performance.uiObservation?.onScreenWindowCount < 1 || performance.uiObservation?.cancelButtonActionInvocations < 1) {
      issues.push(issue("AC-09.uiObservation", "must bind visible AppKit progress and real cancel action"));
    }
  } catch (error) {
    issues.push(issue("AC-09", error instanceof Error ? error.message : String(error)));
  }
  try {
    const release = readJSON(root, criteria["AC-10"].releaseManifest);
    readJSON(root, criteria["AC-10"].archiveVerification);
    if (typeof release.product !== "string" || typeof release.version !== "string") {
      issues.push(issue("AC-10.releaseManifest", "must contain product and version"));
    }
  } catch (error) {
    issues.push(issue("AC-10", error instanceof Error ? error.message : String(error)));
  }
  return issues;
}

export function validateSeedEvidenceSourceMap(sourceMap, root = projectRoot) {
  const issues = [];
  if (sourceMap?.schemaVersion !== 1) issues.push(issue("schemaVersion", "must equal 1"));
  const criteria = sourceMap?.criteria;
  if (criteria === null || typeof criteria !== "object" || Array.isArray(criteria)) {
    return [...issues, issue("criteria", "must be an object containing AC-01 through AC-10")];
  }
  for (const [criterion, contract] of Object.entries(requirements)) {
    const values = criteria[criterion];
    if (values === null || typeof values !== "object" || Array.isArray(values)) {
      issues.push(issue(criterion, "criterion source object is required"));
      continue;
    }
    for (const field of contract.files ?? []) issues.push(...validatePath(root, `${criterion}.${field}`, values[field], "file"));
    for (const field of contract.directories ?? []) issues.push(...validatePath(root, `${criterion}.${field}`, values[field], "directory"));
    for (const [field, expectedCount] of Object.entries(contract.lists ?? {})) {
      const entries = values[field];
      if (!Array.isArray(entries) || entries.length !== expectedCount) {
        issues.push(issue(`${criterion}.${field}`, `must contain exactly ${expectedCount} paths`));
        continue;
      }
      if (new Set(entries).size !== entries.length) issues.push(issue(`${criterion}.${field}`, "paths must be unique"));
      entries.forEach((entry, index) => issues.push(...validatePath(root, `${criterion}.${field}[${index}]`, entry, "file")));
    }
  }
  const extraCriteria = Object.keys(criteria).filter((criterion) => requirements[criterion] === undefined);
  for (const criterion of extraCriteria) issues.push(issue(criterion, "unexpected criterion source object"));
  issues.push(...validateReceiptShapes(criteria, root));
  return issues;
}

export function assertSeedEvidenceSourceMap(sourceMap, root = projectRoot) {
  const issues = validateSeedEvidenceSourceMap(sourceMap, root);
  if (issues.length > 0) throw new Error(`Seed evidence source map failed dry validation:\n${issues.map((entry) => `- ${entry.field}: ${entry.detail}`).join("\n")}`);
  return sourceMap.criteria;
}

function evidencePathAt(observationRoot, relativePath) {
  if (typeof relativePath !== "string" || relativePath.length === 0 || isAbsolute(relativePath) || relativePath.split(/[\\/]/u).includes("..")) {
    throw new Error(`Observation evidence must be relative to its source root: ${String(relativePath)}`);
  }
  return join(observationRoot, relativePath);
}

export function bindObservationEvidence(observation, observationRoot) {
  const bound = evidence(evidencePathAt(observationRoot, observation.evidencePath));
  if (bound.sha256 !== observation.evidenceHash) throw new Error(`Observation evidence hash mismatch: ${observation.evidencePath}`);
  return { ...observation, evidence: bound };
}

export function bindBlockerEvidence(blocker, observationRoot) {
  const records = (blocker.evidence ?? []).map((record) => {
    const bound = evidence(evidencePathAt(observationRoot, record.path));
    if (bound.sha256 !== record.sha256) throw new Error(`Blocker evidence hash mismatch: ${record.path}`);
    return bound;
  });
  return { ...blocker, evidence: records };
}

export function projectCompatibilityLocalFacts(compatibility) {
  return {
    corpusVersion: compatibility.corpusVersion,
    manifestVersion: compatibility.manifestVersion,
    requiredClientOperations: compatibility.requiredClientOperations,
    capabilityGaps: compatibility.capabilityGaps,
    artifacts: compatibility.artifacts,
    dispositions: compatibility.dispositions,
  };
}
