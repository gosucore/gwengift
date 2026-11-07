import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.services.disclosure_verification import DisclosureVerificationError, verify_disclosure_json
from app.services.disclosures import disclosure_package_hash


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independently verify a GwenGift disclosure")
    parser.add_argument("package", type=Path, help="Path to the downloaded canonical JSON package")
    args = parser.parse_args(argv)
    try:
        package_json = args.package.read_text(encoding="utf-8")
        package = verify_disclosure_json(package_json)
    except (OSError, DisclosureVerificationError) as exc:
        print(f"Disclosure verification failed: {exc}", file=sys.stderr)
        return 1
    completed_bets = sum(bet.state == "COMPLETED" for bet in package.bets)
    remaining_gifts = sum(gift.lifecycle == "AVAILABLE" for gift in package.gifts)
    print(
        json.dumps(
            {
                "completed_bets": completed_bets,
                "remaining_gifts": remaining_gifts,
                "round_id": package.round.id,
                "sha256": disclosure_package_hash(package_json),
                "valid": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
