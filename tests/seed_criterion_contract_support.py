from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Mapping, Sequence, TypedDict, Union


JSONValue = Union[str, int, float, bool, None, Sequence["JSONValue"], Mapping[str, "JSONValue"]]


class ContractCheck(TypedDict):
    id: str
    passed: bool
    detail: str


class ContractResult(TypedDict):
    criterion: str
    verdict: str
    summary: str
    blockers: List[str]
    checks: List[ContractCheck]


ROOT = Path(__file__).resolve().parents[1]
NODE_DRIVER = """
import {
  compareAcceptanceProjection,
  deriveAc10Outcome,
  evaluateCriterionAtRoot,
} from './scripts/seed-criterion-contracts.mjs';
import { readerAt } from './scripts/seed-criterion-contract-core.mjs';
import { packagedGenOfficeRuntimeChecks } from './scripts/seed-genoffice-runtime-contract.mjs';
import {
  projectCompatibilityLocalFacts,
  validateSeedEvidenceSourceMap,
} from './scripts/seed-criterion-source-map.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
let result;
switch (request.action) {
  case 'evaluate':
    result = evaluateCriterionAtRoot(request.criterion, request.root);
    break;
  case 'derive-ac10':
    result = deriveAc10Outcome(request.preceding, request.releaseChecks);
    break;
  case 'compare':
    result = compareAcceptanceProjection(request.receipt, request.evaluation);
    break;
  case 'source-map':
    result = validateSeedEvidenceSourceMap(request.map, request.root);
    break;
  case 'project-compatibility':
    result = projectCompatibilityLocalFacts(request.compatibility);
    break;
  case 'packaged-genoffice':
    result = packagedGenOfficeRuntimeChecks(request.manifest, request.inputLock, readerAt(request.root));
    break;
  default:
    throw new Error(`Unknown test action: ${request.action}`);
}
process.stdout.write(JSON.stringify(result));
"""
PATH_DRIVER = "import { confinedPath } from './scripts/seed-artifacts-lib.mjs'; process.stdout.write(confinedPath(process.argv[1], process.argv[2]));"


def run_node(request: Mapping[str, JSONValue]) -> str:
    return subprocess.run(
        ["node", "--input-type=module", "-e", NODE_DRIVER],
        cwd=ROOT,
        input=json.dumps(request),
        capture_output=True,
        check=True,
        text=True,
    ).stdout


def run_contract(request: Mapping[str, JSONValue]) -> ContractResult:
    return json.loads(run_node(request))


def run_comparison(request: Mapping[str, JSONValue]) -> List[str]:
    return json.loads(run_node(request))
