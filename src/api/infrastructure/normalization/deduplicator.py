"""Deduplication logic"""
from typing import List, Set, TypeVar, Callable, Any
from hashlib import sha256

T = TypeVar('T')


class Deduplicator:
    """Generic deduplication utilities"""
    
    @staticmethod
    def deduplicate_by_key(
        items: List[T],
        key_func: Callable[[T], Any]
    ) -> List[T]:
        """
        Deduplicate list by key function
        
        Args:
            items: List of items to deduplicate
            key_func: Function to extract unique key from item
            
        Returns:
            Deduplicated list (preserves first occurrence)
        """
        seen: Set[Any] = set()
        result: List[T] = []
        
        for item in items:
            key = key_func(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
        
        return result
    
    @staticmethod
    def hash_data(data: str) -> str:
        """Generate SHA256 hash for deduplication"""
        return sha256(data.encode('utf-8')).hexdigest()
    
    @staticmethod
    def deduplicate_hosts(hosts: List[str]) -> List[str]:
        """Deduplicate host list (case-insensitive)"""
        seen: Set[str] = set()
        result: List[str] = []
        
        for host in hosts:
            normalized = host.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(host)
        
        return result
    
    @staticmethod
    def deduplicate_ips(ips: List[str]) -> List[str]:
        """Deduplicate IP address list"""
        return list(dict.fromkeys(ip.strip() for ip in ips if ip.strip()))
