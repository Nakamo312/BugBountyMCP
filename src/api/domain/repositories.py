"""Abstract repository interfaces - Domain layer contracts"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Tuple, Dict, Any
from uuid import UUID



class AbstractRepository(ABC):
    """Base repository interface"""
    
    @abstractmethod
    async def get(self, id: UUID) -> Optional[AbstractModel]:
        raise NotImplementedError

    
    @abstractmethod
    async def get_by_fields(self, **filters) -> Optional[AbstractModel]:
        raise NotImplementedError

    
    @abstractmethod
    async def find_many(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None
    ) -> List[T]:
        raise NotImplementedError

    
    @abstractmethod
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        raise NotImplementedError

    
    @abstractmethod
    async def create(self, data: Optional[AbstractModel]) -> Optional[AbstractModel]:
        raise NotImplementedError

    
    @abstractmethod
    async def update(self, id: UUID, data: Dict[str, Any]) -> Optional[AbstractModel]:
        raise NotImplementedError

    
    @abstractmethod
    async def delete(self, id: UUID) -> None:
        raise NotImplementedError

    
    @abstractmethod
    async def get_or_create(
        self,
        defaults: Optional[AbstractModel] = None,
        **filters
    ) -> Tuple[AbstractModel, bool]:
        raise NotImplementedError

    
    @abstractmethod
    async def upsert(
        self,
        data: Dict[str, Any],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> AbstractModel:
        raise NotImplementedError

    
    @abstractmethod
    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[AbstractModel]:
        raise NotImplementedError

    
    @abstractmethod
    async def bulk_upsert(
        self,
        items: List[Dict[str, Any]],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> None:
        raise NotImplementedError