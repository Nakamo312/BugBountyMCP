"""Host repository"""

from uuid import UUID
from api.domain.models import HostModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.host import HostRepository



class SQLAlchemyHostRepository(SQLAlchemyAbstractRepository, HostRepository):
    model = HostModel

    async def ensure(
        self,
        program_id: UUID,
        host: str,
        in_scope: bool = True,
        cnames: list[str] | None = None,
    ) -> HostModel:

        entity = HostModel(
            program_id=program_id,
            host=host,
            in_scope=in_scope,
            cname=cnames or []
        )

        return await self.upsert(
            entity,
            conflict_fields=["program_id", "host"],
            update_fields=["in_scope", "cname"]
        )
