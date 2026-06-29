from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.contracts import IngestContext
from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor


@pytest.mark.asyncio
async def test_linkfinder_ingestor_returns_referenced_urls_without_materialization() -> None:
    program_id = uuid4()
    context = IngestContext(
        job_id=uuid4(),
        run_id=uuid4(),
        correlation_id=uuid4(),
        raw_artifact_id=uuid4(),
    )
    ingestor = LinkFinderResultIngestor()

    result = await ingestor.ingest(
        program_id,
        [
            {
                "host": "api.example.com",
                "source_js": "https://app.example.com/static/app.js?v=123",
                "urls": [
                    "https://api.example.com/v1/users/123?debug=true",
                    "https://api.example.com/v1/users/123?debug=true",
                ],
            }
        ],
        context=context,
    )

    assert result.urls == ["https://api.example.com/v1/users/123?debug=true"]
    assert result.raw_domains == []


@pytest.mark.asyncio
async def test_linkfinder_ingestor_handles_missing_source_js_as_url_evidence() -> None:
    ingestor = LinkFinderResultIngestor()

    result = await ingestor.ingest(
        uuid4(),
        [{"host": "api.example.com", "urls": ["https://api.example.com/v1/users"]}],
        context=IngestContext(run_id=uuid4(), raw_artifact_id=uuid4()),
    )

    assert result.urls == ["https://api.example.com/v1/users"]
