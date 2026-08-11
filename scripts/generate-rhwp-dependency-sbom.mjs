import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const [
  lockArgument,
  sbomArgument = "provenance/sbom.spdx.json",
  registryArgument,
] = process.argv.slice(2);
if (!lockArgument) {
  throw new Error("usage: node scripts/generate-rhwp-dependency-sbom.mjs <Cargo.lock> [sbom.spdx.json]");
}

const root = resolve(import.meta.dirname, "..");
const lockPath = resolve(root, lockArgument);
const sbomPath = resolve(root, sbomArgument);
const registryPath = registryArgument ? resolve(root, registryArgument) : null;
const lock = readFileSync(lockPath, "utf8");
const sbom = JSON.parse(readFileSync(sbomPath, "utf8"));

const value = (block, key) => {
  const match = new RegExp(`^${key} = "([^"]+)"$`, "m").exec(block);
  return match?.[1] ?? null;
};
const slug = (input) => input.replaceAll(/[^A-Za-z0-9.-]/g, "-");
const packages = lock
  .split("[[package]]")
  .slice(1)
  .map((block) => ({
    name: value(block, "name"),
    version: value(block, "version"),
    source: value(block, "source"),
    checksum: value(block, "checksum"),
  }))
  .filter((entry) => entry.name && entry.version && entry.name !== "rhwp")
  .sort((left, right) => `${left.name}@${left.version}`.localeCompare(`${right.name}@${right.version}`));

const identities = new Set();
for (const entry of packages) {
  const identity = `${entry.name}@${entry.version}`;
  if (identities.has(identity)) throw new Error(`duplicate Cargo.lock package identity: ${identity}`);
  identities.add(identity);
}

const registryDirectories = registryPath && existsSync(registryPath)
  ? new Set(readdirSync(registryPath))
  : new Set();
const declaredLicense = (entry) => {
  const directory = `${entry.name}-${entry.version}`;
  if (!registryDirectories.has(directory)) return "NOASSERTION";
  const manifest = readFileSync(resolve(registryPath, directory, "Cargo.toml"), "utf8");
  return /^license = "([^"]+)"$/m.exec(manifest)?.[1] ?? "NOASSERTION";
};

const spdxPackages = packages.map((entry) => {
  const id = `SPDXRef-Cargo-${slug(entry.name)}-${slug(entry.version)}`;
  const registry = entry.source?.startsWith("registry+");
  const downloadLocation = registry
    ? `https://crates.io/api/v1/crates/${encodeURIComponent(entry.name)}/${encodeURIComponent(entry.version)}/download`
    : entry.source?.replace(/^git\+/, "") ?? "NOASSERTION";
  const licenseDeclared = declaredLicense(entry);
  const packageRecord = {
    name: entry.name,
    SPDXID: id,
    versionInfo: entry.version,
    downloadLocation,
    filesAnalyzed: false,
    licenseConcluded: "NOASSERTION",
    licenseDeclared,
    copyrightText: "NOASSERTION",
    externalRefs: [{
      referenceCategory: "PACKAGE-MANAGER",
      referenceType: "purl",
      referenceLocator: `pkg:cargo/${encodeURIComponent(entry.name)}@${encodeURIComponent(entry.version)}`,
    }],
  };
  if (entry.checksum) packageRecord.checksums = [{ algorithm: "SHA256", checksumValue: entry.checksum }];
  return packageRecord;
});

sbom.packages = [
  ...sbom.packages.filter((entry) => !entry.SPDXID.startsWith("SPDXRef-Cargo-")),
  ...spdxPackages,
];
sbom.relationships = [
  ...sbom.relationships.filter((entry) => !entry.relatedSpdxElement.startsWith("SPDXRef-Cargo-")),
  ...spdxPackages.map((entry) => ({
    spdxElementId: "SPDXRef-Package-rhwp",
    relationshipType: "DEPENDS_ON",
    relatedSpdxElement: entry.SPDXID,
  })),
];
writeFileSync(sbomPath, `${JSON.stringify(sbom, null, 2)}\n`, "utf8");

const lockReceipt = {
  schemaVersion: 1,
  upstream: "https://github.com/edwardkim/rhwp.git",
  commit: "2dced7bfe10c6597cead634264c7c1781c01f1e7",
  cargoLockURL: "https://raw.githubusercontent.com/edwardkim/rhwp/2dced7bfe10c6597cead634264c7c1781c01f1e7/Cargo.lock",
  cargoLockSHA256: `sha256:${createHash("sha256").update(lock).digest("hex")}`,
  packageCount: packages.length,
  packages: packages.map(({ name, version, source, checksum }) => ({
    name,
    version,
    source,
    checksum,
    licenseDeclared: declaredLicense({ name, version }),
  })),
};
writeFileSync(
  resolve(root, "provenance/rhwp-dependency-lock.json"),
  `${JSON.stringify(lockReceipt, null, 2)}\n`,
  "utf8",
);

const noticeLines = [
  "# rhwp Rust dependency notice inventory",
  "",
  "Generated from the exact Cargo.lock pinned in `provenance/rhwp-dependency-lock.json`.",
  "License expressions are the package manifests' declarations; `NOASSERTION` means the",
  "local registry cache did not contain enough data to make a declaration. The SPDX file",
  "keeps `licenseConcluded` at `NOASSERTION` because this inventory is not a legal opinion.",
  "",
  "| Package | Version | Declared license | Source |",
  "| --- | --- | --- | --- |",
  ...packages.map((entry) => (
    `| ${entry.name} | ${entry.version} | ${declaredLicense(entry)} | ${entry.source ?? "workspace"} |`
  )),
  "",
];
writeFileSync(
  resolve(root, "Resources/Legal/rhwp-RUST-DEPENDENCIES.md"),
  noticeLines.join("\n"),
  "utf8",
);
