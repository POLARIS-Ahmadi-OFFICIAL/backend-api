from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.agent_contract import AgentTask  # noqa: E402
from app.tools.polaris_orchestrator import PolarisOrchestrator  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("agent_id")
    parser.add_argument("action")
    parser.add_argument("--payload", default="{}")
    parser.add_argument("--query", nargs="+")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--stage")
    parser.add_argument("--max-papers", type=int)
    args = parser.parse_args()
    payload = json.loads(args.payload)
    if args.query:
        payload["query"] = " ".join(args.query)
    if args.limit is not None:
        payload["limit"] = args.limit
    if args.stage:
        payload["stage"] = args.stage
    if args.max_papers is not None:
        payload.setdefault("request", {})["max_papers"] = args.max_papers
    result = PolarisOrchestrator().dispatch(AgentTask(args.agent_id, args.action, payload))
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
