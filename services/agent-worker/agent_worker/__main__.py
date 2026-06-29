from __future__ import annotations

import argparse
import asyncio
import logging
from uuid import UUID

from agent_worker.client import AgentControlPlaneClient
from agent_worker.runtime import build_agent_task_runtime
from agent_worker.settings import AgentWorkerSettings
from agent_worker.worker import LangGraphAgentTaskWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph agent-task worker")
    parser.add_argument("command", choices=("run-once", "loop"), nargs="?", default="loop")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_amain(args.command))


async def _amain(command: str) -> None:
    settings = AgentWorkerSettings()
    if not settings.AGENT_WORKER_PROGRAM_ID.strip():
        raise SystemExit("AGENT_WORKER_PROGRAM_ID must be set to a program UUID")
    client = AgentControlPlaneClient(
        base_url=settings.CONTROL_API_BASE_URL,
        actor=settings.AGENT_WORKER_ACTOR,
        internal_token=settings.AGENT_PROTOCOL_INTERNAL_TOKEN,
    )
    try:
        runtime = build_agent_task_runtime(settings=settings, client=client)
        worker = LangGraphAgentTaskWorker(
            client=client,
            runtime=runtime,
            program_id=UUID(settings.AGENT_WORKER_PROGRAM_ID),
            campaign_id=UUID(settings.AGENT_WORKER_CAMPAIGN_ID) if settings.AGENT_WORKER_CAMPAIGN_ID else None,
            consumer_id=settings.AGENT_WORKER_CONSUMER_ID,
            claim_limit=settings.AGENT_WORKER_CLAIM_LIMIT,
            lease_seconds=settings.AGENT_WORKER_LEASE_SECONDS,
        )
        if command == "run-once":
            sweep = await worker.process_once()
            print(
                f"claimed={sweep.claimed} processed={sweep.processed} failed={sweep.failed}"
            )
        else:
            await worker.run_forever(poll_seconds=settings.AGENT_WORKER_POLL_SECONDS)
    finally:
        await client.aclose()


if __name__ == "__main__":
    main()
