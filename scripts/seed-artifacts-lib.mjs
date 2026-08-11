import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const seedPath = ".ouroboros/seeds/seed_219732b73d5d.yaml";

export class SeedArtifactPathError extends Error {
  constructor(path, reason) {
    super(`Unsafe Seed artifact path ${String(path)}: ${reason}`);
    this.name = "SeedArtifactPathError";
    this.path = path;
    this.reason = reason;
  }
}

export function confinedPath(root, relativePath, mode = "read") {
  if (typeof relativePath !== "string" || relativePath.length === 0) {
    throw new SeedArtifactPathError(relativePath, "a non-empty project-relative path is required");
  }
  if (isAbsolute(relativePath) || relativePath.split(/[\\/]/u).includes("..")) {
    throw new SeedArtifactPathError(relativePath, "absolute and parent-traversal paths are forbidden");
  }
  const physicalRoot = realpathSync(resolve(root));
  const target = resolve(physicalRoot, relativePath);
  const lexical = relative(physicalRoot, target);
  if (lexical.startsWith("..") || isAbsolute(lexical)) {
    throw new SeedArtifactPathError(relativePath, "path escapes the selected project root");
  }
  let boundaryTarget;
  switch (mode) {
  case "read":
    boundaryTarget = realpathSync(target);
    break;
  case "write": {
    let ancestor = target;
    while (!existsSync(ancestor)) ancestor = dirname(ancestor);
    boundaryTarget = realpathSync(ancestor);
    break;
  }
  default:
    throw new SeedArtifactPathError(relativePath, `unsupported access mode ${String(mode)}`);
  }
  const physicalRelative = relative(physicalRoot, boundaryTarget);
  if (physicalRelative.startsWith("..") || isAbsolute(physicalRelative)) {
    throw new SeedArtifactPathError(relativePath, "symlink resolves outside the selected project root");
  }
  return target;
}

export function absolute(relativePath, mode = "read") {
  return confinedPath(projectRoot, relativePath, mode);
}

export function readText(relativePath) {
  return readFileSync(absolute(relativePath), "utf8");
}

export function readJSON(relativePath) {
  return JSON.parse(readText(relativePath));
}

export function sha256(relativePath) {
  return createHash("sha256").update(readFileSync(absolute(relativePath))).digest("hex");
}

export function evidence(relativePath) {
  const target = absolute(relativePath, "write");
  if (!existsSync(target)) {
    throw new Error(`Required evidence is missing: ${relativePath}`);
  }
  return { path: relativePath, sha256: `sha256:${sha256(relativePath)}` };
}

export function writeJSON(relativePath, value) {
  const target = absolute(relativePath, "write");
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export function writeText(relativePath, value) {
  const target = absolute(relativePath, "write");
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, value.endsWith("\n") ? value : `${value}\n`, "utf8");
}

export function copy(relativeSource, relativeTarget) {
  const target = absolute(relativeTarget, "write");
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(absolute(relativeSource), target);
}

export function acceptance({ criterion, verdict, summary, blockers = [], sources, contracts }) {
  return {
    schemaVersion: 1,
    criterion,
    verdict,
    summary,
    blockers,
    seed: evidence(seedPath),
    sourceEvidence: sources.map(evidence),
    contracts: contracts.map(evidence),
  };
}

export function normalizeCriterion(raw) {
  const value = String(raw ?? "").trim().toUpperCase();
  const match = /^(?:AC-?)?(\d{1,2})$/.exec(value);
  if (!match) throw new Error(`Expected AC-01 through AC-10, received: ${raw ?? ""}`);
  const number = Number.parseInt(match[1], 10);
  if (number < 1 || number > 10) throw new Error(`Criterion is out of range: ${raw}`);
  return `AC-${String(number).padStart(2, "0")}`;
}
