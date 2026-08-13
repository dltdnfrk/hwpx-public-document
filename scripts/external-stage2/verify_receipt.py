from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--trust-policy", type=Path, required=True)
    parser.add_argument("--trust-policy-sha256", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--now")
    arguments = parser.parse_args()
    contract = importlib.import_module("external_stage2.contract")
    verifier = importlib.import_module("external_stage2.verifier")
    try:
        now = (
            contract.parse_timestamp(arguments.now, "INTERNAL_VERIFIER_ERROR")
            if arguments.now is not None
            else datetime.now(timezone.utc)
        )
    except contract.ContractError:
        output = {
            "decision": "NOT_ACCEPTED",
            "reason_codes": ["INTERNAL_VERIFIER_ERROR"],
            "receipt_digest": None,
            "semantic_pass": False,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        return 2
    decision = verifier.verify(
        verifier.VerificationInputs(
            receipt_path=arguments.receipt,
            policy_path=arguments.trust_policy,
            request_path=arguments.request,
            result_path=arguments.result,
            manifest_path=arguments.manifest,
            artifact_root=arguments.artifact_root,
            execution_id=arguments.execution_id,
            now=now,
            trust_policy_sha256=arguments.trust_policy_sha256,
        )
    )
    output = {
        "decision": "ACCEPTED" if decision.semantic_pass else "NOT_ACCEPTED",
        "reason_codes": list(decision.reason_codes),
        "receipt_digest": decision.receipt_digest,
        "semantic_pass": decision.semantic_pass,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0 if decision.semantic_pass else 2


if __name__ == "__main__":
    sys.exit(main())
