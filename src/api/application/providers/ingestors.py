from dishka import Provider, Scope, from_context, provide

from api.config import Settings
from api.infrastructure.ingestors.amass_ingestor import AmassResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor
from api.infrastructure.ingestors.canonical_router import CanonicalIngestorRouter
from api.infrastructure.ingestors.dnsx_ingestor import DNSxDiscoveryResultIngestor, DNSxResultIngestor
from api.infrastructure.ingestors.fuzz_finding_ingestor import FuzzFindingIngestor
from api.infrastructure.ingestors.host_finding_ingestor import HostFindingIngestor
from api.infrastructure.ingestors.host_ingestor import HostIngestor
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import JavaScriptReferenceFindingIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.infrastructure.ingestors.service_finding_ingestor import ServiceFindingIngestor
from api.infrastructure.ingestors.smap_ingestor import SmapResultIngestor
from api.infrastructure.ingestors.subjack_ingestor import SubjackResultIngestor
from api.infrastructure.ingestors.tlsx_ingestor import TLSxResultIngestor
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor
from api.infrastructure.unit_of_work.adapters.asnmap import SQLAlchemyASNMapUnitOfWork
from api.infrastructure.unit_of_work.adapters.dnsx import SQLAlchemyDNSxUnitOfWork
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.infrastructure import SQLAlchemyInfrastructureUnitOfWork
from api.infrastructure.unit_of_work.adapters.katana import SQLAlchemyKatanaUnitOfWork
from api.infrastructure.unit_of_work.adapters.mantra import SQLAlchemyMantraUnitOfWork
from api.infrastructure.unit_of_work.adapters.naabu import SQLAlchemyNaabuUnitOfWork


class IngestorProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.REQUEST)
    def get_httpx_ingestor(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork,
        settings: Settings
    ) -> HTTPXResultIngestor:
        return HTTPXResultIngestor(uow=scan_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_katana_ingestor(
        self,
        katana_uow: SQLAlchemyKatanaUnitOfWork,
        settings: Settings,
    ) -> KatanaResultIngestor:
        return KatanaResultIngestor(uow=katana_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_linkfinder_ingestor(self) -> LinkFinderResultIngestor:
        return LinkFinderResultIngestor()

    @provide(scope=Scope.REQUEST)
    def get_mantra_ingestor(
        self,
        mantra_uow: SQLAlchemyMantraUnitOfWork
    ) -> MantraResultIngestor:
        return MantraResultIngestor(uow=mantra_uow)

    @provide(scope=Scope.REQUEST)
    def get_dnsx_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> DNSxResultIngestor:
        return DNSxResultIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_dnsx_discovery_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> DNSxDiscoveryResultIngestor:
        return DNSxDiscoveryResultIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_subjack_ingestor(
        self,
        httpx_uow: SQLAlchemyHTTPXUnitOfWork,
        settings: Settings
    ) -> SubjackResultIngestor:
        return SubjackResultIngestor(uow=httpx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_asnmap_ingestor(
        self,
        asnmap_uow: SQLAlchemyASNMapUnitOfWork,
        settings: Settings
    ) -> ASNMapResultIngestor:
        return ASNMapResultIngestor(uow=asnmap_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_naabu_ingestor(
        self,
        naabu_uow: SQLAlchemyNaabuUnitOfWork,
        settings: Settings
    ) -> NaabuResultIngestor:
        return NaabuResultIngestor(uow=naabu_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_smap_ingestor(
        self,
        naabu_uow: SQLAlchemyNaabuUnitOfWork,
        settings: Settings
    ) -> SmapResultIngestor:
        return SmapResultIngestor(uow=naabu_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_tlsx_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> TLSxResultIngestor:
        return TLSxResultIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_amass_ingestor(
        self,
        infrastructure_uow: SQLAlchemyInfrastructureUnitOfWork,
        settings: Settings
    ) -> AmassResultIngestor:
        return AmassResultIngestor(uow=infrastructure_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_host_finding_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings,
    ) -> HostFindingIngestor:
        return HostFindingIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_url_finding_ingestor(self) -> UrlFindingIngestor:
        return UrlFindingIngestor()

    @provide(scope=Scope.REQUEST)
    def get_javascript_reference_finding_ingestor(self) -> JavaScriptReferenceFindingIngestor:
        return JavaScriptReferenceFindingIngestor()

    @provide(scope=Scope.REQUEST)
    def get_fuzz_finding_ingestor(self) -> FuzzFindingIngestor:
        return FuzzFindingIngestor()

    @provide(scope=Scope.REQUEST)
    def get_service_finding_ingestor(
        self,
        naabu_uow: SQLAlchemyNaabuUnitOfWork,
        settings: Settings,
    ) -> ServiceFindingIngestor:
        return ServiceFindingIngestor(
            uow=naabu_uow,
            batch_size=settings.NAABU_INGESTOR_BATCH_SIZE,
        )

    @provide(scope=Scope.REQUEST)
    def get_canonical_ingestor_router(
        self,
        host_findings: HostFindingIngestor,
        url_findings: UrlFindingIngestor,
        javascript_references: JavaScriptReferenceFindingIngestor,
        fuzz_findings: FuzzFindingIngestor,
        service_findings: ServiceFindingIngestor,
    ) -> CanonicalIngestorRouter:
        return CanonicalIngestorRouter(
            host_findings=host_findings,
            url_findings=url_findings,
            javascript_references=javascript_references,
            fuzz_findings=fuzz_findings,
            service_findings=service_findings,
        )

    @provide(scope=Scope.REQUEST)
    def get_host_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> HostIngestor:
        return HostIngestor(uow=dnsx_uow, settings=settings)
