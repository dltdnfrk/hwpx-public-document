#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  copyFileSync,
  createReadStream,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, extname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const REPOSITORY_ROOT = realpathSync(resolve(dirname(SCRIPT_PATH), ".."));
const WORD_APP = "/Applications/Microsoft Word.app";
const INFO_PLIST = join(WORD_APP, "Contents", "Info.plist");

function usage() {
  return [
    "Usage:",
    "  node scripts/verify-word-docx-reopen.mjs <artifact.docx> <fixture.json> <new-output-root>",
    "",
    "The output root must not already exist and must be inside this repository.",
  ].join("\n");
}

function fail(message) {
  throw new Error(message);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || "no diagnostic output").trim();
    throw new Error(`${command} exited ${result.status}: ${detail}`);
  }
  return result.stdout.trim();
}

async function sha256(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}

function isWithinRepository(filePath) {
  const pathFromRoot = relative(REPOSITORY_ROOT, filePath);
  return pathFromRoot !== "" && !pathFromRoot.startsWith("..") && !isAbsolute(pathFromRoot);
}

function requireRepositoryFile(argument, label) {
  const candidate = resolve(process.cwd(), argument);
  if (!existsSync(candidate) || !statSync(candidate).isFile()) {
    fail(`${label} is not a file: ${candidate}`);
  }
  const physicalPath = realpathSync(candidate);
  if (!isWithinRepository(physicalPath)) {
    fail(`${label} must resolve inside ${REPOSITORY_ROOT}: ${physicalPath}`);
  }
  return physicalPath;
}

function requireNewRepositoryDirectory(argument) {
  const outputRoot = resolve(process.cwd(), argument);
  if (existsSync(outputRoot)) {
    fail(`output root already exists; refusing to overwrite it: ${outputRoot}`);
  }
  const outputParent = dirname(outputRoot);
  if (!existsSync(outputParent) || !lstatSync(outputParent).isDirectory()) {
    fail(`output parent must already be a directory: ${outputParent}`);
  }
  const physicalParent = realpathSync(outputParent);
  if (!isWithinRepository(physicalParent)) {
    fail(`output root must be inside ${REPOSITORY_ROOT}: ${outputRoot}`);
  }
  return outputRoot;
}

function plistValue(key) {
  return run("/usr/libexec/PlistBuddy", ["-c", `Print :${key}`, INFO_PLIST]);
}

function uniqueKoreanStrings(fixture) {
  const candidates = [
    typeof fixture.title === "string" ? fixture.title : null,
    ...(Array.isArray(fixture.elements)
      ? fixture.elements.map((element) =>
          element && typeof element.text === "string" ? element.text : null,
        )
      : []),
  ];
  return [...new Set(candidates.filter((value) => value && /[\uac00-\ud7a3]/u.test(value)))];
}

function corpusBinding(fixtureHash) {
  const corpusPath = join(
    REPOSITORY_ROOT,
    "Resources",
    "Compatibility",
    "compatibility-corpus-1.0.0.json",
  );
  if (!existsSync(corpusPath)) {
    return { fixtureID: null, requiredFonts: [], corpusVersion: null };
  }
  const corpus = JSON.parse(readFileSync(corpusPath, "utf8"));
  const fixture = Array.isArray(corpus.fixtures)
    ? corpus.fixtures.find((entry) => entry.projectHash === `sha256:${fixtureHash}`)
    : null;
  return {
    fixtureID: fixture?.id ?? null,
    requiredFonts: Array.isArray(corpus.requiredFonts) ? corpus.requiredFonts : [],
    corpusVersion: typeof corpus.corpusVersion === "string" ? corpus.corpusVersion : null,
  };
}

function parseBoolean(value, field) {
  if (value === "true") return true;
  if (value === "false") return false;
  fail(`Microsoft Word returned an invalid ${field}: ${JSON.stringify(value)}`);
}

function parseOptionalInteger(value, field) {
  if (value === "") return null;
  if (!/^-?\d+$/u.test(value)) {
    fail(`Microsoft Word returned an invalid ${field}: ${JSON.stringify(value)}`);
  }
  return Number.parseInt(value, 10);
}

function queryWordRuntimeState() {
  const script = String.raw`
set fieldSeparator to ASCII character 30
tell application "Microsoft Word"
  return (version as text) & fieldSeparator & (build as text) & fieldSeparator & ((count of documents) as text)
end tell
`;
  const result = spawnSync("/usr/bin/osascript", ["-"], {
    encoding: "utf8",
    input: script,
    maxBuffer: 1024 * 1024,
    timeout: 10_000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || `osascript exited ${result.status}`).trim());
  }
  const fields = result.stdout.replace(/\n$/u, "").split("\u001e");
  if (fields.length !== 3) {
    throw new Error(`Microsoft Word returned ${fields.length} runtime fields; expected 3`);
  }
  return {
    version: fields[0],
    build: fields[1],
    openDocumentCount: parseOptionalInteger(fields[2], "open document count"),
  };
}

function observeWordRuntimeState() {
  try {
    return { observation: queryWordRuntimeState(), error: null };
  } catch (error) {
    return {
      observation: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function wordAppleScript() {
  return String.raw`
on writeUTF8(theText, outputPath)
  set outputFile to POSIX file outputPath
  set fileHandle to open for access outputFile with write permission
  try
    set eof fileHandle to 0
    write theText to fileHandle as «class utf8»
    close access fileHandle
  on error errorMessage number errorNumber
    try
      close access fileHandle
    end try
    error errorMessage number errorNumber
  end try
end writeUTF8

set inputPath to system attribute "WORD_REOPEN_INPUT"
set openOutputPath to system attribute "WORD_REOPEN_OPEN_TEXT"
set reopenOutputPath to system attribute "WORD_REOPEN_REOPEN_TEXT"
set fieldSeparator to ASCII character 30
set openedDocument to missing value
set reopenedDocument to missing value

tell application "Microsoft Word"
  try
    set reportedVersion to version as text
    set reportedBuild to build as text
    set openedDocument to open file name inputPath read only true add to recent files false
    set openedName to name of openedDocument as text
    set openedSaved to saved of openedDocument as text
    set openedText to content of text object of openedDocument as text
    set openedPageCount to ""
    set openedPageErrorNumber to ""
    try
      set openedPageCount to (compute statistics openedDocument statistic statistic pages) as text
    on error number pageErrorNumber
      set openedPageErrorNumber to pageErrorNumber as text
    end try
    my writeUTF8(openedText, openOutputPath)
    close openedDocument saving no
    set openedDocument to missing value

    set reopenedDocument to open file name inputPath read only true add to recent files false
    set reopenedName to name of reopenedDocument as text
    set reopenedSaved to saved of reopenedDocument as text
    set reopenedText to content of text object of reopenedDocument as text
    set reopenedPageCount to ""
    set reopenedPageErrorNumber to ""
    try
      set reopenedPageCount to (compute statistics reopenedDocument statistic statistic pages) as text
    on error number pageErrorNumber
      set reopenedPageErrorNumber to pageErrorNumber as text
    end try
    my writeUTF8(reopenedText, reopenOutputPath)
    close reopenedDocument saving no
    set reopenedDocument to missing value

    return reportedVersion & fieldSeparator & reportedBuild & fieldSeparator & openedName & fieldSeparator & openedSaved & fieldSeparator & openedPageCount & fieldSeparator & openedPageErrorNumber & fieldSeparator & reopenedName & fieldSeparator & reopenedSaved & fieldSeparator & reopenedPageCount & fieldSeparator & reopenedPageErrorNumber
  on error errorMessage number errorNumber
    if reopenedDocument is not missing value then
      try
        close reopenedDocument saving no
      end try
    end if
    if openedDocument is not missing value then
      try
        close openedDocument saving no
      end try
    end if
    error errorMessage number errorNumber
  end try
end tell
`;
}

function writeEvidenceHashes(outputRoot, files) {
  const lines = files.map(({ hash, relativePath }) => `${hash}  ${relativePath}`);
  writeFileSync(join(outputRoot, "evidence-sha256.txt"), `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const [artifactArgument, fixtureArgument, outputArgument, ...extra] = process.argv.slice(2);
  if (!artifactArgument || !fixtureArgument || !outputArgument || extra.length > 0) {
    console.error(usage());
    process.exitCode = 64;
    return;
  }

  const artifactPath = requireRepositoryFile(artifactArgument, "artifact");
  const fixturePath = requireRepositoryFile(fixtureArgument, "fixture");
  const outputRoot = requireNewRepositoryDirectory(outputArgument);
  if (extname(artifactPath).toLowerCase() !== ".docx") {
    fail(`artifact must use the .docx extension: ${artifactPath}`);
  }
  if (!existsSync(INFO_PLIST)) {
    fail(`Microsoft Word is not installed at ${WORD_APP}`);
  }

  const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
  const expectedTexts = uniqueKoreanStrings(fixture);
  if (expectedTexts.length === 0) {
    fail(`fixture contains no Korean title or element text: ${fixturePath}`);
  }

  const artifactHashBefore = await sha256(artifactPath);
  const artifactByteCount = statSync(artifactPath).size;
  const fixtureHash = await sha256(fixturePath);
  const fixtureByteCount = statSync(fixturePath).size;
  const binding = corpusBinding(fixtureHash);
  const toolHash = await sha256(SCRIPT_PATH);
  const executableName = plistValue("CFBundleExecutable");
  const executablePath = join(WORD_APP, "Contents", "MacOS", executableName);
  const executableHash = await sha256(executablePath);
  const bundleIdentifier = plistValue("CFBundleIdentifier");
  const bundleVersion = plistValue("CFBundleShortVersionString");
  const bundleBuild = plistValue("CFBundleVersion");
  const osName = run("/usr/bin/sw_vers", ["-productName"]);
  const osVersion = run("/usr/bin/sw_vers", ["-productVersion"]);
  const osBuild = run("/usr/bin/sw_vers", ["-buildVersion"]);
  const architecture = run("/usr/bin/uname", ["-m"]);
  const ioreg = run("/usr/sbin/ioreg", ["-n", "Root", "-d1"]);
  const consoleLocked =
    /"CGSSessionScreenIsLocked"=Yes/u.test(ioreg) || /"IOConsoleLocked" = Yes/u.test(ioreg);

  mkdirSync(outputRoot, { mode: 0o755 });
  const temporaryCopyPath = join(outputRoot, "input.docx");
  const openObservationPath = join(outputRoot, "open-observation.txt");
  const reopenObservationPath = join(outputRoot, "reopen-observation.txt");
  copyFileSync(artifactPath, temporaryCopyPath);
  const temporaryCopyHashBefore = await sha256(temporaryCopyPath);
  const runtimeBefore = observeWordRuntimeState();

  let operationError = null;
  let fields = null;
  try {
    const result = spawnSync("/usr/bin/osascript", ["-"], {
      encoding: "utf8",
      input: wordAppleScript(),
      maxBuffer: 32 * 1024 * 1024,
      timeout: 30_000,
      env: {
        ...process.env,
        WORD_REOPEN_INPUT: temporaryCopyPath,
        WORD_REOPEN_OPEN_TEXT: openObservationPath,
        WORD_REOPEN_REOPEN_TEXT: reopenObservationPath,
      },
    });
    if (result.error) throw result.error;
    if (result.status !== 0) {
      throw new Error((result.stderr || result.stdout || `osascript exited ${result.status}`).trim());
    }
    fields = result.stdout.replace(/\n$/u, "").split("\u001e");
    if (fields.length !== 10) {
      throw new Error(`Microsoft Word returned ${fields.length} metadata fields; expected 10`);
    }
  } catch (error) {
    operationError = error instanceof Error ? error.message : String(error);
  }

  const artifactHashAfter = await sha256(artifactPath);
  const temporaryCopyHashAfter = await sha256(temporaryCopyPath);
  const runtimeAfter = observeWordRuntimeState();
  const inputPreserved = artifactHashAfter === artifactHashBefore;
  const temporaryCopyPreserved = temporaryCopyHashAfter === temporaryCopyHashBefore;

  let openObservation = null;
  let reopenObservation = null;
  if (!operationError) {
    const [
      appReportedVersion,
      appReportedBuild,
      openedName,
      openedSavedRaw,
      openedPageCountRaw,
      openedPageErrorRaw,
      reopenedName,
      reopenedSavedRaw,
      reopenedPageCountRaw,
      reopenedPageErrorRaw,
    ] = fields;
    const openText = readFileSync(openObservationPath, "utf8");
    const reopenText = readFileSync(reopenObservationPath, "utf8");
    openObservation = {
      appReportedVersion,
      appReportedBuild,
      name: openedName,
      saved: parseBoolean(openedSavedRaw, "opened saved state"),
      text: openText,
      textPath: relative(outputRoot, openObservationPath),
      textHash: `sha256:${await sha256(openObservationPath)}`,
      textByteCount: statSync(openObservationPath).size,
      matchedExpectedTextCount: expectedTexts.filter((text) => openText.includes(text)).length,
      pageCount: parseOptionalInteger(openedPageCountRaw, "opened page count"),
      pageCountErrorNumber: parseOptionalInteger(openedPageErrorRaw, "opened page error"),
    };
    reopenObservation = {
      name: reopenedName,
      saved: parseBoolean(reopenedSavedRaw, "reopened saved state"),
      text: reopenText,
      textPath: relative(outputRoot, reopenObservationPath),
      textHash: `sha256:${await sha256(reopenObservationPath)}`,
      textByteCount: statSync(reopenObservationPath).size,
      matchedExpectedTextCount: expectedTexts.filter((text) => reopenText.includes(text)).length,
      pageCount: parseOptionalInteger(reopenedPageCountRaw, "reopened page count"),
      pageCountErrorNumber: parseOptionalInteger(reopenedPageErrorRaw, "reopened page error"),
    };
  }

  const expectedName = "input.docx";
  const documentModelPassed =
    !operationError &&
    inputPreserved &&
    temporaryCopyPreserved &&
    openObservation.name === expectedName &&
    reopenObservation.name === expectedName &&
    openObservation.saved &&
    reopenObservation.saved &&
    openObservation.matchedExpectedTextCount === expectedTexts.length &&
    reopenObservation.matchedExpectedTextCount === expectedTexts.length &&
    openObservation.text === reopenObservation.text;
  const documentModelBlocked =
    !documentModelPassed && Boolean(operationError?.includes("ETIMEDOUT"));
  const documentModelVerdict = documentModelPassed
    ? "pass"
    : documentModelBlocked
      ? "blocked"
      : "fail";
  const pageCountAvailable =
    !operationError &&
    openObservation.pageCount !== null &&
    reopenObservation.pageCount !== null;

  const receipt = {
    schemaVersion: 2,
    operation: "microsoft-word-reopen",
    completedAt: new Date().toISOString(),
    verdict: documentModelPassed || documentModelBlocked ? "blocked" : "fail",
    documentModelVerdict,
    tool: {
      path: relative(REPOSITORY_ROOT, SCRIPT_PATH),
      hash: `sha256:${toolHash}`,
    },
    client: {
      clientID: "microsoft-word",
      clientName: "Microsoft Word",
      bundlePath: WORD_APP,
      bundleIdentifier,
      bundleVersion,
      bundleBuild,
      appReportedVersion:
        openObservation?.appReportedVersion ?? runtimeBefore.observation?.version ?? null,
      appReportedBuild:
        openObservation?.appReportedBuild ?? runtimeBefore.observation?.build ?? null,
      executablePath,
      executableHash: `sha256:${executableHash}`,
    },
    environment: {
      osName,
      osVersion,
      osBuild,
      architecture,
      consoleLocked,
      corpusRequiredFonts: binding.requiredFonts,
      wordRuntimeBefore: runtimeBefore,
      wordRuntimeAfter: runtimeAfter,
    },
    fixture: {
      fixtureID: binding.fixtureID ?? fixture.documentID ?? null,
      corpusVersion: binding.corpusVersion,
      path: relative(REPOSITORY_ROOT, fixturePath),
      hash: `sha256:${fixtureHash}`,
      byteCount: fixtureByteCount,
      expectedKoreanStrings: expectedTexts,
      expectedKoreanStringCount: expectedTexts.length,
    },
    artifact: {
      format: "docx",
      path: relative(REPOSITORY_ROOT, artifactPath),
      hashBefore: `sha256:${artifactHashBefore}`,
      hashAfter: `sha256:${artifactHashAfter}`,
      byteCount: artifactByteCount,
      pristineInputPreserved: inputPreserved,
    },
    temporaryCopy: {
      path: relative(REPOSITORY_ROOT, temporaryCopyPath),
      hashBefore: `sha256:${temporaryCopyHashBefore}`,
      hashAfter: `sha256:${temporaryCopyHashAfter}`,
      byteCount: statSync(temporaryCopyPath).size,
      preserved: temporaryCopyPreserved,
      openedReadOnly: true,
    },
    observations: {
      opened: openObservation,
      reopened: reopenObservation,
      exactTextStableAcrossReopen:
        !operationError && openObservation.text === reopenObservation.text,
      pageCount: {
        available: pageCountAvailable,
        opened: openObservation?.pageCount ?? null,
        reopened: reopenObservation?.pageCount ?? null,
        verdict: pageCountAvailable ? "observed" : "blocked",
        diagnostics: pageCountAvailable
          ? "Observed with Microsoft Word compute statistics using statistic pages."
          : operationError
            ? "The document open/reopen operation did not complete, so page count was not observed."
            : "Microsoft Word did not expose page count through compute statistics for one or both opens.",
      },
      extensionWarningCount: null,
      extensionWarningObservation: {
        verdict: "blocked",
        rawValue: null,
        diagnostics:
          "Microsoft Word's AppleScript document model has no API for enumerating extension-warning dialogs; no zero-warning claim is inferred.",
      },
    },
    visualCapture: {
      verdict: "blocked",
      attempted: false,
      diagnostics: consoleLocked
        ? "The macOS console is locked; this tool makes no GUI screenshot claim."
        : "This tool validates the AppleScript document model only; GUI capture requires a separate visual observation.",
    },
    editSaveRoundtrip: {
      verdict: "blocked",
      attempted: false,
      diagnostics:
        "The tool opens a disposable copy read-only and closes without saving; it makes no save-as or edit-roundtrip claim.",
    },
    operationError,
    operationBlocker: documentModelBlocked
      ? {
          kind: "apple-event-timeout",
          diagnostics: consoleLocked
            ? "The locked console allowed runtime metadata queries, but the DOCX open Apple event did not complete within 30 seconds."
            : "The DOCX open Apple event did not complete within 30 seconds.",
        }
      : null,
  };

  const receiptPath = join(outputRoot, "receipt.json");
  writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
  const hashEntries = [
    {
      relativePath: "input.docx",
      hash: temporaryCopyHashAfter,
    },
  ];
  if (existsSync(openObservationPath)) {
    hashEntries.push({
      relativePath: "open-observation.txt",
      hash: await sha256(openObservationPath),
    });
  }
  if (existsSync(reopenObservationPath)) {
    hashEntries.push({
      relativePath: "reopen-observation.txt",
      hash: await sha256(reopenObservationPath),
    });
  }
  hashEntries.push({ relativePath: "receipt.json", hash: await sha256(receiptPath) });
  writeEvidenceHashes(outputRoot, hashEntries);

  console.log(JSON.stringify(receipt, null, 2));
  if (!documentModelPassed) {
    process.exitCode = documentModelBlocked ? 2 : 1;
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
