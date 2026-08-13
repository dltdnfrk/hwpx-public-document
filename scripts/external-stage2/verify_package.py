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
    parser.add_argument("--primary-manifest", type=Path, required=True)
    parser.add_argument("--secondary-manifest", type=Path, required=True)
    parser.add_argument("--primary-artifact-root", type=Path, required=True)
    parser.add_argument("--secondary-artifact-root", type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--pin-db", type=Path, required=True)
    parser.add_argument("--now")
    arguments = parser.parse_args()
    contract = importlib.import_module("external_stage2.contract")
    package_verifier = importlib.import_module("external_stage2.package_verifier")
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
            "integrity_pass": False,
            "reason_codes": ["INTERNAL_VERIFIER_ERROR"],
            "receipt_digest": None,
            "semantic_pass": False,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        return 2
    decision = package_verifier.verify_package(
        package_verifier.PackageVerificationInputs(
            verification=verifier.VerificationInputs(
                receipt_path=arguments.receipt,
                policy_path=arguments.trust_policy,
                request_path=arguments.request,
                result_path=arguments.result,
                manifest_path=arguments.primary_manifest,
                artifact_root=arguments.primary_artifact_root,
                execution_id=arguments.execution_id,
                now=now,
                trust_policy_sha256=arguments.trust_policy_sha256,
            ),
            secondary_artifact_root=arguments.secondary_artifact_root,
            secondary_manifest_path=arguments.secondary_manifest,
            pin_db_path=arguments.pin_db,
        )
    )
    output = {
        "decision": "ACCEPTED" if decision.accepted else "NOT_ACCEPTED",
        "integrity_pass": decision.integrity_pass,
        "reason_codes": list(decision.reason_codes),
        "receipt_digest": decision.receipt_digest,
        "semantic_pass": decision.semantic_pass,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0 if decision.accepted else 2


if __name__ == "__main__":
    sys.exit(main())
