from typing import AsyncIterator, Protocol, List
from api.application.dto.httpx_raw_dto import HTTPXRawResultDTO

class HTTPXRunner(Protocol):
    async def run(
        self,
        targets: List[str] | str,
        timeout: int,
    ) -> AsyncIterator[HTTPXRawResultDTO]:
        ...
