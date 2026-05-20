"""Whitelisted pipeline component catalog for YAML node specs."""
from __future__ import annotations

from typing import Any

from api.application.services.batch_processor import (
    ASNMapBatchProcessor,
    DNSxBatchProcessor,
    GAUBatchProcessor,
    HTTPXBatchProcessor,
    Hakip2HostBatchProcessor,
    KatanaBatchProcessor,
    LinkFinderBatchProcessor,
    MantraBatchProcessor,
    MapCIDRBatchProcessor,
    NaabuBatchProcessor,
    PlaywrightBatchProcessor,
    SmapBatchProcessor,
    SubfinderBatchProcessor,
    SubjackBatchProcessor,
    TLSxBatchProcessor,
    WaymoreBatchProcessor,
)
from api.infrastructure.ingestors.amass_ingestor import AmassResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor
from api.infrastructure.ingestors.dnsx_ingestor import DNSxDiscoveryResultIngestor, DNSxResultIngestor
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.ingestors.host_ingestor import HostIngestor
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.infrastructure.ingestors.smap_ingestor import SmapResultIngestor
from api.infrastructure.ingestors.subjack_ingestor import SubjackResultIngestor
from api.infrastructure.ingestors.tlsx_ingestor import TLSxResultIngestor
from api.infrastructure.runners.amass_cli import AmassCliRunner
from api.infrastructure.runners.asnmap_cli import ASNMapCliRunner
from api.infrastructure.runners.dnsx_runners import DNSxDeepRunner, DNSxPtrRunner
from api.infrastructure.runners.ffuf_cli import FFUFCliRunner
from api.infrastructure.runners.gau_cli import GAUCliRunner
from api.infrastructure.runners.hakip2host_cli import Hakip2HostCliRunner
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.infrastructure.runners.linkfinder_cli import LinkFinderCliRunner
from api.infrastructure.runners.mantra_cli import MantraCliRunner
from api.infrastructure.runners.mapcidr_runners import MapCIDRExpandRunner
from api.infrastructure.runners.naabu_cli import NaabuCliRunner
from api.infrastructure.runners.playwright_cli import PlaywrightCliRunner
from api.infrastructure.runners.smap_cli import SmapCliRunner
from api.infrastructure.runners.subfinder_cli import SubfinderCliRunner
from api.infrastructure.runners.subjack_cli import SubjackCliRunner
from api.infrastructure.runners.tlsx_runners import TLSxDefaultRunner
from api.infrastructure.runners.waymore_cli import WaymoreCliRunner


RUNNERS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        AmassCliRunner,
        ASNMapCliRunner,
        DNSxDeepRunner,
        DNSxPtrRunner,
        FFUFCliRunner,
        GAUCliRunner,
        Hakip2HostCliRunner,
        HTTPXCliRunner,
        KatanaCliRunner,
        LinkFinderCliRunner,
        MantraCliRunner,
        MapCIDRExpandRunner,
        NaabuCliRunner,
        PlaywrightCliRunner,
        SmapCliRunner,
        SubfinderCliRunner,
        SubjackCliRunner,
        TLSxDefaultRunner,
        WaymoreCliRunner,
    )
}

PROCESSORS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        ASNMapBatchProcessor,
        DNSxBatchProcessor,
        GAUBatchProcessor,
        HTTPXBatchProcessor,
        Hakip2HostBatchProcessor,
        KatanaBatchProcessor,
        LinkFinderBatchProcessor,
        MantraBatchProcessor,
        MapCIDRBatchProcessor,
        NaabuBatchProcessor,
        PlaywrightBatchProcessor,
        SmapBatchProcessor,
        SubfinderBatchProcessor,
        SubjackBatchProcessor,
        TLSxBatchProcessor,
        WaymoreBatchProcessor,
    )
}

INGESTORS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        AmassResultIngestor,
        ASNMapResultIngestor,
        DNSxDiscoveryResultIngestor,
        DNSxResultIngestor,
        FFUFResultIngestor,
        HostIngestor,
        HTTPXResultIngestor,
        KatanaResultIngestor,
        LinkFinderResultIngestor,
        MantraResultIngestor,
        NaabuResultIngestor,
        SmapResultIngestor,
        SubjackResultIngestor,
        TLSxResultIngestor,
    )
}


def resolve_component(catalog: dict[str, type[Any]], name: str | None, field_name: str, node_id: str):
    if name is None:
        return None
    try:
        return catalog[name]
    except KeyError as exc:
        known = ", ".join(sorted(catalog))
        raise ValueError(
            f"Unknown {field_name} '{name}' for pipeline node '{node_id}'. "
            f"Known values: {known}"
        ) from exc
