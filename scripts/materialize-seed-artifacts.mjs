import { statSync } from "node:fs";
import {
  acceptance,
  absolute,
  copy,
  evidence,
  readJSON,
  readText,
  writeJSON,
  writeText,
} from "./seed-artifacts-lib.mjs";
import { criterionContractPaths, evaluateAllCriteriaAtRoot } from "./seed-criterion-contracts.mjs";
import {
  assertSeedEvidenceSourceMap,
  bindBlockerEvidence,
  bindObservationEvidence,
  projectCompatibilityLocalFacts,
} from "./seed-criterion-source-map.mjs";

const checkSourceMapIndex = process.argv.indexOf("--check-source-map");
const sourceMapPath = checkSourceMapIndex >= 0
  ? process.argv[checkSourceMapIndex + 1] ?? "provenance/seed-evidence-sources.json"
  : "provenance/seed-evidence-sources.json";
const evidenceSourcesConfig = readJSON(sourceMapPath);
const sources = assertSeedEvidenceSourceMap(evidenceSourcesConfig);
if (checkSourceMapIndex >= 0) {
  console.log(`Seed evidence source map is valid: ${sourceMapPath}`);
  process.exit(0);
}

copy("provenance/upstream-lock.json", "artifacts/provenance/upstream-lock.json");
copy("provenance/sbom.spdx.json", "artifacts/provenance/sbom.spdx.json");
copy("Resources/Legal/THIRD_PARTY_NOTICES.md", "artifacts/provenance/THIRD_PARTY_NOTICES.md");
copy("provenance/genoffice-docs-port.json", "artifacts/provenance/genoffice-docs-port.json");
copy("Resources/GenOffice/runtime-manifest.json", "artifacts/provenance/genoffice-runtime-manifest.json");
copy("GenOfficeFork/runtime-input-lock.json", "artifacts/provenance/genoffice-runtime-input-lock.json");
writeJSON("artifacts/provenance/foundation-runtime.json", {
  ...readJSON(sources["AC-01"].foundationRuntimeReceipt),
  sourceEvidence: [
    evidence(sources["AC-01"].foundationRuntimeReceipt),
    evidence(sources["AC-01"].appBinary),
    evidence(sources["AC-01"].rhwpBinary),
    evidence("Resources/Studio/index.html"),
    evidence("Resources/Studio/styles.css"),
    evidence("Resources/Studio/app.js"),
    evidence("provenance/genoffice-docs-port.json"),
    evidence("Resources/GenOffice/runtime-manifest.json"),
    evidence("GenOfficeFork/runtime-input-lock.json"),
  ],
});

const projectSample = readJSON(sources["AC-02"].projectSample);
writeJSON("artifacts/document-model/schema.json", {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://muni.local/public-document-project.schema.json",
  title: "Public Document Studio project",
  type: "object",
  required: [
    "schemaVersion", "documentID", "title", "locale", "currentRevisionID", "elements",
    "assets", "styles", "templateBinding", "evidenceLinks", "revisions", "history",
    "aiProposalHistory", "providerConfigurations", "consentGrants", "redoRevisionIDs",
  ],
  properties: {
    schemaVersion: { const: projectSample.schemaVersion },
    documentID: { type: "string", minLength: 1 },
    title: { type: "string" },
    locale: { type: "string" },
    currentRevisionID: { type: "string", minLength: 1 },
    elements: { type: "array", items: { type: "object", required: ["elementID", "kind", "order", "text"] } },
    assets: { type: "array" }, styles: { type: "array" }, templateBinding: { type: "object" },
    evidenceLinks: { type: "array" }, revisions: { type: "array" }, history: { type: "array" },
    aiProposalHistory: { type: "array" }, providerConfigurations: { type: "array" },
    consentGrants: { type: "array" }, redoRevisionIDs: { type: "array" },
  },
  additionalProperties: false,
  observedExample: evidence(sources["AC-02"].projectSample),
});
writeJSON("artifacts/document-model/recovery-matrix.json", {
  schemaVersion: 1,
  projectStore: readJSON(sources["AC-02"].projectStoreReceipt),
  migration: readJSON(sources["AC-02"].migrationReceipt),
  windowLifecycle: readJSON(sources["AC-02"].windowLifecycleReceipt),
  sourceEvidence: [
    evidence(sources["AC-02"].projectStoreReceipt), evidence(sources["AC-02"].migrationReceipt),
    evidence(sources["AC-02"].windowLifecycleReceipt), evidence(sources["AC-02"].projectSample),
  ],
});

writeJSON("artifacts/templates/catalog-manifest.json", {
  schemaVersion: 1,
  envelope: readJSON("Resources/Templates/catalog-envelope.json"),
  sourceEvidence: [evidence("Resources/Templates/catalog-envelope.json")],
});
writeJSON("artifacts/templates/update-rollback-evidence.json", {
  schemaVersion: 1,
  result: readJSON(sources["AC-03"].templateCatalogReceipt),
  sourceEvidence: [evidence(sources["AC-03"].templateCatalogReceipt)],
});

const ai = readJSON(sources["AC-04"].aiGovernanceReceipt);
writeJSON("artifacts/privacy/provider-boundary-evidence.json", {
  ...ai,
  schemaVersion: 1,
  sourceEvidence: [evidence(sources["AC-04"].aiGovernanceReceipt)],
});
writeJSON("artifacts/ai/proposal-lifecycle-evidence.json", {
  ...ai,
  schemaVersion: 1,
  sourceEvidence: [evidence(sources["AC-04"].aiGovernanceReceipt)],
});

copy("Resources/Capabilities/authoring-capabilities-1.0.0.json", "artifacts/formats/authoring-capability-manifest.json");
copy("Resources/Capabilities/format-capabilities-1.0.0.json", "artifacts/formats/format-capability-matrix.json");
const hwpFamilyReceipt = readJSON(sources["AC-05"].hwpFamilyReceipt);
const nestedReceipt = readJSON(sources["AC-05"].nestedReceipt);
const capabilityScenarioReceipts = sources["AC-05"].scenarioReceipts.map(readJSON);
const lossReports = [
  ...hwpFamilyReceipt.lossReports,
  ...nestedReceipt.lossReports,
  ...capabilityScenarioReceipts.flatMap((receipt) => receipt.lossReports ?? []),
];
writeText("artifacts/formats/loss-reports.jsonl", lossReports.map((entry) => JSON.stringify(entry)).join("\n"));
writeJSON("artifacts/formats/export-validation-evidence.json", {
  schemaVersion: 1,
  receipts: [hwpFamilyReceipt, nestedReceipt, ...capabilityScenarioReceipts],
  sourceEvidence: [evidence(sources["AC-05"].hwpFamilyReceipt), evidence(sources["AC-05"].nestedReceipt), ...sources["AC-05"].scenarioReceipts.map(evidence)],
});

const batchScenarioPaths = sources["AC-06"].scenarioManifests;
writeJSON("artifacts/export/batch-lifecycle-evidence.json", {
  schemaVersion: 1,
  scenarios: batchScenarioPaths.map((path) => ({ result: readJSON(path), evidence: evidence(path) })),
  recovery: readJSON(sources["AC-06"].recoveryReceipt),
  recoveryEvidence: evidence(sources["AC-06"].recoveryReceipt),
});
copy(sources["AC-06"].finalManifest, "artifacts/export/batch-result-manifest.json");

copy("Resources/Compatibility/compatibility-corpus-1.0.0.json", "artifacts/compatibility/corpus-manifest.json");
const observationSubmission = readJSON(sources["AC-07"].clientObservations);
const observationRoot = sources["AC-07"].observationRoot;
const clientObservations = observationSubmission.clientObservations.map((entry) => bindObservationEvidence(entry, observationRoot));
writeText(
  "artifacts/compatibility/observations.jsonl",
  clientObservations.map((entry) => JSON.stringify(entry)).join("\n"),
);
const compatibility = projectCompatibilityLocalFacts(readJSON(sources["AC-07"].compatibilityReceipt));
const observedCompatibility = projectCompatibilityLocalFacts(readJSON(sources["AC-07"].observedReceipt));
if (JSON.stringify(compatibility) !== JSON.stringify(observedCompatibility)) {
  throw new Error("AC-07 observed receipt local facts drift from the compatibility receipt.");
}
writeJSON("artifacts/compatibility/verdict-summary.json", {
  ...compatibility,
  artifacts: (compatibility.artifacts ?? []).map((artifact) => ({
    ...artifact,
    artifactEvidence: evidence(`${sources["AC-07"].artifactRoot}/${artifact.relativePath}`),
  })),
  visualObservations: observationSubmission.visualObservations.map((entry) => bindObservationEvidence(entry, observationRoot)),
  externalBlockers: observationSubmission.externalBlockers.map((entry) => bindBlockerEvidence(entry, observationRoot)),
  sourceEvidence: [
    evidence(sources["AC-07"].compatibilityReceipt),
    evidence(sources["AC-07"].observedReceipt),
    evidence(sources["AC-07"].clientObservations),
    evidence(sources["AC-07"].externalEvidenceIndex),
  ],
});

copy(sources["AC-08"].axeResults, "artifacts/accessibility/automated-results.json");
writeJSON("artifacts/accessibility/manual-scenarios.json", {
  schemaVersion: 1,
  verificationReceipt: readJSON(sources["AC-08"].verificationReceipt),
  browserReceipt: readJSON(sources["AC-08"].browserReceipt),
  voiceOver: readJSON(sources["AC-08"].voiceOverReceipt),
  keyboard: readJSON(sources["AC-08"].keyboardReceipt),
  sourceEvidence: [
    evidence(sources["AC-08"].verificationReceipt), evidence(sources["AC-08"].browserReceipt),
    evidence(sources["AC-08"].voiceOverReceipt), evidence(sources["AC-08"].keyboardReceipt), evidence(sources["AC-08"].axeResults),
  ],
});
writeJSON("artifacts/ui/reference-comparison.json", {
  schemaVersion: 1,
  comparisons: [readJSON(sources["AC-08"].diff1280), readJSON(sources["AC-08"].diff920)],
  pinnedReference: readJSON(sources["AC-08"].pinnedReferenceReceipt),
  referenceSource: readJSON(sources["AC-08"].pinnedReferenceSourceReceipt),
  independentReviews: sources["AC-08"].visualReviews.map(evidence),
  sourceEvidence: [evidence(sources["AC-08"].diff1280), evidence(sources["AC-08"].diff920), evidence(sources["AC-08"].pinnedReferenceReceipt), evidence(sources["AC-08"].pinnedReferenceSourceReceipt)],
});

const performance = readJSON(sources["AC-09"].performanceReceipt);
const performanceProfilePath = "Resources/Performance/performance-profile-1.0.0.json";
writeJSON("artifacts/performance/environment.json", {
  schemaVersion: 1,
  profileVersion: performance.profileVersion,
  profileHash: performance.profileHash,
  profile: readJSON(performanceProfilePath),
  profileEvidence: evidence(performanceProfilePath),
  environment: performance.environment,
  fixtures: performance.fixtures,
  sourceEvidence: [evidence(sources["AC-09"].performanceReceipt)],
});
writeJSON("artifacts/performance/results.json", {
  schemaVersion: 1,
  exportObservations: performance.exportObservations.map((observation) => ({
    ...observation,
    artifactEvidence: evidence(`${sources["AC-09"].artifactRoot}/${observation.artifactRelativePath}`),
  })),
  interactionObservation: performance.interactionObservation,
  executionIdentity: performance.executionIdentity,
  uiObservation: performance.uiObservation,
  sourceEvidence: [evidence(sources["AC-09"].performanceReceipt)],
});

const release = readJSON(sources["AC-10"].releaseManifest);
const archiveVerification = readJSON(sources["AC-10"].archiveVerification);
const archiveEvidence = evidence(sources["AC-10"].archive);
writeJSON("artifacts/release/local-functional-candidate.json", {
  schemaVersion: 1,
  product: release.product,
  version: release.version,
  releaseManifest: evidence(sources["AC-10"].releaseManifest),
  archiveVerification,
  archive: {
    path: sources["AC-10"].archive,
    sha256: archiveEvidence.sha256,
    byteCount: statSync(absolute(sources["AC-10"].archive)).size,
    evidence: archiveEvidence,
  },
  sourceEvidence: [evidence(sources["AC-10"].archiveVerification)],
});
writeJSON("artifacts/release/evidence-index.json", {
  schemaVersion: 1,
  sha256Inventory: readText(sources["AC-10"].sha256Inventory).trim().split(/\r?\n/u).filter(Boolean),
  inventoryEvidence: evidence(sources["AC-10"].sha256Inventory),
  sourceEvidence: [evidence(sources["AC-10"].archiveVerification), archiveEvidence],
});

const criterionSources = {
  "AC-01": ["docs/ac-01-foundation-evidence.md", sourceMapPath, "provenance/upstream-lock.json", "provenance/sbom.spdx.json", "provenance/genoffice-docs-port.json", "Resources/GenOffice/runtime-manifest.json", "GenOfficeFork/runtime-input-lock.json", sources["AC-01"].foundationRuntimeReceipt, sources["AC-01"].appBinary, sources["AC-01"].rhwpBinary],
  "AC-02": ["docs/ac-02-project-lifecycle-evidence.md", sourceMapPath, sources["AC-02"].projectSample, sources["AC-02"].projectStoreReceipt, sources["AC-02"].migrationReceipt, sources["AC-02"].windowLifecycleReceipt],
  "AC-03": ["docs/ac-03-guided-template-evidence.md", sourceMapPath, sources["AC-03"].templateCatalogReceipt],
  "AC-04": ["docs/ac-04-ai-governance-evidence.md", sourceMapPath, sources["AC-04"].aiGovernanceReceipt],
  "AC-05": ["docs/ac-05-format-export-evidence.md", sourceMapPath, sources["AC-05"].hwpFamilyReceipt, sources["AC-05"].nestedReceipt, ...sources["AC-05"].scenarioReceipts],
  "AC-06": ["docs/ac-06-batch-export-evidence.md", sourceMapPath, ...sources["AC-06"].scenarioManifests, sources["AC-06"].finalManifest, sources["AC-06"].recoveryReceipt],
  "AC-07": ["docs/ac-07-compatibility-evidence.md", sourceMapPath, sources["AC-07"].compatibilityReceipt, sources["AC-07"].observedReceipt, sources["AC-07"].clientObservations, sources["AC-07"].externalEvidenceIndex],
  "AC-08": ["docs/ac-08-accessibility-evidence.md", sourceMapPath, sources["AC-08"].verificationReceipt, sources["AC-08"].browserReceipt, sources["AC-08"].voiceOverReceipt, sources["AC-08"].keyboardReceipt, sources["AC-08"].pinnedReferenceReceipt, sources["AC-08"].pinnedReferenceSourceReceipt, sources["AC-08"].axeResults, sources["AC-08"].diff1280, sources["AC-08"].diff920, ...sources["AC-08"].visualReviews],
  "AC-09": ["docs/ac-09-performance-evidence.md", sourceMapPath, sources["AC-09"].performanceReceipt, performanceProfilePath],
  "AC-10": ["docs/ac-10-functional-release-evidence.md", sourceMapPath, sources["AC-10"].releaseManifest, sources["AC-10"].archiveVerification, sources["AC-10"].archive, sources["AC-10"].sha256Inventory],
};
const evaluations = evaluateAllCriteriaAtRoot();
for (const evaluation of evaluations) {
  const projected = acceptance({
    criterion: evaluation.criterion,
    verdict: evaluation.verdict,
    summary: evaluation.summary,
    blockers: evaluation.blockers,
    sources: criterionSources[evaluation.criterion],
    contracts: criterionContractPaths[evaluation.criterion],
  });
  writeJSON(`artifacts/acceptance/${evaluation.criterion}.json`, { ...projected, evaluation });
}

console.log(`Materialized ${Object.values(criterionContractPaths).flat().length + evaluations.length} Seed artifacts from ${sourceMapPath}.`);
