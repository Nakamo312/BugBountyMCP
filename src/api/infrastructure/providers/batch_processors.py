from dishka import Provider, Scope, from_context, provide

from api.application.pipeline.canonical_processor import (
    CanonicalBatchProcessor,
    ServiceFindingBatchProcessor,
    UrlEvidenceBatchProcessor,
)
from api.application.services.batch_processor import (
    ASNMapBatchProcessor,
    AmassBatchProcessor,
    DNSxBatchProcessor,
    HTTPXBatchProcessor,
    MantraBatchProcessor,
    MapCIDRBatchProcessor,
    PlaywrightBatchProcessor,
    SmapBatchProcessor,
    SubjackBatchProcessor,
    TLSxBatchProcessor,
)
from api.config import Settings


class BatchProcessorProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_canonical_processor(self, settings: Settings) -> CanonicalBatchProcessor:
        return CanonicalBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_httpx_processor(self, settings: Settings) -> HTTPXBatchProcessor:
        return HTTPXBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_url_evidence_processor(self, settings: Settings) -> UrlEvidenceBatchProcessor:
        return UrlEvidenceBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_mantra_processor(self, settings: Settings) -> MantraBatchProcessor:
        return MantraBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_dnsx_processor(self, settings: Settings) -> DNSxBatchProcessor:
        return DNSxBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_subjack_processor(self, settings: Settings) -> SubjackBatchProcessor:
        return SubjackBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_asnmap_processor(self, settings: Settings) -> ASNMapBatchProcessor:
        return ASNMapBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_amass_processor(self, settings: Settings) -> AmassBatchProcessor:
        return AmassBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_service_finding_processor(self, settings: Settings) -> ServiceFindingBatchProcessor:
        return ServiceFindingBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_tlsx_processor(self, settings: Settings) -> TLSxBatchProcessor:
        return TLSxBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_mapcidr_processor(self, settings: Settings) -> MapCIDRBatchProcessor:
        return MapCIDRBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_smap_processor(self, settings: Settings) -> SmapBatchProcessor:
        return SmapBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_playwright_processor(self, settings: Settings) -> PlaywrightBatchProcessor:
        return PlaywrightBatchProcessor(settings)
