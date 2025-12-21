"""Abstract repository interfaces - Domain layer contracts"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Tuple, Dict, Any
from uuid import UUID

# Generic type for entities
T = TypeVar('T')


class IBaseRepository(ABC, Generic[T]):
    """Base repository interface"""
    
    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[T]:
        """Get entity by ID"""
        pass
    
    @abstractmethod
    async def get_by_fields(self, **filters) -> Optional[T]:
        """Get entity by arbitrary fields"""
        pass
    
    @abstractmethod
    async def find_many(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None
    ) -> List[T]:
        """Find multiple entities with pagination"""
        pass
    
    @abstractmethod
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count entities matching filters"""
        pass
    
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> T:
        """Create new entity"""
        pass
    
    @abstractmethod
    async def update(self, id: UUID, data: Dict[str, Any]) -> T:
        """Update entity by ID"""
        pass
    
    @abstractmethod
    async def delete(self, id: UUID) -> None:
        """Delete entity by ID"""
        pass
    
    @abstractmethod
    async def get_or_create(
        self,
        defaults: Optional[Dict[str, Any]] = None,
        **filters
    ) -> Tuple[T, bool]:
        """Get existing or create new entity"""
        pass
    
    @abstractmethod
    async def upsert(
        self,
        data: Dict[str, Any],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> T:
        """Insert or update entity"""
        pass
    
    @abstractmethod
    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[T]:
        """Create multiple entities"""
        pass
    
    @abstractmethod
    async def bulk_upsert(
        self,
        items: List[Dict[str, Any]],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> None:
        """Bulk insert or update"""
        pass


class IProgramRepository(IBaseRepository):
    """Program repository interface"""
    pass


class IScopeRuleRepository(IBaseRepository):
    """Scope rule repository interface"""
    pass


class IRootInputRepository(IBaseRepository):
    """Root input repository interface"""
    pass


class IHostRepository(IBaseRepository):
    """Host repository interface"""
    pass


class IIPAddressRepository(IBaseRepository):
    """IP address repository interface"""
    pass


class IHostIPRepository(IBaseRepository):
    """Host-IP mapping repository interface"""
    
    @abstractmethod
    async def link(self, host_id: UUID, ip_id: UUID, source: str) -> Any:
        """Link host to IP address"""
        pass


class IServiceRepository(IBaseRepository):
    """Service repository interface"""
    
    @abstractmethod
    async def get_or_create_with_tech(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: Dict[str, bool]
    ) -> Any:
        """Get or create service and merge technologies"""
        pass


class IEndpointRepository(IBaseRepository):
    """Endpoint repository interface"""
    
    @abstractmethod
    async def upsert_with_method(
        self,
        host_id: UUID,
        service_id: UUID,
        path: str,
        method: str,
        normalized_path: str,
        status_code: Optional[int] = None,
        **kwargs
    ) -> Any:
        """Upsert endpoint and add HTTP method"""
        pass


class IInputParameterRepository(IBaseRepository):
    """Input parameter repository interface"""
    pass


class IHeaderRepository(IBaseRepository):
    """Header repository interface"""
    pass


class IVulnTypeRepository(IBaseRepository):
    """Vulnerability type repository interface"""
    pass


class ILeakTypeRepository(IBaseRepository):
    """Leak type repository interface"""
    pass


class IScannerTemplateRepository(IBaseRepository):
    """Scanner template repository interface"""
    pass


class IScannerExecutionRepository(IBaseRepository):
    """Scanner execution repository interface"""
    pass


class IPayloadRepository(IBaseRepository):
    """Payload repository interface"""
    pass


class IFindingRepository(IBaseRepository):
    """Finding repository interface"""
    pass


class ILeakRepository(IBaseRepository):
    """Leak repository interface"""
    pass
