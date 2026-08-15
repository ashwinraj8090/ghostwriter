#!/usr/bin/env python3
"""
Pre-seed approval history for a sender so the trust-calibration moment is
visible in a single demo take, instead of approving five real emails live.

Usage:
    python demo/seed_trust.py someone@example.com 5
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghostwriter.config import config
from ghostwriter.storage import Storage


def main():
    if len(sys.argv) != 3:
        print("Usage: python demo/seed_trust.py <sender-email> <approved-count>")
        sys.exit(1)

    sender, count = sys.argv[1], int(sys.argv[2])
    storage = Storage(config.STATE_FILE)
    for _ in range(count):
        storage.record_decision(sender, "approved")

    score = storage.trust_score(sender)
    print(f"Seeded {sender}: {score}")
    print(
        f"Trusted (>= {config.TRUST_AUTO_SEND_THRESHOLD} approvals)? "
        f"{storage.is_trusted(sender, config.TRUST_AUTO_SEND_THRESHOLD)}"
    )


if __name__ == "__main__":
    main()
