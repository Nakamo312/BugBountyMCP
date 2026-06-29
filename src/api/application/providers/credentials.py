from typing import Iterable

from dishka import Provider, Scope, from_context, provide
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from api.application.credential_management import CredentialManagementService
from api.application.credential_secret_versions import CredentialSecretVersionService
from api.config import Settings
from api.infrastructure.credential_store import PostgresCredentialStore
from api.infrastructure.credentials.factory import build_postgres_credential_store


class CredentialProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_credential_sync_engine(self, settings: Settings) -> Iterable[Engine]:
        engine = create_engine(settings.postgres_dsn_sync, future=True)
        try:
            yield engine
        finally:
            engine.dispose()

    @provide(scope=Scope.REQUEST)
    def get_credential_connection(self, credential_engine: Engine) -> Iterable[Connection]:
        with credential_engine.begin() as connection:
            yield connection

    @provide(scope=Scope.REQUEST)
    def get_postgres_credential_store(
        self,
        credential_connection: Connection,
        settings: Settings,
    ) -> PostgresCredentialStore:
        return build_postgres_credential_store(credential_connection, settings)

    @provide(scope=Scope.REQUEST)
    def get_credential_secret_version_service(
        self,
        store: PostgresCredentialStore,
    ) -> CredentialSecretVersionService:
        return CredentialSecretVersionService(registry=store, secret_store=store)

    @provide(scope=Scope.REQUEST)
    def get_credential_management_service(
        self,
        store: PostgresCredentialStore,
        secret_versions: CredentialSecretVersionService,
    ) -> CredentialManagementService:
        return CredentialManagementService(registry=store, secret_versions=secret_versions)
