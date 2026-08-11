import {
  approvedProviders,
  booleanChecks,
  check,
  criterionContractPaths,
  formats,
  identityCheck,
  result,
} from "./seed-criterion-contract-core.mjs";
import { repositoryGenOfficeRuntimeChecks } from "./seed-genoffice-runtime-contract.mjs";

function evaluateAc01(snapshot, reader) {
  const lock = snapshot[criterionContractPaths["AC-01"][0]];
  const sbom = snapshot[criterionContractPaths["AC-01"][1]];
  const notices = snapshot[criterionContractPaths["AC-01"][2]];
  const port = snapshot[criterionContractPaths["AC-01"][3]];
  const manifest = snapshot[criterionContractPaths["AC-01"][4]];
  const inputLock = snapshot[criterionContractPaths["AC-01"][5]];
  const runtime = snapshot[criterionContractPaths["AC-01"][6]];
  const upstreams = Object.fromEntries((lock.upstreams ?? []).map((entry) => [entry.name, entry]));
  const packages = sbom.packages ?? [];
  const studioText = ["Resources/Studio/index.html", "Resources/Studio/styles.css", "Resources/Studio/app.js"].map((path) => reader.text(path)).join("\n");
  const checks = [
    check("pins.genoffice", upstreams.genoffice?.commit === "d8305ff2dc152593a1ec5639d77e6860c6a512bd", "approved GenOffice commit"),
    check("pins.rhwp", upstreams.rhwp?.commit === "2dced7bfe10c6597cead634264c7c1781c01f1e7", "approved rhwp commit"),
    check("pins.genoffice-runtime", upstreams.genoffice?.integration_mode === "pinned-adapter-runtime-fork" && upstreams.genoffice?.direct_package_runtime_linkage === true && upstreams.genoffice?.upstream_runtime_files_bundled === true && lock.runtime_scope?.integration_mode === "pinned-adapter-runtime-fork" && lock.runtime_scope?.direct_upstream_package_linkage === true && lock.runtime_scope?.bundled_upstream_runtime_files === true, "upstream lock records the pinned bundled GenOffice adapter runtime fork"),
    check("port.mode", port.integrationMode === "pinned-adapter-runtime-fork" && port.upstream?.commit === upstreams.genoffice?.commit && port.portBoundary?.directPackageRuntimeLinkage === true && port.portBoundary?.upstreamRuntimeFilesBundled === true, "pinned adapter runtime fork linkage"),
    check("runtime-manifest.upstream", manifest.schemaVersion === 1 && manifest.upstream?.repository === upstreams.genoffice?.repository && manifest.upstream?.commit === upstreams.genoffice?.commit && manifest.upstream?.license === upstreams.genoffice?.license && upstreams.genoffice?.port_manifest_sha256 === `sha256:${reader.sha256("artifacts/provenance/genoffice-docs-port.json")}`, "runtime manifest and port bind the approved upstream"),
    ...repositoryGenOfficeRuntimeChecks(manifest, inputLock, reader),
    check("sbom.upstreams", packages.some((item) => item.name === "GenOffice Docs" && item.versionInfo === upstreams.genoffice?.commit) && packages.some((item) => item.name === "rhwp" && item.versionInfo === upstreams.rhwp?.commit), "SBOM binds both upstreams"),
    check("sbom.dependencies", packages.length >= 207 && (sbom.relationships ?? []).length >= packages.length, "complete dependency inventory"),
    check("notices.licenses", /GenOffice/u.test(notices) && /rhwp/u.test(notices) && /Apache(?:-2\.0| License 2\.0)/u.test(notices) && /MIT/u.test(notices), "notices include both licenses"),
    check("runtime.arm64", runtime.architecture === "arm64", "arm64 runtime"),
    check("runtime.codesign", runtime.codesignVerification === "pass", "strict local codesign receipt"),
    check("runtime.rhwp", runtime.rhwpBinaryHash === upstreams.rhwp?.local_patchset?.bundled_arm64_binary_sha256, "bundled rhwp identity"),
    check("runtime.surface", !/genspark/iu.test(studioText), "owned Studio has no Genspark runtime surface"),
    identityCheck(snapshot, reader, 8, ["inputs", "outputs", "sourceFiles"]),
  ];
  return result("AC-01", checks, [], "Pinned owned Docs runtime, provenance, notices, and SBOM checks passed.");
}

function evaluateAc02(snapshot, reader) {
  const schema = snapshot[criterionContractPaths["AC-02"][0]];
  const recovery = snapshot[criterionContractPaths["AC-02"][1]];
  const required = new Set(schema.required ?? []);
  const authoritative = ["elements", "assets", "styles", "templateBinding", "evidenceLinks", "revisions", "history"];
  const checks = [
    check("schema.authoritative-fields", authoritative.every((field) => required.has(field)), "all authoritative fields are required"),
    ...booleanChecks("project", recovery.projectStore ?? {}, [
      "assetsPreserved", "derivedExportDidNotMutateProject", "evidenceLinksPreserved", "recoveredAutosave",
      "recoveryFileRemovedAfterCommit", "revisionHistoryPreserved", "richStructurePreserved", "stableElementIDs",
      "stylesPreserved", "templateBindingPreserved",
    ]),
    check("migration.version", recovery.migration?.fromSchemaVersion === 0 && recovery.migration?.toSchemaVersion === schema.properties?.schemaVersion?.const, "legacy migration reaches current schema"),
    check("migration.identity", new Set(recovery.migration?.elementIDs ?? []).size === (recovery.migration?.elementIDs ?? []).length && recovery.migration?.historyEvent === "schema-migrated", "migration preserves unique IDs and records history"),
    check("window.visible", recovery.windowLifecycle?.visibleWindowCount >= 1, "a visible document window was observed"),
    identityCheck(snapshot, reader, 4),
  ];
  return result("AC-02", checks, [], "Project persistence, recovery, migration, and export-authority checks passed.");
}

function evaluateAc03(snapshot, reader) {
  const catalog = snapshot[criterionContractPaths["AC-03"][0]];
  const update = snapshot[criterionContractPaths["AC-03"][1]];
  const receipt = update.result ?? {};
  const checks = [
    check("catalog.signed-envelope", typeof catalog.envelope?.payload === "string" && typeof catalog.envelope?.signature === "string" && typeof catalog.envelope?.keyID === "string", "signed catalog envelope"),
    ...booleanChecks("template", receipt, [
      "exportSnapshotUsedRuleRevision", "failedUpdatePreservedLastTrusted", "immutableRevisionCreated",
      "lowerPrecedenceCouldNotOverride", "officialRuleHistoryRecorded", "officialRuleTitleElementEnforced",
      "repeatedEnforcementWasIdempotent", "signatureRejected", "unsupportedOfficialFieldRejected",
    ]),
    check("template.precedence", receipt.highestAppliedPrecedence >= 100 && receipt.authoritativeTitle === receipt.exportBoundProjectTitle?.replace(/^#\s+/u, ""), "highest official title reaches export"),
    check("template.pinning", receipt.pinnedTemplateVersionBeforeUpdate === receipt.pinnedTemplateVersionAfterUpdate, "pinned document version remains unchanged"),
    check("template.rollback", receipt.rollbackCatalogVersion === receipt.bootstrappedCatalogVersion && receipt.offlineReloadCatalogVersion === receipt.updatedCatalogVersion, "rollback and offline catalog lineage"),
    identityCheck(snapshot, reader, 2),
  ];
  return result("AC-03", checks, [], "Signed updates, pinned templates, rollback, and official-rule enforcement checks passed.");
}

function evaluateAc04(snapshot, reader) {
  const provider = snapshot[criterionContractPaths["AC-04"][0]];
  const proposal = snapshot[criterionContractPaths["AC-04"][1]];
  const checks = [
    check("providers.approved-set", JSON.stringify([...(provider.approvedProviderKinds ?? [])].sort()) === JSON.stringify(approvedProviders), "only approved existing providers"),
    ...booleanChecks("providers", provider, [
      "offlineEditingAndExportAvailable", "localAdapterUnavailableWithoutFallback", "allConsentBindingsRequired",
      "forbiddenDataAbsentFromPersistence", "secureProviderTransportBehavior", "brandedEndpointAllowlistEnforced",
      "endpointValidationPrecedesPersistence", "consentRebindingRequired",
    ]),
    ...booleanChecks("proposal", proposal, [
      "proposalDidNotMutateDocument", "diffsExposeStableTargets", "staleProposalRejected",
      "wholeApprovalAppliedAtomically", "partialApprovalAppliedAtomically", "rejectionPersisted",
      "undoRedoPersistedAcrossRestart", "revocationBlockedFutureRequest", "actualScopedTargetIDsEnforced",
      "operationSpecificCommands.missingDataMarking", "operationSpecificCommands.evidenceClaimCheck",
      "operationSpecificCommands.tableCellUpdate", "exactTablePathFailClosed", "tableCellOnlyMutation", "fullDiffPersisted",
    ]),
    identityCheck(snapshot, reader, 2),
  ];
  return result("AC-04", checks, [], "Offline provider, consent, scoped proposal, diff, and revision checks passed.");
}

function evaluateAc05(snapshot, reader) {
  const authoring = snapshot[criterionContractPaths["AC-05"][0]];
  const matrix = snapshot[criterionContractPaths["AC-05"][1]];
  const losses = snapshot[criterionContractPaths["AC-05"][2]];
  const validation = snapshot[criterionContractPaths["AC-05"][3]];
  const elementIDs = (authoring.elements ?? []).map((entry) => entry.id);
  const rows = matrix.matrix ?? [];
  const receipts = validation.receipts ?? [];
  const selected = new Set(receipts.flatMap((receipt) => receipt.selectedFormats ?? []));
  const validClassifications = new Set(matrix.classifications ?? []);
  const resultRows = receipts.flatMap((receipt) => receipt.results ?? []);
  const checks = [
    check("capabilities.unique", elementIDs.length > 0 && new Set(elementIDs).size === elementIDs.length, "authoring capability IDs are unique"),
    check("matrix.coverage", elementIDs.every((id) => rows.some((row) => row.capability === id)) && rows.every((row) => formats.every((format) => validClassifications.has(row[format]))), "every capability has four classified mappings"),
    check("exports.selected-formats", formats.every((format) => selected.has(format)), "all four formats selected across executable receipts"),
    check("exports.validation", resultRows.length > 0 && resultRows.every((entry) => entry.structuralValid === true && entry.semanticValid === true && entry.validation?.structuralValid === true && entry.validation?.semanticValid === true && (entry.validation?.orderedElements ?? []).length > 0), "published results carry artifact-derived validation"),
    check("exports.disposition", receipts.every((receipt) => {
      const selectedList = receipt.selectedFormats ?? [];
      const publishedList = receipt.publishedFormats ?? [];
      const blockedList = receipt.blockedFormats ?? [];
      const failedList = receipt.failedFormats ?? [];
      const resultList = (receipt.results ?? []).map((entry) => entry.format);
      const selectedFormats = new Set(selectedList);
      const dispositionList = [...publishedList, ...blockedList, ...failedList];
      const dispositionFormats = new Set(dispositionList);
      const visualFlattening = (receipt.lossReports ?? []).some((entry) => entry.classification === "visual-only-flattening" && publishedList.includes(entry.format));
      return receipt.allAuthoredElementIDsPreserved === true
        && (!visualFlattening || receipt.flatteningConsentRecorded === true)
        && selectedFormats.size === selectedList.length
        && [publishedList, blockedList, failedList, resultList].every((entries) => new Set(entries).size === entries.length)
        && dispositionFormats.size === dispositionList.length
        && dispositionFormats.size === selectedFormats.size
        && [...selectedFormats].every((format) => dispositionFormats.has(format))
        && publishedList.length === resultList.length
        && publishedList.every((format) => resultList.includes(format));
    }), "every selected format is published or precisely blocked with one validated result per publication"),
    check("exports.runtime-failures", receipts.every((receipt) => (receipt.failedFormats ?? []).length === 0 && (receipt.failures ?? []).length === 0), "canonical export receipts contain no runtime failures"),
    check("losses.precise", losses.length > 0 && losses.every((entry) => formats.includes(entry.format) && typeof entry.elementID === "string" && typeof entry.elementPath === "string" && typeof entry.fallback === "string" && (entry.classification !== "visual-only-flattening" || entry.requiresConsent === true) && (entry.classification !== "semantic-loss" || entry.requiresConsent === false)), "loss reports bind format, element, path, fallback, and consent"),
    identityCheck(snapshot, reader, 2),
  ];
  return result("AC-05", checks, [], "Four-format capability, validation, consent, and loss-report checks passed.");
}

export const evaluatorsAc01ToAc05 = {
  "AC-01": evaluateAc01,
  "AC-02": evaluateAc02,
  "AC-03": evaluateAc03,
  "AC-04": evaluateAc04,
  "AC-05": evaluateAc05,
};
