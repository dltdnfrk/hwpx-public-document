import { createHash, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { createRequire } from "node:module";

const approvedCommit = "d8305ff2dc152593a1ec5639d77e6860c6a512bd";
const approvedTree = "41cccf8c72120f971fca4f37fe257ffc4b1d8b99";
const approvedRepository = "https://github.com/genspark-ai/genoffice.git";
const approvedFixtureHash = "sha256:d4f4d8d4fa44db5db7325960c75d628ce780aa50128bddbf31b59a524823e034";
const approvedBuildHashes = new Map([
  ["apps/docs/out/main/index.js", "sha256:eb0a19dd2c8924d9e32d6892eee6b540431dadcb284ddf88ab41b9df0cad9794"], ["apps/docs/out/preload/index.js", "sha256:8f4383c06099f4fef6fe591c00254c0fa07ee4a4ec081fb6948ebf42c8ca7c0a"],
  ["apps/docs/out/renderer/index.html", "sha256:f2e179da1231100613d6bf258faf8570aede6a753c2900af9a5cce2492530ed1"], ["apps/shell/out/main/index.js", "sha256:95517fb3b523add4f2eac3f5f4038bd9e8ac783f617770e302e538021a7a4c3e"],
  ["apps/shell/out/preload/index.js", "sha256:2f827cf1673382ee854cfae8be21714dd9fcf3682f3033cfc90099ebfab70e2d"], ["apps/shell/out/renderer/index.html", "sha256:0de712520bbefb31065d70c02343b6bb508da78797eee2df54988aa267cc4928"],
]);
const approvedSourceHashes = new Map([
  ["apps/docs/src/renderer/App.tsx", "sha256:0cd748ce1b259c52a051f9976f785119e03f9dd6358b0f3136d3c75bf136b155"],
  ["apps/shell/src/main/index.ts", "sha256:11e8423d136396febb087d71bf952b3c6ccd0e22b03fa4723b96dca167c3e233"],
]);
const hostResolverRule = "MAP * ~NOTFOUND, EXCLUDE localhost";

class VerificationError extends Error {}

const digest = (path) => `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
const digestText = (value) => `sha256:${createHash("sha256").update(value).digest("hex")}`;
const git = (root, ...arguments_) => execFileSync("git", ["-C", root, ...arguments_], { encoding: "utf8" }).trim();

function parseArguments(arguments_) {
  const values = new Map();
  for (let index = 0; index < arguments_.length; index += 2) {
    const option = arguments_[index];
    const value = arguments_[index + 1];
    if (!option?.startsWith("--") || !value || value.startsWith("--")) {
      throw new VerificationError(`missing value for option: ${option ?? "<none>"}`);
    }
    if (!new Set(["--genoffice-root", "--artifact", "--fixture", "--output-root"]).has(option)) {
      throw new VerificationError(`unsupported option: ${option}`);
    }
    if (values.has(option)) throw new VerificationError(`duplicate option: ${option}`);
    values.set(option, value);
  }
  for (const option of ["--genoffice-root", "--artifact", "--fixture", "--output-root"]) {
    if (!values.has(option)) throw new VerificationError(`missing required option: ${option}`);
  }
  return { genofficeRoot: resolve(values.get("--genoffice-root")), artifact: resolve(values.get("--artifact")), fixture: resolve(values.get("--fixture")), outputRoot: resolve(values.get("--output-root")) };
}

function verifyInputs(input) {
  if (existsSync(input.outputRoot)) throw new VerificationError("output root already exists");
  for (const [label, path] of [["GenOffice root", input.genofficeRoot], ["artifact", input.artifact], ["fixture", input.fixture]]) {
    if (!existsSync(path)) throw new VerificationError(`${label} does not exist: ${path}`);
  }
  if (extname(input.artifact).toLowerCase() !== ".docx") {
    throw new VerificationError("artifact must have the .docx extension");
  }
  if (readFileSync(input.artifact).subarray(0, 2).toString("binary") !== "PK") {
    throw new VerificationError("artifact is not a DOCX ZIP package");
  }
  const fixtureHash = digest(input.fixture);
  if (fixtureHash !== approvedFixtureHash) throw new VerificationError("fixture identity is not approved");
  const head = git(input.genofficeRoot, "rev-parse", "HEAD");
  const tree = git(input.genofficeRoot, "rev-parse", "HEAD^{tree}");
  const origin = git(input.genofficeRoot, "remote", "get-url", "origin");
  const trackedStatus = git(input.genofficeRoot, "status", "--porcelain", "--untracked-files=no");
  if (head !== approvedCommit || tree !== approvedTree || origin !== approvedRepository || trackedStatus !== "") {
    throw new VerificationError("GenOffice checkout is not the clean approved source identity");
  }
  const verifiedHashes = (approved, label) => Object.fromEntries([...approved].map(([path, expected]) => {
    const observed = digest(resolve(input.genofficeRoot, path));
    if (observed !== expected) throw new VerificationError(`GenOffice ${label} hash mismatch: ${path}`);
    return [path, observed];
  }));
  const buildHashes = verifiedHashes(approvedBuildHashes, "build");
  const sourceHashes = verifiedHashes(approvedSourceHashes, "source");
  return { fixtureHash, head, tree, origin, buildHashes, sourceHashes };
}

function isolatedEnvironment(runRoot) {
  const environment = Object.fromEntries(Object.entries(process.env).filter(([, value]) => value !== undefined));
  const removedCredentials = [];
  for (const name of Object.keys(environment)) {
    if (/(?:API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|COOKIE|SESSION)/i.test(name) || /^(?:GSK|GENSPARK)_/i.test(name)) {
      removedCredentials.push(name);
      delete environment[name];
    }
    if (/^(?:HTTP|HTTPS|ALL|NO)_PROXY$/i.test(name)) delete environment[name];
  }
  Object.assign(environment, {
    GENOFFICE_USER_DATA: join(runRoot, "user-data"), GENOFFICE_AUTH_DIR: join(runRoot, "auth"),
    GENOFFICE_LANG: "en", AI_SEARCH_DISABLE_GSK: "1", GSK_API_KEY: "", GSK_BASE_URL: "",
    GSK_CLI_PATH: "", SERPER_API_KEY: "", GENOFFICE_CLOUD_SLIDE: "0",
    GENOFFICE_CLOUD_SLIDE_TIER: "", GENOFFICE_UPDATE_URL: "",
    HTTP_PROXY: "", HTTPS_PROXY: "", ALL_PROXY: "", NO_PROXY: "*",
  });
  mkdirSync(environment.GENOFFICE_USER_DATA);
  mkdirSync(environment.GENOFFICE_AUTH_DIR);
  return { environment, removedCredentials: removedCredentials.sort() };
}

async function exitApplication(application, exitCode) {
  const child = application.process();
  if (child.exitCode !== null || child.signalCode !== null) return;
  const closed = new Promise((resolveClosed) => application.once("close", resolveClosed));
  await application.evaluate(({ app }, code) => {
    setImmediate(() => app.exit(code));
  }, exitCode);
  await closed;
}

async function runObservation(input, identity) {
  mkdirSync(input.outputRoot);
  const runRoot = mkdtempSync(join(tmpdir(), "genoffice-docx-reopen-"));
  const { environment, removedCredentials } = isolatedEnvironment(runRoot);
  const executable = resolve(input.genofficeRoot, "node_modules/electron/dist/Electron.app/Contents/MacOS/Electron");
  const executableHash = digest(executable);
  const package_ = JSON.parse(readFileSync(resolve(input.genofficeRoot, "apps/docs/package.json"), "utf8"));
  const fixtureData = JSON.parse(readFileSync(input.fixture, "utf8"));
  const expectedTexts = fixtureData.elements.map((element) => element.text).filter((text) => /[\uac00-\ud7a3]/u.test(text));
  if (expectedTexts.length === 0) throw new VerificationError("fixture has no expected Korean text");
  const requireFromGenOffice = createRequire(resolve(input.genofficeRoot, "package.json"));
  const { _electron } = requireFromGenOffice("playwright-core");
  const startedAt = new Date();
  const dialogs = [];
  const pageErrors = [];
  const consoleErrors = [];
  const externalRequests = [];
  const instrumented = new WeakSet();
  let application = null;
  try {
    application = await _electron.launch({
      executablePath: executable,
      args: [`--host-resolver-rules=${hostResolverRule}`, resolve(input.genofficeRoot, "apps/shell"), input.artifact],
      cwd: input.genofficeRoot,
      env: environment,
      offline: true,
      recordVideo: { dir: join(runRoot, "video"), size: { width: 1360, height: 900 } },
      timeout: 30000,
    });
    const instrument = (page) => {
      if (instrumented.has(page)) return;
      instrumented.add(page);
      page.on("dialog", (dialog) => { dialogs.push(dialog.message()); void dialog.dismiss(); });
      page.on("pageerror", (error) => pageErrors.push(error.message));
      page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
      page.on("request", (request) => { if (/^https?:/u.test(request.url())) externalRequests.push(request.url()); });
    };
    application.on("window", instrument);
    application.windows().forEach(instrument);
    const runtimeIsolation = await application.evaluate(({ app }, expected) => {
      const credentialsPresent = expected.credentialNames.filter((name) => Boolean(process.env[name]));
      const gensparkDisabled = process.env.AI_SEARCH_DISABLE_GSK === "1" && !process.env.GSK_API_KEY && !process.env.GSK_BASE_URL && !process.env.GSK_CLI_PATH && !process.env.SERPER_API_KEY && process.env.GENOFFICE_CLOUD_SLIDE === "0";
      const proxiesDisabled = !process.env.HTTP_PROXY && !process.env.HTTPS_PROXY && !process.env.ALL_PROXY && process.env.NO_PROXY === "*";
      const freshPaths = app.getPath("userData") === expected.userData && process.env.GENOFFICE_AUTH_DIR === expected.auth;
      return { credentialsPresent, gensparkDisabled, proxiesDisabled, freshPaths, hostResolverApplied: process.argv.includes(expected.hostResolverArgument) };
    }, { credentialNames: [...new Set([...removedCredentials, "GSK_API_KEY", "GSK_BASE_URL", "GSK_CLI_PATH", "SERPER_API_KEY"])], userData: environment.GENOFFICE_USER_DATA, auth: environment.GENOFFICE_AUTH_DIR, hostResolverArgument: `--host-resolver-rules=${hostResolverRule}` });
    let docsPage = application.windows().find((page) => page.url().includes("/apps/docs/out/renderer/index.html"));
    docsPage ??= await application.waitForEvent("window", {
      predicate: (page) => page.url().includes("/apps/docs/out/renderer/index.html"),
      timeout: 30000,
    });
    instrument(docsPage);
    await docsPage.waitForSelector(".ProseMirror", { state: "visible", timeout: 30000 });
    await docsPage.waitForFunction(
      ({ texts }) => texts.every((text) => document.body.innerText.includes(text)) && /Page \d+ of \d+/u.test(document.body.innerText),
      { texts: expectedTexts },
      { timeout: 30000 },
    );
    const dom = await docsPage.evaluate((texts) => {
      const bodyText = document.body.innerText;
      const status = bodyText.match(/Page (\d+) of (\d+)/u)?.[0] ?? null;
      const pageCount = document.querySelectorAll(".doc-page").length;
      const rendered = texts.map((text) => {
        const node = [...document.querySelectorAll(".ProseMirror p, .ProseMirror h1, .ProseMirror h2, .ProseMirror h3")]
          .find((candidate) => candidate.textContent?.trim() === text);
        if (!node) return { text, visible: false };
        const box = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return { text, visible: box.width > 0 && box.height > 0 && style.display !== "none" && style.visibility === "visible", box: { x: box.x, y: box.y, width: box.width, height: box.height }, fontFamily: style.fontFamily, fontSize: style.fontSize };
      });
      const warningTexts = [...document.querySelectorAll('[role="alert"], [role="dialog"], dialog')]
        .map((node) => node.textContent?.trim() ?? "")
        .filter((text) => /(unsupported|not supported|지원되지 않|확장자)/iu.test(text));
      const editor = document.querySelector(".ProseMirror")?.getBoundingClientRect();
      return { status, pageCount, rendered, warningTexts, editorVisible: Boolean(editor?.width && editor?.height) };
    }, expectedTexts);
    const shellPage = application.windows().find((page) => page.url().includes("/apps/shell/out/renderer/index.html"));
    const shellText = shellPage ? await shellPage.locator("body").innerText() : "";
    const extensionWarnings = dialogs.filter((text) => /(unsupported|not supported|지원되지 않|확장자)/iu.test(text)).length + dom.warningTexts.length;
    const assertions = [
      { id: "expected-korean-text", expected: expectedTexts, observed: dom.rendered.filter((item) => item.visible).map((item) => item.text), passed: dom.rendered.every((item) => item.visible) },
      { id: "page-count", expected: 1, observed: dom.pageCount, passed: dom.pageCount === 1 && dom.status === "Page 1 of 1" },
      { id: "extension-warning-count", expected: 0, observed: extensionWarnings, passed: extensionWarnings === 0 },
      { id: "editor-visible", expected: true, observed: dom.editorVisible, passed: dom.editorVisible },
      { id: "shell-tab", expected: basename(input.artifact), observed: shellText.includes(basename(input.artifact)), passed: shellText.includes(basename(input.artifact)) },
      { id: "runtime-errors", expected: [], observed: [...pageErrors, ...consoleErrors], passed: pageErrors.length === 0 && consoleErrors.length === 0 },
      { id: "runtime-isolation", expected: { credentialsPresent: [], gensparkDisabled: true, proxiesDisabled: true, freshPaths: true, hostResolverApplied: true }, observed: runtimeIsolation, passed: runtimeIsolation.credentialsPresent.length === 0 && runtimeIsolation.gensparkDisabled && runtimeIsolation.proxiesDisabled && runtimeIsolation.freshPaths && runtimeIsolation.hostResolverApplied },
    ];
    const screenshotPath = resolve(input.outputRoot, "genoffice-docx-reopen.png");
    const videoPath = resolve(input.outputRoot, "genoffice-docx-reopen.webm");
    await docsPage.screenshot({ path: screenshotPath });
    const video = docsPage.video(); if (!video) throw new VerificationError("Playwright did not produce a video");
    await docsPage.close({ runBeforeUnload: false }); copyFileSync(await video.path(), videoPath);
    const process_ = application.process();
    await exitApplication(application, 0);
    application = null;
    const trackedStatusAfter = git(input.genofficeRoot, "status", "--porcelain", "--untracked-files=no");
    assertions.push({ id: "tracked-source-clean-after-run", expected: "", observed: trackedStatusAfter, passed: trackedStatusAfter === "" });
    assertions.push({ id: "client-process-exit", expected: { exitCode: 0, signal: null }, observed: { exitCode: process_.exitCode, signal: process_.signalCode }, passed: process_.exitCode === 0 && process_.signalCode === null });
    const artifactHash = digest(input.artifact);
    const evidence = {
      screenshot: { path: basename(screenshotPath), sha256: digest(screenshotPath), byteCount: statSync(screenshotPath).size },
      video: { path: basename(videoPath), sha256: digest(videoPath), byteCount: statSync(videoPath).size },
    };
    assertions.push({ id: "visual-evidence", expected: "non-empty screenshot and video", observed: { screenshotBytes: evidence.screenshot.byteCount, videoBytes: evidence.video.byteCount }, passed: evidence.screenshot.byteCount > 0 && evidence.video.byteCount > 0 });
    const receipt = {
      schemaVersion: 1,
      observationID: `observation-ac07-genoffice-${randomUUID()}`,
      operation: "genoffice-docs-reopen",
      verdict: assertions.every((assertion) => assertion.passed) ? "pass" : "fail",
      startedAt: startedAt.toISOString(),
      completedAt: new Date().toISOString(),
      source: { repository: identity.origin, approvedCommit, verifiedHead: identity.head, treeHash: identity.tree, trackedSourceClean: trackedStatusAfter === "", sourceHashes: identity.sourceHashes },
      client: { clientID: "genoffice-docs", clientName: package_.productName, clientVersion: package_.version, clientBuild: identity.head, electronVersion: package_.build.electronVersion, executablePath: realpathSync(executable), executableHash, builtArtifactHashes: identity.buildHashes, clientBuildSetHash: digestText(JSON.stringify(identity.buildHashes)) },
      isolation: { userData: "fresh temporary directory removed after run", auth: "fresh empty temporary directory removed after run", credentialsRemovedFromParentEnvironment: removedCredentials, runtime: runtimeIsolation, offline: true, hostResolverRule },
      fixture: { fixtureID: "basic-client-interoperability", path: input.fixture, sha256: identity.fixtureHash, expectedTexts, expectedPageCount: 1 },
      artifact: { format: "docx", path: input.artifact, sha256: artifactHash, byteCount: statSync(input.artifact).size },
      observation: { docsPageURL: docsPage.url(), shellPageURL: shellPage?.url() ?? null, pageStatus: dom.status, pageCount: dom.pageCount, renderedTextElements: dom.rendered, extensionWarningCount: extensionWarnings, dialogMessages: dialogs, observedExternalRequestURLs: [...new Set(externalRequests)] },
      process: { pid: process_.pid, exitCode: process_.exitCode, signal: process_.signalCode, pageErrors, consoleErrors, durationMs: Date.now() - startedAt.getTime() },
      rawAssertions: assertions,
      evidence,
      evidenceSetHash: digestText(JSON.stringify({ artifactHash, fixtureHash: identity.fixtureHash, assertions, evidence })),
    };
    const receiptPath = resolve(input.outputRoot, "receipt.json");
    writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
    const sums = [receiptPath, screenshotPath, videoPath].map((path) => `${digest(path).slice(7)}  ${basename(path)}`).join("\n");
    writeFileSync(resolve(input.outputRoot, "SHA256SUMS"), `${sums}\n`);
    process.stdout.write(`${JSON.stringify({ verdict: receipt.verdict, receiptPath, receiptSha256: digest(receiptPath), evidence }, null, 2)}\n`);
    if (receipt.verdict !== "pass") process.exitCode = 1;
  } finally {
    if (application) await exitApplication(application, 1);
    rmSync(runRoot, { recursive: true, force: true });
  }
}

async function main() {
  const input = parseArguments(process.argv.slice(2));
  const identity = verifyInputs(input);
  await runObservation(input, identity);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
