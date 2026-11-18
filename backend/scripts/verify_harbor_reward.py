"""
Harbor Verifier Reward Extraction & Verification CLI Script — Day 12 Step 3.

Reads Harbor evaluation output from a specified jobs directory,
extracts the verifier reward score from TrialResult/JobResult artifacts,
validates the score against expected thresholds, and records the score
to GitHub Actions step outputs.

Zero untrusted code is executed on the host.
"""

import argparse
import os
from pathlib import Path
import sys

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.harbor_service import find_and_extract_harbor_reward


def record_github_output(score: float) -> None:
    """Safely appends reward_score to GITHUB_OUTPUT if available."""
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out and os.path.exists(gh_out):
        with open(gh_out, "a", encoding="utf-8") as out:
            out.write(f"reward_score={score}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Harbor trial execution results and verifier reward protocol."
    )
    parser.add_argument(
        "--jobs-dir",
        type=Path,
        default=Path("harbor_jobs"),
        help="Path to Harbor jobs directory containing evaluation results.",
    )
    parser.add_argument(
        "--expected-reward",
        type=float,
        default=1.0,
        help="Expected numeric reward for Oracle verification (default: 1.0).",
    )
    args = parser.parse_args()

    jobs_dir = args.jobs_dir.resolve()
    print(f"=== Inspecting Harbor Evaluation Results under: {jobs_dir} ===")

    score, source_file, key_path = find_and_extract_harbor_reward(jobs_dir)

    print(f"Matched Result Source : {source_file or 'None'}")
    print(f"Matched Key Path / Ref: {key_path}")
    print(f"Recorded Reward Score : {score}")

    if score is None:
        print(
            f"ERROR: Verifier reward score could not be determined from Harbor results: {key_path}",
            file=sys.stderr,
        )
        return 1

    record_github_output(score)

    if float(score) != args.expected_reward:
        print(
            f"ERROR: Oracle verification failed. Expected reward {args.expected_reward}, got {score}",
            file=sys.stderr,
        )
        return 1

    print(f"SUCCESS: Oracle evaluation verified with reward {score}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
