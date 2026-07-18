import json
import sys

from insight_builder.orchestrator import run_pipeline


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_csv>")
        sys.exit(1)

    result = run_pipeline(sys.argv[1])

    print(f"\nRows: {result['n_rows']}")
    print(f"Schema roles: {json.dumps(result['schema'], indent=2)}")
    print(
        f"\nCandidates generated: {result['n_candidates_generated']} "
        f"-> after triage: {result['n_candidates_after_triage']} "
        f"-> executed: {result['n_executed']} "
        f"-> validated: {result['n_validated']}"
    )
    print(f"Audit trail: {result['audit_dir']}\n")

    for i, insight in enumerate(result["insights"], start=1):
        print(f"{i}. {insight['narrative']}")


if __name__ == "__main__":
    main()
