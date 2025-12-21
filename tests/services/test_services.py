# """
# Unit tests for SubdomainScanService
# """
# import pytest
# from unittest.mock import AsyncMock, MagicMock
# from uuid import uuid4


# from api.application.services.subfinder import SubdomainScanService
# from api.infrastructure.repositories.host import PostgresHostRepository


# # =================== FIXTURES ===================

# @pytest.fixture
# def program_id():
#     return str(uuid4())


# @pytest.fixture
# def host_repository():
#     repo = AsyncMock(spec=PostgresHostRepository)
#     repo.bulk_upsert.return_value = {
#         "created": 2,
#         "existing": 1
#     }
#     return repo


# @pytest.fixture
# def service(host_repository):
#     return SubdomainScanService(host_repository)


# # =================== TESTS ===================

# @pytest.mark.asyncio
# class TestSubdomainScanService:

#     async def test_execute_scan_filters_and_yields_domains(self, service):
#         fake_output = [
#             "test.example.com",
#             "invalid_domain",
#             "api.example.com",
#             ""
#         ]

#         async def fake_stream(*args, **kwargs):
#             for line in fake_output:
#                 yield line

#         service.exec_stream = fake_stream

#         result = []
#         async for domain in service.execute_scan("example.com"):
#             result.append(domain)

#         assert result == [
#             "test.example.com",
#             "api.example.com"
#         ]

#     async def test_parse_and_save_calls_repository_correctly(
#         self, service, host_repository, program_id
#     ):
#         async def fake_scan(*args, **kwargs):
#             yield "a.example.com"
#             yield "b.example.com"
#             yield "a.example.com"  

#         service.execute_scan = fake_scan

#         result = await service.parse_and_save(
#             program_id=program_id,
#             target="example.com"
#         )

#         host_repository.bulk_upsert.assert_awaited_once()

#         call_kwargs = host_repository.bulk_upsert.call_args.kwargs
#         assert call_kwargs["program_id"]
#         assert call_kwargs["in_scope"] is True
#         assert set(call_kwargs["hosts"]) == {
#             "a.example.com",
#             "b.example.com"
#         }

#         assert result["scanner"] == "SubdomainScanService"
#         assert result["target"] == "example.com"
#         assert result["total_found"] == 3
#         assert result["new"] == 2
#         assert result["existing"] == 1
#         assert len(result["subdomains"]) == 3
