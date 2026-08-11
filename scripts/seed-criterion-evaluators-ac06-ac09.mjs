import {
  check,
  criterionContractPaths,
  formats,
  identityCheck,
  result,
} from "./seed-criterion-contract-core.mjs";
import { evaluateAc07 } from "./seed-criterion-evaluator-ac07.mjs";

function evaluateAc06(snapshot, reader) {
  const lifecycle = snapshot[criterionContractPaths["AC-06"][0]];
  const finalManifest = snapshot[criterionContractPaths["AC-06"][1]];
  const scenarios = new Map((lifecycle.scenarios ?? []).map((entry) => [entry.result?.operationID, entry.result]));
  const required = ["batch-ac06-partial", "batch-ac06-cancelled", "batch-ac06-cancel-before-publication", "batch-ac06-existing", "batch-ac06-crashed", "batch-ac06-retry-after-crash", "batch-ac06-disk-full", "batch-ac06-retry-after-disk-full"];
  const clean = [...scenarios.values()].every((manifest) => manifest.cleanupState === "clean");
  const validatedPublications = [...scenarios.values()].flatMap((manifest) => manifest.items ?? []).every((item) => item.state !== "published"
    || (typeof item.artifactHash === "string" && item.publicationIntent?.expectedArtifactHash === item.artifactHash));
  const existing = scenarios.get("batch-ac06-existing");
  const recovery = lifecycle.recovery ?? {};
  const reconciled = recovery.reconciledAfterMove;
  const reconciledItem = reconciled?.items?.[0];
  const startup = recovery.startupRecovered ?? [];
  const checks = [
    check("batch.scenarios", required.every((id) => scenarios.has(id)), "all partial, cancellation, non-overwrite, crash, disk-full, and retry scenarios"),
    check("batch.cleanup", clean, "all temporary cleanup states are clean"),
    check("batch.no-unvalidated-publication", validatedPublications, "published items bind exact validated artifact hashes"),
    check("batch.partial-isolation", finalManifest.state === "completed-with-errors" && finalManifest.items?.some((item) => item.state === "failed") && finalManifest.items?.some((item) => item.state === "published"), "sibling successes survive partial failure"),
    check("batch.non-overwrite", existing?.items?.some((item) => item.diagnosticCode === "destination-exists") && existing?.destinationIntegrity?.existingBytesPreserved === true, "existing destination bytes remain unchanged"),
    check("batch.retry-lineage", scenarios.get("batch-ac06-retry-after-crash")?.retryOfOperationID === "batch-ac06-crashed" && scenarios.get("batch-ac06-retry-after-disk-full")?.retryOfOperationID === "batch-ac06-disk-full", "retry uses a new operation ID"),
    check("batch.post-move-reconciliation", reconciled?.operationID === "batch-ac06-crash-after-move" && reconciled?.state === "completed" && reconciled?.cleanupState === "clean" && reconciledItem?.state === "published" && reconciledItem?.publicationIntent?.expectedArtifactHash === reconciledItem?.artifactHash, "post-move crash is reconciled only from exact intended bytes"),
    check("batch.pre-manifest-isolation", recovery.manifestlessOperationID === "batch-ac06-pre-manifest" && recovery.manifestlessOperationExists === true && recovery.manifestlessManifestExists === false, "manifestless operation is isolated"),
    check("batch.startup-recovery-isolation", startup.length === 1 && startup[0]?.operationID === "batch-ac06-startup-recoverable" && startup[0]?.state === "interrupted", "startup recovery continues past a manifestless sibling"),
    identityCheck(snapshot, reader, required.length),
  ];
  return result("AC-06", checks, [], "Batch isolation, cancellation, recovery, non-overwrite, and cleanup checks passed.");
}

function evaluateAc08(snapshot, reader) {
  const axe = snapshot[criterionContractPaths["AC-08"][0]];
  const manual = snapshot[criterionContractPaths["AC-08"][1]];
  const visual = snapshot[criterionContractPaths["AC-08"][2]];
  const receipt = manual.verificationReceipt ?? {};
  const voiceOver = manual.voiceOver ?? {};
  const keyboard = manual.keyboard ?? {};
  const testedHashes = receipt.testedSourceSHA256 ?? {};
  const sourcesCurrent = Object.entries(testedHashes).every(([path, hash]) => reader.sha256(path) === hash);
  const commands = receipt.commands ?? [];
  const browserCommand = commands.find((entry) => entry.exitCode === 0 && /playwright test/u.test(entry.command));
  const browserCounts = receipt.browserTests;
  const structuredBrowserPassed = browserCounts?.passed === 6 && browserCounts?.failed === 0;
  const commandBrowserPassed = /\b6\/6 passed\b/u.test(browserCommand?.result ?? "");
  const browserExecuted = browserCommand !== undefined
    && (browserCounts === undefined ? commandBrowserPassed : structuredBrowserPassed);
  const sourceContractExecuted = commands.some((entry) => entry.exitCode === 0 && /test_ac08_accessibility\.py/u.test(entry.command));
  const visualCommandsPassed = commands.filter((entry) => /visual-qa\.mjs image-diff/u.test(entry.command)).length >= 2
    && commands.filter((entry) => /visual-qa\.mjs image-diff/u.test(entry.command)).every((entry) => entry.exitCode === 0);
  const comparisons = visual.comparisons ?? [];
  const pinnedReference = visual.pinnedReference ?? {};
  const referenceSource = visual.referenceSource ?? {};
  const requiredJourneys = ["guided-authoring", "AI-proposal-review", "AI-consent", "official-rule-and-template-guidance", "loss-resolution", "single-export", "batch-export"];
  const journeyMap = new Map((voiceOver.journeys ?? []).map((journey) => [journey.name, journey]));
  const blockerHashes = voiceOver.browserTarget?.sourceSHA256 ?? {};
  const blockerCurrent = ["index.html", "styles.css", "app.js"].every((name) => blockerHashes[name] === testedHashes[`Resources/Studio/${name}`] && reader.sha256(`Resources/Studio/${name}`) === blockerHashes[name]);
  const checks = [
    check("accessibility.browser", browserExecuted && sourceContractExecuted && visualCommandsPassed, "browser, keyboard, source-contract, and visual commands exited successfully"),
    check("accessibility.freshness", receipt.freshness?.sourceHashesMatchedBeforeAndAfterBrowserRun === true && sourcesCurrent, "browser evidence binds current Studio source"),
    check("accessibility.axe", Array.isArray(axe) && axe.length >= 6 && axe.every((state) => Array.isArray(state.violations) && state.violations.length === 0), "all required live states have zero axe violations"),
    check("accessibility.visual", comparisons.length >= 2 && comparisons.every((entry) => entry.dimensionsMatch === true && entry.alphaChannelIntact === true && entry.similarityScore >= 90), "approved-size visual comparisons meet threshold"),
    check("accessibility.keyboard-evidence", keyboard.journeys?.length === 7 && keyboard.journeys.every((journey) => journey.status === "PASS" && journey.criticalActivationInputSource === "keyboard"), "all seven journeys record keyboard critical activation"),
    check("accessibility.programmatic-states", keyboard.programmaticStates?.outlineCurrent?.passed === true && keyboard.programmaticStates?.formatToggles?.onAndOffObserved === true, "outline and formatting states are programmatically exposed"),
    check("accessibility.focus-restoration", Object.values(keyboard.focusTransitions ?? {}).length >= 2 && Object.values(keyboard.focusTransitions ?? {}).every((transition) => transition.activeElementMatched === true), "AI approval and rejection restore focus"),
    check("accessibility.reference-lineage", pinnedReference.passed === true && pinnedReference.lineage === "pinned-genoffice-docs-fidelity-v1" && pinnedReference.referenceSetHash === referenceSource.referenceSetHash && referenceSource.upstream?.commit === "d8305ff2dc152593a1ec5639d77e6860c6a512bd", "semantic comparison uses the distinct pinned GenOffice Docs lineage"),
    check("accessibility.voiceover-contract", requiredJourneys.every((name) => journeyMap.has(name)), "all seven VoiceOver journeys are represented"),
    identityCheck(snapshot, reader, 8),
  ];
  const journeyFailure = [...journeyMap.values()].some((journey) => journey.status === "FAIL");
  checks.push(check("accessibility.voiceover-failures", !journeyFailure, "no executed VoiceOver journey failed"));
  const allPassed = requiredJourneys.every((name) => journeyMap.get(name)?.status === "PASS");
  const allNotRun = requiredJourneys.every((name) => journeyMap.get(name)?.status === "NOT_RUN");
  const supportedVoiceOverBlocker = voiceOver.console?.screenLocked === true
    || voiceOver.blocker?.code === "exact-package-ax-tree-empty";
  const blockers = allPassed ? [] : allNotRun && voiceOver.status === "BLOCKED" && supportedVoiceOverBlocker && blockerCurrent && typeof voiceOver.recordedAt === "string"
    ? [voiceOver.rerunCondition ?? "Unlock the console and run all seven VoiceOver journeys."]
    : [];
  if (!allPassed && blockers.length === 0) checks.push(check("accessibility.voiceover-outcome", false, "VoiceOver is neither complete nor supported by a locked-console blocker"));
  return result("AC-08", checks, blockers, "Current browser, keyboard, axe, visual, and VoiceOver journey checks passed.");
}

function evaluateAc09(snapshot, reader) {
  const environment = snapshot[criterionContractPaths["AC-09"][0]];
  const results = snapshot[criterionContractPaths["AC-09"][1]];
  const profile = environment.profile ?? {};
  const fixtures = new Map((environment.fixtures ?? []).map((fixture) => [fixture.fixtureID, fixture]));
  const observations = results.exportObservations ?? [];
  const observationPairs = new Set(observations.map((entry) => `${entry.fixtureID}/${entry.format}`));
  const expectedPairs = ["100-page", "50-mb"].flatMap((fixture) => formats.map((format) => `${fixture}/${format}`));
  const interaction = results.interactionObservation ?? {};
  const thresholds = profile.thresholds ?? {};
  const authoredFixture = fixtures.get("50-mb") ?? {};
  const identity = results.executionIdentity ?? {};
  const ui = results.uiObservation ?? {};
  const checks = [
    check("performance.environment", environment.environment?.architecture === profile.requiredArchitecture && /Apple/u.test(environment.environment?.processor ?? ""), "recorded Apple Silicon arm64 environment"),
    check("performance.profile", environment.profileHash === environment.profileEvidence?.sha256 && profile.profileVersion === environment.profileVersion, "frozen profile identity"),
    check("performance.fixtures", fixtures.get("100-page")?.declaredPageCount >= profile.fixtures?.["100-page"]?.minimumPageCount && authoredFixture.authoredUTF8ByteCount >= profile.fixtures?.["50-mb"]?.minimumAuthoredUTF8Bytes && typeof authoredFixture.authoredContentHash === "string", "separate authored 100-page and 50 MB fixtures"),
    check("performance.coverage", observationPairs.size === expectedPairs.length && expectedPairs.every((pair) => observationPairs.has(pair)), "exactly two fixtures by four formats"),
    check("performance.exports", observations.every((entry) => entry.durationSeconds <= thresholds.exportSeconds && entry.structuralValid === true && entry.semanticValid === true && entry.artifactEvidence?.sha256 === entry.artifactHash && entry.authoredContentValidated === true), "all artifact-derived exports meet the 30-second and authored-content contract"),
    check("performance.interaction", interaction.responsive === true && interaction.maximumHeartbeatGapMilliseconds <= thresholds.mainThreadHeartbeatMilliseconds && interaction.firstProgressMilliseconds <= thresholds.firstProgressMilliseconds && interaction.maximumProgressGapMilliseconds <= thresholds.progressGapMilliseconds && interaction.cancellationRequestMilliseconds <= thresholds.cancellationRequestMilliseconds && interaction.cancellationCompletionMilliseconds <= thresholds.cancellationCompletionMilliseconds, "responsiveness, progress, and cancellation thresholds"),
    check("performance.package-identity", identity.bundleIdentifier === "com.muni.public-document" && /^sha256:[a-f0-9]{64}$/u.test(identity.executableSHA256 ?? "") && /^sha256:[a-f0-9]{64}$/u.test(identity.genOfficeRuntimeManifestSHA256 ?? "") && /^sha256:[a-f0-9]{64}$/u.test(identity.genOfficeBundleSHA256 ?? "") && /^sha256:[a-f0-9]{64}$/u.test(identity.nodeExecutableSHA256 ?? "") && /^sha256:[a-f0-9]{64}$/u.test(identity.rhwpExecutableSHA256 ?? ""), "benchmark binds exact packaged executable and engines"),
    check("performance.visible-ui", ui.status === "pass" && ui.observationSurface === "AppKit" && ui.windowVisible === true && ui.onScreenWindowCount >= 1 && ui.progressObservedMainThreadOnly === true && ui.cancelButtonActionPath === "NSButton.performClick" && ui.cancelButtonActionInvocations >= 1 && ui.cancelActionObservedOnMainThread === true, "visible AppKit progress and real cancel button were observed"),
    identityCheck(snapshot, reader, 10),
  ];
  return result("AC-09", checks, [], "Authored fixture export and interaction performance checks passed.");
}

export const evaluatorsAc06ToAc09 = {
  "AC-06": evaluateAc06,
  "AC-07": evaluateAc07,
  "AC-08": evaluateAc08,
  "AC-09": evaluateAc09,
};
