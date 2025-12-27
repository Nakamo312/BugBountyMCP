from api.application.dto.httpx_raw_dto import HTTPXRawResultDTO
from api.domain.models.httpx import HTTPXResult

class HTTPXResultMapper:
    def map(self, raw: HTTPXRawResultDTO) -> HTTPXResult | None:
        host = raw.host or raw.input
        if not host or not raw.host_ip:
            return None

        return HTTPXResult(
            host=host,
            primary_ip=raw.host_ip,
            extra_ips=raw.a,
            scheme=raw.scheme,
            port=raw.port,
            technologies={t: True for t in raw.tech},
            path=raw.path or "/",
            method=raw.method,
            status_code=raw.status_code,
        )
