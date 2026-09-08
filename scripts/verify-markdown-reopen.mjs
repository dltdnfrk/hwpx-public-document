#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  accessSync,
  constants,
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const projectRoot = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const requiredPandocVersion = "3.9.0.2";
const requiredArguments = new Set(["--artifact", "--fixture", "--output-root"]);

function fail(message) {
  throw new Error(message);
}

function parseArguments(argv) {
  if (argv.length !== 6) fail("usage: verify-markdown-reopen.mjs --artifact PATH --fixture PATH --output-root PATH");
  const parsed = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!requiredArguments.has(key) || parsed.has(key) || !value) fail(`invalid argument: ${key ?? "missing"}`);
    parsed.set(key, value);
  }
  for (const key of requiredArguments) if (!parsed.has(key)) fail(`missing argument: ${key}`);
  return Object.fromEntries([...parsed].map(([key, value]) => [key.slice(2), value]));
}

function isConfined(path) {
  const delta = relative(projectRoot, path);
  return delta !== "" && !delta.startsWith(`..${sep}`) && delta !== ".." && !isAbsolute(delta);
}

function confinedInput(rawPath, label) {
  const physical = realpathSync(resolve(projectRoot, rawPath));
  if (!isConfined(physical) || !statSync(physical).isFile()) fail(`${label} must be a file inside the project root`);
  return physical;
}

function confinedOutput(rawPath) {
  const target = resolve(projectRoot, rawPath);
  if (!isConfined(target)) fail("output root must be inside the project root");
  let ancestor = dirname(target);
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  if (!isConfined(realpathSync(ancestor))) fail("output root resolves outside the project root");
  return target;
}

function projectPath(path) {
  return relative(projectRoot, path).split(sep).join("/");
}

function sha256(path) {
  return `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
}

function executable(name, extraCandidates = []) {
  const candidates = [...extraCandidates];
  for (const directory of (process.env.PATH ?? "").split(":").filter(Boolean)) candidates.push(join(directory, name));
  for (const candidate of candidates) {
    try {
      accessSync(candidate, constants.X_OK);
      return realpathSync(candidate);
    } catch {}
  }
  fail(`required executable is unavailable: ${name}`);
}

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", maxBuffer: 128 * 1024 * 1024, timeout: 30_000, killSignal: "SIGKILL" });
  if (result.error) fail(`${basename(command)} failed to start: ${result.error.message}`);
  if (result.status !== 0) fail(`${basename(command)} failed (${result.status}): ${(result.stderr || result.stdout).trim()}`);
  return result.stdout;
}

function playwrightBrowserExecutable(chromium) {
  const expected = chromium.executablePath();
  if (existsSync(expected)) return realpathSync(expected);
  const cacheRoot = join(os.homedir(), "Library", "Caches", "ms-playwright");
  const expectedRevision = Number(/chromium-(\d+)/u.exec(expected)?.[1] ?? 0);
  if (existsSync(cacheRoot)) {
    const architecture = os.arch() === "arm64" ? "mac-arm64" : "mac";
    const candidates = readdirSync(cacheRoot)
      .map((name) => ({
        executable: join(cacheRoot, name, `chrome-headless-shell-${architecture}`, "chrome-headless-shell"),
        revision: Number(/^chromium_headless_shell-(\d+)$/u.exec(name)?.[1] ?? Number.MAX_SAFE_INTEGER),
      }))
      .filter((candidate) => Number.isFinite(candidate.revision) && existsSync(candidate.executable))
      .sort((left, right) => Math.abs(left.revision - expectedRevision) - Math.abs(right.revision - expectedRevision));
    if (candidates.length > 0) return realpathSync(candidates[0].executable);
  }
  return executable("google-chrome", [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ]);
}

async function renderPage(htmlPath, screenshotPath) {
  const harnessRoot = process.env.GENOFFICE_DEPENDENCY_ROOT
    ? resolve(projectRoot, process.env.GENOFFICE_DEPENDENCY_ROOT)
    : join(projectRoot, ".omo", "ac08-browser");
  const harnessPackage = join(harnessRoot, "package.json");
  if (!existsSync(harnessPackage)) fail("installed Playwright harness is unavailable");
  const requireFromHarness = createRequire(harnessPackage);
  const { chromium } = requireFromHarness("playwright-core");
  const playwrightVersion = requireFromHarness("playwright-core/package.json").version;
  const browserExecutable = playwrightBrowserExecutable(chromium);
  const browser = await chromium.launch({
    executablePath: browserExecutable,
    headless: true,
    timeout: 30_000,
    args: ["--disable-background-networking", "--disable-component-update", "--disable-sync", "--no-first-run", "--disable-default-apps", "--metrics-recording-only", "--safebrowsing-disable-auto-update", "--host-resolver-rules=MAP * ~NOTFOUND", "--proxy-server=direct://", "--proxy-bypass-list=*"],
  });
  const networkRequests = [];
  try {
    const context = await browser.newContext({ viewport: { width: 960, height: 1240 }, deviceScaleFactor: 1, locale: "ko-KR" });
    await context.route(/^https?:\/\//u, (route) => {
      networkRequests.push(route.request().url());
      return route.abort("blockedbyclient");
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15_000);
    page.setDefaultNavigationTimeout(15_000);
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready.then(() => true));
    await page.screenshot({ path: screenshotPath, fullPage: false });
    await context.close();
  } finally {
    await browser.close();
  }
  if (networkRequests.length !== 0) fail(`render attempted network access: ${networkRequests.join(", ")}`);
  return { browserExecutable, playwrightVersion };
}

function fixtureExpectation(path) {
  const fixture = JSON.parse(readFileSync(path, "utf8"));
  if (!Array.isArray(fixture.elements) || typeof fixture.title !== "string") fail("fixture lacks authored elements or title");
  const ordered = [...fixture.elements].sort((left, right) => left.order - right.order);
  const expected = ordered.filter((element) => typeof element.text === "string" && /[\uac00-\ud7a3]/u.test(element.text));
  if (expected.length === 0 || expected.some((element) => typeof element.elementID !== "string")) fail("fixture lacks Korean authored text identities");
  return { fixture, expected };
}

function exactTextObservation(plainText, expected) {
  const expectedText = expected.map((element) => element.text);
  const observedText = [];
  let cursor = 0;
  for (const text of expectedText) {
    const position = plainText.indexOf(text, cursor);
    if (position < 0) fail(`expected Korean text is missing or out of order: ${text}`);
    observedText.push(text);
    cursor = position + text.length;
  }
  for (const text of new Set(expectedText)) {
    const expectedCount = expectedText.filter((candidate) => candidate === text).length;
    const observedCount = plainText.split(text).length - 1;
    if (observedCount !== expectedCount) fail(`expected Korean text count mismatch: ${text}`);
  }
  return observedText;
}

function escapeHTML(value) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function pageHTML(fragment, title, font) {
  return `<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escapeHTML(title)}</title><style>\nhtml{background:#d9dde3;color:#17191c}body{margin:0;padding:24px}main.page{box-sizing:border-box;width:794px;min-height:1123px;margin:0 auto;padding:76px 72px;background:#fff;box-shadow:0 3px 18px #0003;font-family:"${escapeHTML(font)}",sans-serif;font-size:15px;line-height:1.8;overflow-wrap:break-word}h1{margin:0 0 32px;font-size:26px;line-height:1.35}p{margin:0 0 18px}strong{font-weight:700}table{width:100%;border-collapse:collapse}th,td{border:1px solid #8b9097;padding:6px 8px}@media print{html{background:#fff}body{padding:0}main.page{box-shadow:none}}\n</style></head><body><main class="page">${fragment}\n</main></body></html>\n`;
}

function osEnvironment(requestedFonts) {
  const swVers = process.platform === "darwin" ? executable("sw_vers", ["/usr/bin/sw_vers"]) : null;
  const fontMatcher = executable("fc-match", ["/opt/homebrew/bin/fc-match", "/usr/local/bin/fc-match"]);
  return {
    osName: process.platform === "darwin" ? "macOS" : os.type(),
    osVersion: swVers ? run(swVers, ["-productVersion"]).trim() : os.release(),
    osBuild: swVers ? run(swVers, ["-buildVersion"]).trim() : os.release(),
    architecture: os.arch(),
    fonts: requestedFonts.map((font) => ({ requested: font, matched: run(fontMatcher, [font]).trim() })),
  };
}

function evidenceRows(root, paths) {
  return paths.map((path) => ({ path, sha256: sha256(join(root, path)), sizeBytes: statSync(join(root, path)).size }));
}

function writeJSON(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  const artifact = confinedInput(args.artifact, "artifact");
  const fixturePath = confinedInput(args.fixture, "fixture");
  const outputRoot = confinedOutput(args["output-root"]);
  if (existsSync(outputRoot)) fail(`output root already exists: ${projectPath(outputRoot)}`);
  const outputParent = dirname(outputRoot);
  mkdirSync(outputParent, { recursive: true });
  const staging = mkdtempSync(join(outputParent, ".markdown-reopen-"));
  let published = false;
  try {
    const artifactBefore = sha256(artifact);
    const fixtureBefore = sha256(fixturePath);
    const { fixture, expected } = fixtureExpectation(fixturePath);
    const requestedFonts = [...new Set(fixture.styles.map((style) => style.properties?.font).filter((font) => typeof font === "string"))];
    const font = requestedFonts[0] ?? "Apple SD Gothic Neo";
    const pandoc = executable("pandoc", ["/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc"]);
    const pandocVersion = run(pandoc, ["--version"]).split("\n")[0].replace(/^pandoc /u, "").trim();
    if (pandocVersion !== requiredPandocVersion) fail(`Pandoc ${requiredPandocVersion} required, found ${pandocVersion}`);
    copyFileSync(artifact, join(staging, "input.md"));
    const fragment = run(pandoc, ["--from=commonmark", "--to=html5", "--wrap=none", artifact]);
    const plainText = run(pandoc, ["--from=commonmark", "--to=plain", "--wrap=none", artifact]);
    const observedText = exactTextObservation(plainText, expected);
    writeFileSync(join(staging, "pandoc-rendered.html"), fragment, "utf8");
    writeFileSync(join(staging, "rendered.txt"), plainText, "utf8");
    writeFileSync(join(staging, "rendered.html"), pageHTML(fragment, fixture.title, font), "utf8");
    const { browserExecutable, playwrightVersion } = await renderPage(join(staging, "rendered.html"), join(staging, "commonmark-render.png"));
    if (sha256(artifact) !== artifactBefore || sha256(fixturePath) !== fixtureBefore) fail("input changed during verification");
    const completedAt = new Date().toISOString();
    const environment = osEnvironment(requestedFonts);
    const screenshotHash = sha256(join(staging, "commonmark-render.png"));
    const blocker = {
      schemaVersion: 1, operation: "approved-rendering", verdict: "blocked", selfApprovalPermitted: false,
      approval: { authorityID: "public-document-rendering-authority", status: "pending-external-authority", authorityReceipt: null, approvedAt: null },
      bindings: { artifactSha256: artifactBefore, fixtureSha256: fixtureBefore, screenshotSha256: screenshotHash },
    };
    writeJSON(join(staging, "approved-rendering-blocker.json"), blocker);
    const deterministicPaths = ["input.md", "pandoc-rendered.html", "rendered.txt", "rendered.html", "commonmark-render.png", "approved-rendering-blocker.json"];
    writeFileSync(join(staging, "SHA256SUMS"), deterministicPaths.map((path) => `${sha256(join(staging, path)).slice(7)}  ${path}`).join("\n") + "\n", "utf8");
    const evidence = evidenceRows(staging, [...deterministicPaths, "SHA256SUMS"]);
    const blockerEvidence = evidence.find((row) => row.path === "approved-rendering-blocker.json");
    const receipt = {
      schemaVersion: 1, completedAt, localVerdict: "pass", overallVerdict: "blocked",
      inputs: {
        artifact: { path: projectPath(artifact), pristineBeforeSha256: artifactBefore, pristineAfterSha256: sha256(artifact), inputCopyPath: "input.md", inputCopySha256: sha256(join(staging, "input.md")) },
        fixture: { path: projectPath(fixturePath), pristineBeforeSha256: fixtureBefore, pristineAfterSha256: sha256(fixturePath) },
      },
      tool: { id: "public-document-markdown-reopen", path: projectPath(fileURLToPath(import.meta.url)), sha256: sha256(fileURLToPath(import.meta.url)), networkAccess: "disabled-local-file-only" },
      environment,
      commonMarkObservation: {
        observationID: `commonmark-${artifactBefore.slice(7, 19)}`, operation: "commonmark-validate", clientID: "pandoc-commonmark", clientName: "Pandoc CommonMark reader", clientVersion: pandocVersion, clientBuild: `pandoc-${pandocVersion}`, executableSha256: sha256(pandoc), timestamp: completedAt, opened: true, interactionSurface: "non-interactive-cli-reader", extensionDialogCapable: false, extensionWarningCount: 0, expectedTextCount: expected.length, observedTextCount: observedText.length, expectedTextOrder: expected.map((element) => element.text), observedTextOrder: observedText, evidencePath: "rendered.txt", evidenceSha256: sha256(join(staging, "rendered.txt")), osVersion: environment.osVersion, osBuild: environment.osBuild, fonts: environment.fonts,
      },
      renderCandidate: {
        operation: "approved-rendering", verdict: "candidate", approvalStatus: "pending-external-authority", renderer: "Playwright bundled Chromium headless", rendererVersion: run(browserExecutable, ["--version"]).trim(), playwrightVersion, rendererExecutableSha256: sha256(browserExecutable), timestamp: completedAt, screenshotPath: "commonmark-render.png", screenshotSha256: screenshotHash, expectedTextCount: expected.length, observedTextCount: observedText.length, missingAuthoredElementIDs: [], networkAccess: "disabled-local-file-only",
      },
      externalBlockers: [{ operation: "approved-rendering", status: "pending-external-authority", verdict: "blocked", evidencePath: blockerEvidence.path, evidenceSha256: blockerEvidence.sha256 }],
      evidence,
    };
    writeJSON(join(staging, "receipt.json"), receipt);
    renameSync(staging, outputRoot);
    published = true;
    process.stdout.write(`${JSON.stringify(receipt)}\n`);
  } finally {
    if (!published) rmSync(staging, { recursive: true, force: true });
  }
}

try {
  await main();
} catch (error) {
  if (!(error instanceof Error)) throw error;
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
}
