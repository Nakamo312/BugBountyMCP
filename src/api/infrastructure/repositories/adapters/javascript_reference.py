"""JavaScript reference repository adapters."""

from sqlalchemy.dialects.postgresql import insert

from api.domain.models import JavaScriptReferenceModel
from api.infrastructure.adapters.orm import graph_projection_events
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.javascript_reference import (
    JavaScriptReferenceRepository,
)


class SQLAlchemyJavaScriptReferenceRepository(
    SQLAlchemyAbstractRepository,
    JavaScriptReferenceRepository,
):
    """SQLAlchemy implementation for append-only JavaScript references."""

    model = JavaScriptReferenceModel

    async def create(self, entity: JavaScriptReferenceModel) -> JavaScriptReferenceModel:
        created = await super().create(entity)
        await self._enqueue_graph_projection_event(created)
        await self.session.flush()
        return created

    async def _enqueue_graph_projection_event(
        self,
        reference: JavaScriptReferenceModel,
    ) -> None:
        if reference.raw_artifact_id is None:
            return
        if reference.run_id is None:
            return

        dedupe_key = f"javascript-references-ready:{reference.raw_artifact_id}"
        statement = (
            insert(graph_projection_events)
            .values(
                program_id=reference.program_id,
                source_type="raw_artifact",
                source_id=reference.raw_artifact_id,
                event_type="javascript_references_ready",
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
        await self.session.execute(statement)
