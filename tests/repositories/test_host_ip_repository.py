import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.database.models import HostIPModel
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.host_ip import HostIPRepository
from api.infrastructure.repositories.ip_address import IPAddressRepository


@pytest.mark.asyncio
class TestHostIPRepository:
    
    async def test_link_host_ip(self, session, program):
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        link_repo = HostIPRepository(session)
        
        host = await host_repo.create({
            'program_id': program.id,
            'host': 'example.com'
        })
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        await session.commit()
        
        link = await link_repo.link(host.id, ip.id, 'dns')
        assert link is not None
        assert link.source == 'dns'
    
    async def test_duplicate_link(self, session, program):
     
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        link_repo = HostIPRepository(session)
        
        host = await host_repo.create({
            'program_id': program.id,
            'host': 'example.com'
        })
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        await session.commit()
        
        await link_repo.link(host.id, ip.id, 'dns')
        await session.commit()
        
        # Second link should return None (already exists)
        second_link = await link_repo.link(host.id, ip.id, 'nmap')
        assert second_link is None
