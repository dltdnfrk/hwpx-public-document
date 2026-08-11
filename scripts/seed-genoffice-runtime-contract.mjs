import { check } from "./seed-criterion-contract-core.mjs";

const rawSha256 = /^[a-f0-9]{64}$/u;
const forbiddenSurface = /genspark|AiPanel|electron-updater|apps\/(?:sheets|slides|pdf|shell|markdown)|packages\/(?:ai-provider|ai-search|agent-core|pptx-engine|pptx-render|electron-utils)|fetch\s*\(|WebSocket|XMLHttpRequest|sendBeacon/iu;
const requiredPackages = ["@genoffice/docx-engine", "@genoffice/ui", "@tiptap/core", "react", "react-dom"];

const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const safeLogicalPath = (path) => typeof path === "string"
  && !path.startsWith("/")
  && !path.includes("\\")
  && !path.split("/").includes("..");

function attempt(predicate) {
  try {
    return predicate() === true;
  } catch {
    return false;
  }
}

function uniqueRecords(records) {
  if (!Array.isArray(records) || records.length === 0) return false;
  const paths = records.map((entry) => entry?.path);
  return records.every((entry) => safeLogicalPath(entry?.path) && rawSha256.test(entry?.sha256))
    && new Set(paths).size === paths.length;
}

function inputPathAllowed(path) {
  return /^adapter\/GenOfficeFork\//u.test(path)
    || path === "adapter/scripts/build-genoffice-runtime.mjs"
    || /^dependencies\/node_modules\//u.test(path)
    || /^upstream\/(?:LICENSE|package-lock\.json)$/u.test(path)
    || /^upstream\/(?:apps\/docs|packages\/(?:ui|docx-engine))\//u.test(path);
}

function packageLedgerValid(packages) {
  if (!Array.isArray(packages) || packages.length < requiredPackages.length) return false;
  const names = packages.map((entry) => entry?.name);
  return new Set(names).size === names.length
    && requiredPackages.every((name) => names.includes(name))
    && packages.every((entry) => typeof entry.version === "string" && entry.version.length > 0
      && typeof entry.license === "string" && entry.license.length > 0
      && rawSha256.test(entry.packageJsonSha256));
}

function buildToolValid(buildTool) {
  return buildTool?.name === "esbuild"
    && typeof buildTool.version === "string" && buildTool.version.length > 0
    && typeof buildTool.license === "string" && buildTool.license.length > 0
    && rawSha256.test(buildTool.packageJsonSha256);
}

function resourceRecordCurrent(record, reader) {
  return safeLogicalPath(record?.path)
    && rawSha256.test(record?.sha256)
    && Number.isSafeInteger(record?.sizeBytes)
    && record.sizeBytes > 0
    && reader.sha256(`Resources/${record.path}`) === record.sha256
    && reader.size(`Resources/${record.path}`) === record.sizeBytes;
}

function runtimeContractValid(manifest) {
  const outputPaths = new Set((manifest.outputs ?? []).map((entry) => entry.path));
  const runtimePaths = [manifest.runtime?.browserBundlePath, manifest.runtime?.docxCliPath];
  return runtimePaths.every((path) => outputPaths.has(path))
    && manifest.runtime?.offline === true
    && manifest.runtime?.customElementTag === "public-document-genoffice-editor"
    && manifest.runtime?.readyEvent === "public-document-genoffice-ready"
    && manifest.runtime?.changeEvent === "public-document-genoffice-change"
    && manifest.node?.version === "22.17.1"
    && manifest.node?.architecture === "arm64"
    && Array.isArray(manifest.node?.linkedLibraries)
    && manifest.node.linkedLibraries.length > 0
    && manifest.node.linkedLibraries.every((path) => path.startsWith("/System/Library/") || path.startsWith("/usr/lib/"));
}

function forbiddenScanCurrent(manifest, reader, includeAdapters) {
  const adapterPaths = includeAdapters ? manifest.inputs
    .filter((entry) => /^adapter\/GenOfficeFork\/.+\.(?:mjs|ts|tsx)$/u.test(entry.path))
    .map((entry) => entry.path.slice(8)) : [];
  const outputPaths = [manifest.runtime.browserBundlePath, manifest.runtime.docxCliPath].map((path) => `Resources/${path}`);
  return [...adapterPaths, ...outputPaths].every((path) => !forbiddenSurface.test(reader.text(path)));
}

export function repositoryGenOfficeRuntimeChecks(manifest, artifactLock, reader) {
  const sourcePath = manifest.inputLock?.sourcePath;
  let projectLock;
  try {
    projectLock = reader.json(sourcePath);
  } catch {
    projectLock = undefined;
  }
  const lockCurrent = projectLock !== undefined
    && sourcePath === "GenOfficeFork/runtime-input-lock.json"
    && manifest.inputLock?.packagedPath === "Provenance/genoffice-runtime-input-lock.json"
    && rawSha256.test(manifest.inputLock?.sha256)
    && reader.sha256(sourcePath) === manifest.inputLock.sha256
    && same(projectLock, artifactLock)
    && artifactLock.schemaVersion === 1
    && artifactLock.upstreamCommit === manifest.upstream?.commit
    && buildToolValid(manifest.buildTool)
    && same(artifactLock.buildTool, manifest.buildTool)
    && same(artifactLock.inputs, manifest.inputs)
    && same(artifactLock.packages, manifest.packages);
  const inputs = manifest.inputs ?? [];
  const prefixes = new Set(inputs.map((entry) => entry.path?.split("/")[0]));
  const inputsValid = uniqueRecords(inputs)
    && same(inputs.map((entry) => entry.path), [...inputs.map((entry) => entry.path)].sort())
    && inputs.every((entry) => inputPathAllowed(entry.path))
    && ["adapter", "dependencies", "upstream"].every((prefix) => prefixes.has(prefix));
  const adaptersCurrent = attempt(() => inputs.filter((entry) => entry.path.startsWith("adapter/"))
    .every((entry) => reader.sha256(entry.path.slice(8)) === entry.sha256));
  const outputsCurrent = attempt(() => uniqueRecords(manifest.outputs) && manifest.outputs.every((entry) => resourceRecordCurrent(entry, reader)));
  const nodeCurrent = attempt(() => safeLogicalPath(manifest.node?.sourcePath)
    && rawSha256.test(manifest.node?.sha256)
    && Number.isSafeInteger(manifest.node?.sizeBytes)
    && reader.sha256(`Resources/${manifest.node.sourcePath}`) === manifest.node.sha256
    && reader.size(`Resources/${manifest.node.sourcePath}`) === manifest.node.sizeBytes);
  return [
    check("runtime-manifest.input-lock", lockCurrent, "materialized and checked runtime input locks exactly bind manifest inputs and packages"),
    check("runtime-manifest.inputs", inputsValid && adaptersCurrent && packageLedgerValid(manifest.packages), "safe locked upstream, dependency, and current adapter inputs"),
    check("runtime-manifest.outputs", outputsCurrent && nodeCurrent, "Resources-relative runtime outputs and Node match exact hashes and sizes"),
    check("runtime-manifest.contract", runtimeContractValid(manifest), "exact browser, CLI, events, offline, and arm64 Node contract"),
    check("runtime-manifest.forbidden-surface", attempt(() => forbiddenScanCurrent(manifest, reader, true)), "independent adapter and shipped bundle scan excludes forbidden runtime surfaces"),
  ];
}

export function packagedGenOfficeRuntimeChecks(manifest, inputLock, reader) {
  const lockPath = `Resources/${manifest.inputLock?.packagedPath}`;
  const lockCurrent = attempt(() => manifest.inputLock?.sourcePath === "GenOfficeFork/runtime-input-lock.json"
    && manifest.inputLock?.packagedPath === "Provenance/genoffice-runtime-input-lock.json"
    && reader.sha256(lockPath) === manifest.inputLock.sha256
    && inputLock.upstreamCommit === manifest.upstream?.commit
    && buildToolValid(manifest.buildTool)
    && same(inputLock.buildTool, manifest.buildTool)
    && same(inputLock.inputs, manifest.inputs)
    && same(inputLock.packages, manifest.packages));
  const outputsCurrent = attempt(() => uniqueRecords(manifest.outputs) && manifest.outputs.every((entry) => resourceRecordCurrent(entry, reader)));
  const nodeCurrent = attempt(() => reader.sha256(`Resources/${manifest.node.sourcePath}`) === manifest.node.sha256
    && reader.size(`Resources/${manifest.node.sourcePath}`) === manifest.node.sizeBytes);
  return [
    check("release.genoffice-lock", lockCurrent, "packaged runtime lock exactly binds manifest inputs and packages"),
    check("release.genoffice-outputs", outputsCurrent && nodeCurrent, "packaged GenOffice outputs and Node match exact hashes and sizes"),
    check("release.genoffice-contract", runtimeContractValid(manifest), "packaged GenOffice runtime contract remains exact"),
    check("release.genoffice-forbidden-surface", attempt(() => forbiddenScanCurrent(manifest, reader, false)), "packaged runtime bundle scan excludes forbidden surfaces"),
  ];
}
