"""Abstract repository interfaces - Domain layer contracts"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar
from uuid import UUID

from api.domain.models import AbstractModel

T = TypeVar('T', bound=AbstractModel)


class AbstractRepository(ABC, Generic[T]):  
    @abstractmethod
    async def get(self, id: UUID) -> Optional[T]:  
        raise NotImplementedError
    
    @abstractmethod
    async def get_by_fields(self, **filters) -> Optional[T]:  
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
    async def create(self, entity: T) -> T: 
        raise NotImplementedError
    
    @abstractmethod
    async def update(self, id: UUID, entity: T) -> T:  
        raise NotImplementedError
       
    @abstractmethod
    async def delete(self, id: UUID) -> None:
        raise NotImplementedError
    
    @abstractmethod
    async def get_or_create(
        self,
        entity: T,  
    ) -> Tuple[T, bool]:  
        raise NotImplementedError
    
    @abstractmethod
    async def upsert(
        self,
        entity: T,
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> T:  
        raise NotImplementedError
    
    @abstractmethod
    async def bulk_create(self, entities: List[T]) -> List[T]: 
        raise NotImplementedError
    
    @abstractmethod
    async def bulk_upsert(
        self,
        entities: List[T],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> None:
        raise NotImplementedError