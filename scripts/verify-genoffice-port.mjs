import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, lstatSync, readFileSync, realpathSync } from "node:fs";
import { resolve, sep } from "node:path";

const projectRoot = resolve(import.meta.dirname, "..");
const approvedCommit = "d8305ff2dc152593a1ec5639d77e6860c6a512bd";
const approvedRepository = "https://github.com/genspark-ai/genoffice.git";
const defaultManifest = "provenance/genoffice-docs-port.json";
const approvedSources = new Map([
  ["apps/docs/src/renderer/App.tsx", "sha256:0cd748ce1b259c52a051f9976f785119e03f9dd6358b0f3136d3c75bf136b155"],
  ["apps/docs/src/renderer/components/Ribbon.tsx", "sha256:9b17e022ddd5f8d0d5ba728b1522a1f70b80b2734f0e1f5dc2cd55774da8019d"],
  ["apps/docs/src/renderer/components/NavPane.tsx", "sha256:2feb9209f9a92e7f54a71930d11502e4e3fbae3bc32a218b1903b0af6f4a03c7"],
  ["apps/docs/src/renderer/components/ribbon-tabs.tsx", "sha256:66a02109b0450ba5306f2f1a695810d55f47960cec0e22746489af11b9157f34"],
  ["apps/docs/src/renderer/file-actions.ts", "sha256:6699e5b841d5a2430018e9644110777c84b9f9525e88055e77661a65c4bfa08c"],
  ["apps/docs/src/renderer/styles.css", "sha256:1ea360efb6976e3a2a1378f51dd08723b2a8bade1ab5b34d6f0eccf69c89bae7"],
  ["packages/ui/src/index.ts", "sha256:761c3bddd885c8f5fd9d54bab6faa6009f30c95f31d36662fc51e37802fe5bcf"],
  ["packages/docx-engine/src/index.ts", "sha256:707d99e0ca80ba0ed2ed0752dfe90b9e5597d82023fb48eb4c3161d2350106ab"],
  ["packages/docx-engine/src/generate.ts", "sha256:067b6ba8f9e01c752fe572fa2be21770a37adf0cb88f23276505fae07597a79b"],
  ["packages/docx-engine/src/patch.ts", "sha256:ec2140201a91eaf9f46ddfa2bb99e3d39728ed390a5fd72412ed1a3639065b10"],
]);
const approvedScopes = new Set([
  "apps/docs/src/renderer",
  "packages/ui/src",
  "packages/docx-engine/src",
]);
const approvedLocalPaths = new Set([
  "Resources/Studio/index.html",
  "Resources/Studio/styles.css",
  "Resources/Studio/app.js",
  "Sources/PublicDocumentApp/ExportSerializers.swift",
  "Sources/PublicDocumentApp/OfficialLayoutEngine.swift",
  "Sources/PublicDocumentApp/ExportValidation.swift",
  "Resources/Studio/ai-settings.js",
  "Resources/Studio/ai-workspace.js",
  "Resources/Studio/bridge.js",
  "Resources/Studio/easy-library.js",
  "Resources/Studio/easy-tools.js",
  "Resources/Studio/easy-tools-ui.js",
  "Resources/Studio/editor-commands.js",
  "Resources/Studio/export-dialogs.js",
  "Resources/Studio/project-content.js",
  "Resources/Studio/project-model.js",
  "Resources/Studio/project-render.js",
  "Resources/Studio/studio-events.js",
  "Resources/Studio/studio-prefs.js",
  "Resources/Studio/studio-state.js",
  "Resources/Studio/template-panel.js",
  "Resources/Studio/view-tab.js",
  "Resources/Studio/draft-wizard.js",
  "Resources/Studio/review-tab.js",
  "Resources/Studio/title-lock.js",
  "Resources/Studio/page-engine.js",
  "Resources/Studio/official-layout-profile.js",
]);
const approvedPortMarkers = new Set([
  "data-action=\"open-export\"",
  "--studio-accent",
  "projectBridge",
  "enum ExportSerializers",
  "enum ExportArtifactValidator",
]);
const forbiddenRuntimeWords = new Set(["genspark", "aipanel", "electron-updater", "websocket", "xmlhttprequest"]);

const parseArguments = (arguments_) => {
  let manifest = defaultManifest;
  let upstreamRoot = null;
  let localRoot = null;
  let hasManifestArgument = false;
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === "--upstream-root") {
      upstreamRoot = arguments_[index + 1] ?? null;
      index += 1;
    } else if (argument === "--local-root") {
      localRoot = arguments_[index + 1] ?? null;
      index += 1;
    } else if (argument === "--manifest") {
      manifest = arguments_[index + 1] ?? "";
      hasManifestArgument = true;
      index += 1;
    } else if (!hasManifestArgument && !argument.startsWith("-")) {
      manifest = argument;
      hasManifestArgument = true;
    } else {
      throw new Error(`unsupported argument: ${argument}`);
    }
  }
  if (
    !manifest
    || (arguments_.includes("--upstream-root") && !upstreamRoot)
    || (arguments_.includes("--local-root") && !localRoot)
  ) {
    throw new Error("manifest, --upstream-root, and --local-root values must not be empty");
  }
  return { manifest, upstreamRoot, localRoot };
};

const digest = (path) =>
  `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
const isSafeRelativePath = (path) =>
  typeof path === "string" && path.length > 0 && !path.startsWith("/") && !path.split("/").includes("..");
const setEquals = (left, right) =>
  left.size === right.size && [...left].every((value) => right.has(value));

const {
  manifest: manifestArgument,
  upstreamRoot: upstreamArgument,
  localRoot: localArgument,
} = parseArguments(
  process.argv.slice(2),
);
const manifestPath = resolve(projectRoot, manifestArgument);
const upstreamRoot = upstreamArgument ? resolve(upstreamArgument) : null;
const localRoot = localArgument ? resolve(localArgument) : projectRoot;
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const failures = [];

if (manifest.schemaVersion !== 1) failures.push("unsupported manifest schema");
if (manifest.integrationMode !== "pinned-adapter-runtime-fork") {
  failures.push("integration mode mismatch");
}
if (manifest.upstream?.repository !== approvedRepository) failures.push("GenOffice repository mismatch");
if (manifest.upstream?.commit !== approvedCommit) failures.push("GenOffice commit mismatch");
if (manifest.upstream?.license !== "Apache-2.0") failures.push("GenOffice license mismatch");
if (manifest.portBoundary?.directPackageRuntimeLinkage !== true) {
  failures.push("direct upstream package linkage must be true");
}
if (manifest.portBoundary?.upstreamRuntimeFilesBundled !== true) {
  failures.push("upstream runtime files must be declared bundled");
}

const reviewedScopes = new Set(manifest.portBoundary?.reviewedUpstreamSourceScopes ?? []);
if (!setEquals(reviewedScopes, approvedScopes)) failures.push("reviewed upstream scope mismatch");
const excludedScopes = new Set(manifest.portBoundary?.excludedUpstreamScopes ?? []);
for (const scope of ["ee", "apps/sheets", "apps/slides", "apps/pdf"]) {
  if (!excludedScopes.has(scope)) failures.push(`missing excluded upstream scope: ${scope}`);
}

const upstreamSources = Array.isArray(manifest.upstream?.sourceFiles)
  ? manifest.upstream.sourceFiles
  : [];
const upstreamPaths = new Set();
for (const source of upstreamSources) {
  if (!isSafeRelativePath(source.path)) failures.push(`unsafe upstream path: ${source.path}`);
  if (upstreamPaths.has(source.path)) failures.push(`duplicate upstream source: ${source.path}`);
  upstreamPaths.add(source.path);
  if (!/^sha256:[0-9a-f]{64}$/.test(source.sha256 ?? "")) {
    failures.push(`invalid upstream source hash: ${source.path}`);
  }
  if (approvedSources.get(source.path) !== source.sha256) {
    failures.push(`unapproved upstream source identity: ${source.path}`);
  }
  if (!Array.isArray(source.reviewedResponsibilities) || source.reviewedResponsibilities.length === 0) {
    failures.push(`missing upstream source responsibility: ${source.path}`);
  }
}
if (!setEquals(upstreamPaths, new Set(approvedSources.keys()))) {
  failures.push("upstream source inventory mismatch");
}

const localArtifacts = Array.isArray(manifest.localArtifacts) ? manifest.localArtifacts : [];
const localPaths = new Set();
if (lstatSync(localRoot).isSymbolicLink()) {
  failures.push("symlinked local verification root");
}
const physicalLocalRoot = realpathSync(localRoot);
for (const artifact of localArtifacts) {
  if (!isSafeRelativePath(artifact.path)) failures.push(`unsafe local port path: ${artifact.path}`);
  if (localPaths.has(artifact.path)) failures.push(`duplicate local port artifact: ${artifact.path}`);
  localPaths.add(artifact.path);
  const path = resolve(localRoot, artifact.path);
  if (!existsSync(path)) {
    failures.push(`missing local port artifact: ${artifact.path}`);
  } else if (lstatSync(path).isSymbolicLink()) {
    failures.push(`symlinked local port artifact: ${artifact.path}`);
  } else if (
    realpathSync(path) !== physicalLocalRoot
    && !realpathSync(path).startsWith(`${physicalLocalRoot}${sep}`)
  ) {
    failures.push(`local port artifact escapes verification root: ${artifact.path}`);
  } else if (digest(path) !== artifact.sha256) {
    failures.push(`local port hash drift: ${artifact.path}`);
  }
  if (artifact.runtimeSurface !== true) failures.push(`non-runtime local port artifact: ${artifact.path}`);
  if (!Array.isArray(artifact.portedResponsibilities) || artifact.portedResponsibilities.length === 0) {
    failures.push(`missing local port responsibility: ${artifact.path}`);
  }
  for (const source of artifact.upstreamSources ?? []) {
    if (!upstreamPaths.has(source)) failures.push(`unbound upstream source mapping: ${artifact.path}`);
  }
  if (!Array.isArray(artifact.upstreamSources) || artifact.upstreamSources.length === 0) {
    failures.push(`missing upstream source mapping: ${artifact.path}`);
  }
}
if (!setEquals(localPaths, approvedLocalPaths)) failures.push("local port inventory mismatch");
const declaredLocalPaths = new Set(manifest.portBoundary?.shippedLocalArtifacts ?? []);
if (!setEquals(localPaths, declaredLocalPaths)) failures.push("shipped local artifact boundary mismatch");

const runtimeText = localArtifacts
  .filter((artifact) => artifact.runtimeSurface && existsSync(resolve(localRoot, artifact.path)))
  .map((artifact) => readFileSync(resolve(localRoot, artifact.path), "utf8").toLowerCase())
  .join("\n");
const runtimeWords = new Set(runtimeText.match(/[a-z]+/g) ?? []);
const declaredForbiddenWords = new Set(manifest.excludedRuntimeWords ?? []);
if (!setEquals(declaredForbiddenWords, forbiddenRuntimeWords)) {
  failures.push("excluded runtime word policy mismatch");
}
for (const word of declaredForbiddenWords) {
  if (runtimeWords.has(word)) failures.push(`excluded runtime word is reachable: ${word}`);
}
const requiredPortMarkers = new Set(manifest.requiredPortMarkers ?? []);
if (!setEquals(requiredPortMarkers, approvedPortMarkers)) failures.push("required port marker policy mismatch");
for (const marker of requiredPortMarkers) {
  if (!runtimeText.includes(marker.toLowerCase())) failures.push(`missing port marker: ${marker}`);
}

let upstreamVerified = false;
if (upstreamRoot) {
  const head = execFileSync("git", ["-C", upstreamRoot, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
  if (head !== approvedCommit) failures.push(`upstream checkout mismatch: ${head}`);
  for (const source of upstreamSources) {
    const path = resolve(upstreamRoot, source.path);
    if (!existsSync(path)) {
      failures.push(`missing upstream source: ${source.path}`);
    } else if (digest(path) !== source.sha256) {
      failures.push(`upstream source hash drift: ${source.path}`);
    }
  }
  upstreamVerified = !failures.some((failure) => failure.includes("upstream"));
}

const result = {
  schemaVersion: 1,
  verdict: failures.length === 0 ? "pass" : "fail",
  integrationMode: manifest.integrationMode,
  upstreamCommit: manifest.upstream?.commit,
  upstreamVerified,
  upstreamSourceCount: upstreamSources.length,
  localArtifactCount: localArtifacts.length,
  directPackageRuntimeLinkage: manifest.portBoundary?.directPackageRuntimeLinkage,
  upstreamRuntimeFilesBundled: manifest.portBoundary?.upstreamRuntimeFilesBundled,
  failures,
};
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
if (failures.length > 0) process.exitCode = 1;
