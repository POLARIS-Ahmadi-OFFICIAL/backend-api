"""CLI for POLARIS to operate and query LiteratureAgent."""

from __future__ import annotations

import argparse
import json

from literature_agent_service import LiteratureAgentConfig, LiteratureAgentService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("health")
    sub.add_parser("artifacts")
    jobs = sub.add_parser("jobs")
    jobs.add_argument("--job-id")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("job_id")
    search = sub.add_parser("search")
    search.add_argument("query", nargs="+")
    search.add_argument("--limit", type=int, default=8)
    context = sub.add_parser("context")
    context.add_argument("query", nargs="+")
    context.add_argument("--limit", type=int, default=5)
    run = sub.add_parser("run")
    run.add_argument("stage", choices=sorted({"extract_batch", "vision_pass", "sanitize_summaries", "integrate_and_model", "knowledge_graph"}))
    run.add_argument("--max-papers", type=int, default=100)
    run.add_argument("--search-query", nargs="+")
    run.add_argument("--run-model", action="store_true")
    run.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    service = LiteratureAgentService(LiteratureAgentConfig.load(args.config))
    if args.action == "health":
        result = service.health()
    elif args.action == "artifacts":
        result = service.artifact_manifest()
    elif args.action == "jobs":
        result = service.job_status(args.job_id) if args.job_id else [job.__dict__ for job in service.list_jobs()]
    elif args.action == "cancel":
        result = service.cancel_job(args.job_id)
    elif args.action == "search":
        result = service.search(" ".join(args.query), args.limit)
    elif args.action == "context":
        result = {"context": service.evidence_context(" ".join(args.query), args.limit)}
    else:
        request = {"max_papers": args.max_papers, "run_model": args.run_model}
        if args.search_query:
            request["search_query"] = " ".join(args.search_query)
        result = service.start_stage(args.stage, request, wait=args.wait)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
