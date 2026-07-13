import json
import sys

from market_research import analyze_file

if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "data.csv"
    description = sys.argv[2] if len(sys.argv) > 2 else None

    result = analyze_file(file_path, description=description)

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2)

    print("Domain:", result.data_profile.domain)
    print("Description generated:", result.data_profile.description_was_generated)
    print("Timeline:", result.data_profile.timeline)
    print("Mode:", result.market_research.mode)
    print("Key findings:", len(result.market_research.key_findings))
    print("Sources:", len(result.market_research.sources))
    if result.dag:
        print("DAG nodes:", len(result.dag.nodes), "edges:", len(result.dag.edges))
    else:
        print("DAG unavailable:", result.dag_unavailable_reason)
    print("\nFull output written to output.json")
