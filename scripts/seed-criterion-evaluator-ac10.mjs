import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, join, relative } from "node:path";
import {
  check,
  criterionContractPaths,
  formats,
  identityCheck,
  result,
} from "./seed-criterion-contract-core.mjs";
import { packagedGenOfficeRuntimeChecks } from "./seed-genoffice-runtime-contract.mjs";

const sha256 = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");

function command(path, args) {
  try {
    return { passed: true, output: execFileSync(path, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }) };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { passed: false, output: detail };
  }
}

function extractedFile(root, path) {
  if (isAbsolute(path) || path.split(/[\\/]/u).includes("..")) throw new Error(`unsafe extracted path: ${path}`);
  const physicalRoot = realpathSync(root);
  const physical = realpathSync(join(physicalRoot, path));
  const confined = relative(physicalRoot, physical);
  if (confined.startsWith("..") || isAbsolute(confined)) throw new Error(`extracted path escapes root: ${path}`);
  return physical;
}

function appBundles(root, directory = root, found = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const path = join(directory, entry.name);
    if (entry.name.endsWith(".app")) found.push(path);
    else appBundles(root, path, found);
  }
  return found;
}

function extractedReader(root) {
  const bytes = (path) => readFileSync(extractedFile(root, path));
  return {
    sha256: (path) => createHash("sha256").update(bytes(path)).digest("hex"),
    size: (path) => statSync(extractedFile(root, path)).size,
    text: (path) => bytes(path).toString("utf8"),
    json: (path) => JSON.parse(bytes(path).toString("utf8")),
  };
}

function smoke(binary, root, scenario) {
  mkdirSync(root, { recursive: true });
  const execution = command(binary, ["--export-self-test", root, scenario]);
  if (!execution.passed) return { passed: false, formats: [] };
  try {
    const receipt = JSON.parse(execution.output);
    const validResults = (receipt.results ?? []).filter((entry) => entry.structuralValid === true && entry.semanticValid === true).map((entry) => entry.format);
    return { passed: true, formats: validResults };
  } catch (error) {
    return { passed: false, formats: [], detail: error instanceof Error ? error.message : String(error) };
  }
}

function inspectArchive(candidate, index, reader) {
  const archive = candidate.archive ?? {};
  const checks = [];
  let archivePath;
  try {
    archivePath = reader.safe(archive.path);
    const archiveBytes = readFileSync(archivePath);
    checks.push(check("release.archive", archive.path.endsWith(".zip") && archive.sha256 === `sha256:${sha256(archivePath)}` && archive.evidence?.sha256 === archive.sha256 && archive.byteCount === statSync(archivePath).size && archiveBytes.subarray(0, 2).toString("ascii") === "PK", "canonical candidate is the actual hash- and size-bound ZIP"));
  } catch (error) {
    checks.push(check("release.archive", false, error instanceof Error ? error.message : String(error)));
    return checks;
  }
  const extractionRoot = mkdtempSync(join(tmpdir(), "public-document-seed-"));
  try {
    const extraction = command("/usr/bin/ditto", ["-x", "-k", archivePath, extractionRoot]);
    checks.push(check("release.extraction", extraction.passed, extraction.output || "pristine ZIP extraction"));
    if (!extraction.passed) return checks;
    const apps = appBundles(extractionRoot);
    checks.push(check("release.app-count", apps.length === 1, "archive contains exactly one application bundle"));
    if (apps.length !== 1) return checks;
    const app = realpathSync(apps[0]);
    const binary = realpathSync(join(app, "Contents/MacOS/PublicDocumentApp"));
    const bundledRhwp = realpathSync(join(app, "Contents/Resources/Engines/rhwp"));
    const contentsReader = extractedReader(join(app, "Contents"));
    const codesign = command("/usr/bin/codesign", ["--verify", "--deep", "--strict", "--verbose=2", app]);
    const architecture = command("/usr/bin/file", [binary]);
    const xattrs = command("/usr/bin/xattr", ["-lr", app]);
    checks.push(check("release.codesign", codesign.passed, codesign.output || "strict codesign passes after extraction"));
    const architecturePassed = architecture.passed && /Mach-O.*arm64/u.test(architecture.output);
    const xattrsPassed = xattrs.passed && !/com\.apple\.(FinderInfo|ResourceFork)/u.test(xattrs.output);
    checks.push(check("release.architecture", architecturePassed, architecturePassed ? "extracted executable is arm64" : architecture.output));
    checks.push(check("release.xattrs", xattrsPassed, xattrsPassed ? "no forbidden extended attributes" : xattrs.output));
    const inventory = index.sha256Inventory ?? [];
    const inventoryPaths = inventory.map((line) => /^([a-f0-9]{64})\s{2}(.+)$/u.exec(line));
    const relativePaths = inventoryPaths.filter((match) => match !== null).map((match) => match[2]);
    const inventoryValid = inventory.length > 0
      && inventory.length === new Set(relativePaths).size
      && JSON.stringify(relativePaths) === JSON.stringify([...relativePaths].sort())
      && inventoryPaths.every((match) => match !== null && sha256(extractedFile(extractionRoot, match[2])) === match[1]);
    checks.push(check("release.inventory", inventoryValid, "sorted unique inventory hashes recomputed from pristine extraction"));
    const upstream = reader.json("artifacts/provenance/upstream-lock.json");
    const pinnedRhwp = upstream.upstreams?.find((entry) => entry.name === "rhwp")?.local_patchset?.bundled_arm64_binary_sha256;
    checks.push(check("release.rhwp", `sha256:${sha256(bundledRhwp)}` === pinnedRhwp, "packaged rhwp matches the approved upstream lock"));
    const studioMatches = ["index.html", "styles.css", "app.js"].every((name) => sha256(join(app, "Contents/Resources/Studio", name)) === reader.sha256(`Resources/Studio/${name}`));
    checks.push(check("release.studio", studioMatches, "packaged Studio hashes match the current verified source"));
    const runtimeManifestPath = "Resources/GenOffice/runtime-manifest.json";
    const inputLockPath = "Resources/Provenance/genoffice-runtime-input-lock.json";
    const packagedManifest = contentsReader.json(runtimeManifestPath);
    const packagedInputLock = contentsReader.json(inputLockPath);
    const runtimeArtifactsMatch = contentsReader.sha256(runtimeManifestPath) === reader.sha256("artifacts/provenance/genoffice-runtime-manifest.json")
      && contentsReader.sha256(inputLockPath) === reader.sha256("artifacts/provenance/genoffice-runtime-input-lock.json");
    checks.push(check("release.genoffice-artifacts", runtimeArtifactsMatch, "packaged runtime manifest and input lock match AC-01 artifacts"));
    checks.push(...packagedGenOfficeRuntimeChecks(packagedManifest, packagedInputLock, contentsReader));
    const nodeArchitecture = command("/usr/bin/file", [extractedFile(join(app, "Contents"), `Resources/${packagedManifest.node?.sourcePath}`)]);
    const nodeArchitecturePassed = nodeArchitecture.passed && /Mach-O.*arm64/u.test(nodeArchitecture.output);
    checks.push(check("release.genoffice-node-architecture", nodeArchitecturePassed, nodeArchitecturePassed ? "packaged Node executable is arm64" : nodeArchitecture.output));
    const hwpSmoke = smoke(binary, join(extractionRoot, "smoke-hwp"), "basic-hwp-family");
    const docsSmoke = smoke(binary, join(extractionRoot, "smoke-docs"), "all-consented");
    const smokeFormats = new Set([...hwpSmoke.formats, ...docsSmoke.formats]);
    checks.push(check("release.offline-smoke", hwpSmoke.passed && docsSmoke.passed && formats.every((format) => smokeFormats.has(format)), "extracted binary produced and validated all four formats without credentials"));
  } catch (error) {
    checks.push(check("release.archive-inspection", false, error instanceof Error ? error.message : String(error)));
  } finally {
    rmSync(extractionRoot, { recursive: true, force: true });
  }
  return checks;
}

export function deriveAc10Outcome(preceding, releaseChecks) {
  const checks = [...releaseChecks];
  const predecessorFailure = preceding.some((entry) => entry.verdict === "fail");
  if (predecessorFailure) checks.push(check("release.predecessors", false, "at least one predecessor failed"));
  const blockers = preceding.filter((entry) => entry.verdict === "blocked").map((entry) => `${entry.criterion} remains externally blocked.`);
  return result("AC-10", checks, blockers, "Pristine unsigned archive and all nine predecessor checks passed.");
}

export function evaluateAc10(snapshot, reader, preceding) {
  const candidate = snapshot[criterionContractPaths["AC-10"][0]];
  const index = snapshot[criterionContractPaths["AC-10"][1]];
  const releaseChecks = [...inspectArchive(candidate, index, reader), identityCheck(snapshot, reader, 4, ["archiveVerification"])];
  return deriveAc10Outcome(preceding, releaseChecks);
}
