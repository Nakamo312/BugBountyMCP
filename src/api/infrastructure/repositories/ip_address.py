from typing import Optional
from uuid import UUID

from sqlalchemy import select
from api.infrastructure.database.models import IPAddressModel
from api.infrastructure.repositories.base_repo import BaseRepository


class IPAddressRepository(BaseRepository[IPAddressModel]):
    """PostgreSQL implementation of IPAddress repository"""

    model = IPAddressModel
    unique_fields = [('program_id', 'address')]

    async def find_by_address(
        self, program_id: UUID, address: str
    ) -> Optional[IPAddressModel]:
        """Find IP address by program and address"""
        return await self.get_by_unique_fields(program_id=program_id, address=address)