#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { constants, accessSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const rhwpPath = join(projectRoot, "Resources/Engines/rhwp");
const corpusPath = join(projectRoot, "Resources/Compatibility/compatibility-corpus-1.0.0.json");
const requiredRhwpHash = "sha256:a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b";
const requiredArguments = new Set(["--artifact", "--fixture", "--output-root", "--format"]);
const allowedFormats = new Set(["hwpx", "hwp"]);

class ObservationError extends Error {}

const fail = (message) => { throw new ObservationError(message); };
const sha256 = (path) => `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
const projectPath = (path) => relative(projectRoot, path).split(sep).join("/");
const writeJSON = (path, value) => writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);

function parseArguments(argv) {
  if (argv.length !== 8) fail("usage: verify-rhwp-visual.mjs --artifact PATH --fixture PATH --output-root PATH --format hwpx|hwp");
  const parsed = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const [key, value] = [argv[index], argv[index + 1]];
    if (!requiredArguments.has(key) || parsed.has(key) || !value) fail(`invalid argument: ${key ?? "missing"}`);
    parsed.set(key, value);
  }
  for (const key of requiredArguments) if (!parsed.has(key)) fail(`missing argument: ${key}`);
  const format = parsed.get("--format");
  if (!allowedFormats.has(format)) fail(`unsupported format: ${format}`);
  return { artifact: parsed.get("--artifact"), fixture: parsed.get("--fixture"), outputRoot: parsed.get("--output-root"), format };
}

function isConfined(path) {
  const delta = relative(projectRoot, path);
  return delta !== "" && delta !== ".." && !delta.startsWith(`..${sep}`) && !isAbsolute(delta);
}

function confinedFile(rawPath, label) {
  const path = realpathSync(resolve(projectRoot, rawPath));
  if (!isConfined(path) || !statSync(path).isFile()) fail(`${label} must be a file inside the project root`);
  return path;
}

function confinedOutput(rawPath) {
  const path = resolve(projectRoot, rawPath);
  if (!isConfined(path)) fail("output root must be inside the project root");
  const parent = realpathSync(dirname(path));
  if (!isConfined(parent) || !statSync(parent).isDirectory()) fail("output root parent must be a directory inside the project root");
  return path;
}

function run(command, arguments_) {
  const result = spawnSync(command, arguments_, { encoding: "utf8", maxBuffer: 128 * 1024 * 1024, timeout: 30_000, killSignal: "SIGKILL" });
  if (result.error) fail(`${basename(command)} failed to start: ${result.error.message}`);
  if (result.status !== 0) fail(`${basename(command)} failed (${result.status}): ${(result.stderr || result.stdout).trim()}`);
  return { stdout: result.stdout, stderr: result.stderr };
}

function parseJSON(value, label) {
  try { return JSON.parse(value); }
  catch (error) {
    if (error instanceof SyntaxError) fail(`${label} did not return valid JSON`);
    throw error;
  }
}

function fixtureIdentity(path, format) {
  const hash = sha256(path);
  const fixture = parseJSON(readFileSync(path, "utf8"), "fixture");
  const corpus = parseJSON(readFileSync(corpusPath, "utf8"), "compatibility corpus");
  const catalogEntry = corpus.fixtures?.find((entry) => entry.projectHash === hash);
  if (!catalogEntry || !catalogEntry.formats?.includes(format)) fail("fixture is not a frozen compatibility corpus entry for the requested format");
  if (!Array.isArray(fixture.elements) || fixture.elements.length === 0) fail("fixture must contain authored elements");
  const elements = [...fixture.elements].sort((left, right) => left.order - right.order);
  const ids = new Set(), orders = new Set();
  for (const element of elements) {
    if (typeof element.elementID !== "string" || !element.elementID || typeof element.text !== "string" || !element.text || !Number.isInteger(element.order)) fail("fixture element identity, text, and order are required");
    if (ids.has(element.elementID) || orders.has(element.order)) fail("fixture element IDs and orders must be unique");
    ids.add(element.elementID);
    orders.add(element.order);
  }
  return { fixtureID: catalogEntry.id, fixtureHash: hash, elements };
}

function orderedMatches(elements, text) {
  const matches = new Map();
  let cursor = 0;
  for (const element of elements) {
    const start = text.indexOf(element.text, cursor);
    if (start < 0) continue;
    matches.set(element.elementID, { start, end: start + element.text.length });
    cursor = start + element.text.length;
  }
  return matches;
}

function collectTextRuns(node, target) {
  if (node?.type === "TextRun" && typeof node.text === "string") target.push({ text: node.text, bbox: node.bbox });
  if (Array.isArray(node?.children)) for (const child of node.children) collectTextRuns(child, target);
}

function renderProjection(trees) {
  let text = "";
  const segments = [], pageTexts = [];
  for (let pageIndex = 0; pageIndex < trees.length; pageIndex += 1) {
    if (pageIndex > 0) text += "\n";
    const runs = [];
    collectTextRuns(trees[pageIndex], runs);
    const pageStart = text.length;
    for (const run of runs) {
      const start = text.length;
      text += run.text;
      const bbox = run.bbox;
      const bounded = [bbox?.x, bbox?.y, bbox?.w, bbox?.h].every(Number.isFinite) && bbox.w > 0 && bbox.h > 0;
      if (run.text.length > 0) segments.push({ start, end: text.length, bounded });
    }
    pageTexts.push(text.slice(pageStart));
  }
  return { text, segments, pageTexts };
}

function hasCompleteBounds(match, segments) {
  let cursor = match.start;
  for (const segment of segments) {
    if (segment.end <= cursor || segment.start >= match.end) continue;
    if (segment.start > cursor || !segment.bounded) return false;
    cursor = Math.min(match.end, segment.end);
    if (cursor === match.end) return true;
  }
  return false;
}

function filesUnder(root, prefix = "") {
  const files = [];
  for (const entry of readdirSync(join(root, prefix), { withFileTypes: true })) {
    const path = join(prefix, entry.name);
    if (entry.isDirectory()) files.push(...filesUnder(root, path));
    else if (entry.isFile()) files.push(path.split(sep).join("/"));
  }
  return files.sort();
}

function environment(info) {
  const fontsJSON = parseJSON(run("/usr/sbin/system_profiler", ["SPFontsDataType", "-json"]).stdout, "system font inventory");
  const requested = Array.isArray(info.fonts) ? info.fonts : [];
  const installed = [];
  for (const file of fontsJSON.SPFontsDataType ?? []) {
    for (const face of file.typefaces ?? []) {
      const canonicalName = typeof face.unique === "string" ? face.unique.split(";")[0].trim() : "";
      if (requested.some((font) => canonicalName.startsWith(`${font} `)) && face.enabled === "yes" && face.valid === "yes") installed.push({ family: face.family, fullName: canonicalName, localizedFullName: face.fullname, postScriptName: face._name, style: face.style, version: face.version, path: file.path });
    }
  }
  const fontNames = [...new Set(installed.map((face) => face.fullName).filter(Boolean))].sort();
  if (requested.length === 0 || fontNames.length === 0) fail("requested document fonts could not be proven installed");
  return { osVersion: `macOS ${run("/usr/bin/sw_vers", ["-productVersion"]).stdout.trim()}`, osBuild: run("/usr/bin/sw_vers", ["-buildVersion"]).stdout.trim(), architecture: process.arch, requestedDocumentFonts: requested, installedMatchingFonts: installed, fontNames, networkAccess: "not-requested-local-file-cli-only", gui: "not-used" };
}

function evidenceEntries(outputRoot, paths) {
  return paths.sort().map((path) => ({ path, sha256: sha256(join(outputRoot, path)), sizeBytes: statSync(join(outputRoot, path)).size }));
}

function verifyRhwp() {
  accessSync(rhwpPath, constants.X_OK);
  const hash = sha256(rhwpPath);
  if (hash !== requiredRhwpHash) fail("bundled rhwp SHA-256 mismatch");
  const versionOutput = run(rhwpPath, ["--version"]).stdout.trim();
  const version = versionOutput.match(/rhwp\s+v?([0-9.]+)/u)?.[1];
  if (!version) fail("bundled rhwp version is unavailable");
  return { hash, version, versionOutput };
}

function main() {
  const raw = parseArguments(process.argv.slice(2));
  const outputRoot = confinedOutput(raw.outputRoot);
  if (existsSync(outputRoot)) fail("output root already exists");
  const artifact = confinedFile(raw.artifact, "artifact"), fixture = confinedFile(raw.fixture, "fixture");
  if (extname(artifact).toLowerCase() !== `.${raw.format}`) fail("artifact extension does not match --format");
  const artifactBefore = sha256(artifact), fixtureBefore = sha256(fixture);
  const identity = fixtureIdentity(fixture, raw.format);
  const tool = verifyRhwp();
  mkdirSync(outputRoot);
  let published = false;
  try {
    mkdirSync(join(outputRoot, "svg"));
    mkdirSync(join(outputRoot, "render-tree"));
    const commands = [
      { name: "info", arguments: ["info", artifact, "--json"], evidence: "info.json" },
      { name: "export-text", arguments: ["export-text", artifact, "--json"], evidence: "export-text.json" },
      { name: "export-svg", arguments: ["export-svg", artifact, "-o", join(outputRoot, "svg"), "--font-style", "--json"], evidence: "export-svg-manifest.json" },
      { name: "export-render-tree", arguments: ["export-render-tree", artifact, "-o", join(outputRoot, "render-tree")], evidence: "render-tree.log" },
    ];
    const results = commands.map((command) => run(rhwpPath, command.arguments));
    for (let index = 0; index < commands.length; index += 1) writeFileSync(join(outputRoot, commands[index].evidence), `${results[index].stdout}${results[index].stderr}`);
    const info = parseJSON(results[0].stdout, "rhwp info"), textResult = parseJSON(results[1].stdout, "rhwp export-text"), svgResult = parseJSON(results[2].stdout, "rhwp export-svg");
    const treePaths = filesUnder(join(outputRoot, "render-tree")).filter((path) => path.endsWith(".json"));
    const trees = treePaths.map((path) => parseJSON(readFileSync(join(outputRoot, "render-tree", path), "utf8"), `render tree ${path}`));
    const extractionText = [...textResult.pages].sort((left, right) => left.page - right.page).map((page) => page.text).join("\n");
    const extracted = orderedMatches(identity.elements, extractionText), projection = renderProjection(trees), rendered = orderedMatches(identity.elements, projection.text);
    const bounded = identity.elements.filter((element) => extracted.has(element.elementID) && rendered.has(element.elementID) && hasCompleteBounds(rendered.get(element.elementID), projection.segments));
    const missing = identity.elements.filter((element) => !extracted.has(element.elementID) || !rendered.has(element.elementID)).map((element) => element.elementID);
    const pageCountSources = { info: info.pageCount, text: textResult.pageCount, svg: svgResult.pageCount, renderTree: trees.length };
    const pageCountsAgree = new Set(Object.values(pageCountSources)).size === 1 && info.pageCount > 0;
    const unexpectedBlankPageNumbers = projection.pageTexts.map((text, index) => text.trim() ? null : index + 1).filter((page) => page !== null);
    const analysis = {
      verdict: pageCountsAgree && missing.length === 0 && bounded.length === identity.elements.length && unexpectedBlankPageNumbers.length === 0 ? "pass" : "fail",
      authoredElementCount: identity.elements.length,
      authoredElementIDs: identity.elements.map((element) => element.elementID),
      extractedElementIDs: identity.elements.filter((element) => extracted.has(element.elementID)).map((element) => element.elementID),
      renderedElementIDs: identity.elements.filter((element) => rendered.has(element.elementID)).map((element) => element.elementID),
      boundedElementIDs: bounded.map((element) => element.elementID),
      missingAuthoredElementIDs: missing,
      textBoundsCoverage: bounded.length / identity.elements.length,
      unexpectedBlankPageNumbers,
      pageCountSources,
    };
    const actualEnvironment = environment(info);
    writeJSON(join(outputRoot, "environment.json"), actualEnvironment);
    writeJSON(join(outputRoot, "analysis.json"), analysis);
    const artifactAfter = sha256(artifact), fixtureAfter = sha256(fixture);
    if (artifactAfter !== artifactBefore || fixtureAfter !== fixtureBefore) fail("artifact or fixture changed during observation");
    const evidencePaths = ["info.json", "export-text.json", "export-svg-manifest.json", "render-tree.log", "environment.json", "analysis.json", ...filesUnder(join(outputRoot, "svg")).map((path) => `svg/${path}`), ...treePaths.map((path) => `render-tree/${path}`)];
    const manifest = {
      schemaVersion: 1,
      tool: { id: "edwardkim-rhwp-local-visual-observer", path: projectPath(rhwpPath), sha256: tool.hash, version: tool.version, versionOutput: tool.versionOutput, commands },
      inputs: { artifact: { path: projectPath(artifact), pristineBeforeSha256: artifactBefore, pristineAfterSha256: artifactAfter }, fixture: { path: projectPath(fixture), pristineBeforeSha256: fixtureBefore, pristineAfterSha256: fixtureAfter } },
      fixture: { fixtureID: identity.fixtureID, orderedElements: identity.elements.map(({ elementID, order, text }) => ({ elementID, order, text })) },
      environment: actualEnvironment,
      analysis,
      evidence: evidenceEntries(outputRoot, evidencePaths),
    };
    writeJSON(join(outputRoot, "evidence-manifest.json"), manifest);
    const observation = {
      observationID: `observation-ac07-rhwp-${raw.format}-${randomUUID()}`,
      toolID: "edwardkim-rhwp-local-visual-observer", clientName: "rhwp local layout/render engine",
      clientVersion: tool.version, clientBuild: tool.hash,
      osVersion: actualEnvironment.osVersion, osBuild: actualEnvironment.osBuild, fonts: actualEnvironment.fontNames,
      timestamp: new Date().toISOString(), fixtureID: identity.fixtureID, fixtureHash: identity.fixtureHash,
      format: raw.format, artifactHash: artifactBefore,
      expectedPageCount: info.pageCount, observedPageCount: svgResult.pageCount,
      missingAuthoredElementIDs: missing, unexpectedBlankPageNumbers, textBoundsCoverage: analysis.textBoundsCoverage,
      evidencePath: "evidence-manifest.json", evidenceHash: sha256(join(outputRoot, "evidence-manifest.json")),
    };
    writeJSON(join(outputRoot, "visual-observation.json"), observation);
    const sums = evidenceEntries(outputRoot, [...evidencePaths, "evidence-manifest.json", "visual-observation.json"]).map((entry) => `${entry.sha256.slice(7)}  ${entry.path}`).join("\n");
    writeFileSync(join(outputRoot, "SHA256SUMS"), `${sums}\n`);
    published = true;
    process.stdout.write(`${JSON.stringify(observation)}\n`);
    if (analysis.verdict !== "pass") process.exitCode = 1;
  } finally {
    if (!published) rmSync(outputRoot, { recursive: true, force: true });
  }
}

try { main(); }
catch (error) {
  if (!(error instanceof Error)) throw error;
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
}
