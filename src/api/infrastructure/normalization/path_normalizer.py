"""URL path normalization for deduplication"""
import re
from urllib.parse import urlparse, parse_qs, urlencode
from typing import Dict, Any


class PathNormalizer:
    """Normalize URL paths for deduplication (urldedupe-like logic)"""
    
    # Patterns for parameter value normalization
    UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)
    MD5_PATTERN = re.compile(r'\b[0-9a-f]{32}\b', re.IGNORECASE)
    SHA1_PATTERN = re.compile(r'\b[0-9a-f]{40}\b', re.IGNORECASE)
    SHA256_PATTERN = re.compile(r'\b[0-9a-f]{64}\b', re.IGNORECASE)
    NUMERIC_PATTERN = re.compile(r'^\d+$')
    
    @classmethod
    def normalize_path(cls, url: str) -> str:
        """
        Normalize URL path for deduplication
        
        Example:
            /api/users/123/profile -> /api/users/{id}/profile
            /api/posts/abc-def-ghi-jkl/comments -> /api/posts/{uuid}/comments
        """
        parsed = urlparse(url)
        path = parsed.path
        
        # Split path into segments
        segments = [s for s in path.split('/') if s]
        
        # Normalize each segment
        normalized_segments = []
        for segment in segments:
            normalized_segments.append(cls._normalize_segment(segment))
        
        # Reconstruct path
        normalized_path = '/' + '/'.join(normalized_segments) if normalized_segments else '/'
        
        return normalized_path
    
    @classmethod
    def _normalize_segment(cls, segment: str) -> str:
        """Normalize a single path segment"""
        # UUID
        if cls.UUID_PATTERN.fullmatch(segment):
            return '{uuid}'
        
        # SHA256
        if cls.SHA256_PATTERN.fullmatch(segment):
            return '{sha256}'
        
        # SHA1
        if cls.SHA1_PATTERN.fullmatch(segment):
            return '{sha1}'
        
        # MD5
        if cls.MD5_PATTERN.fullmatch(segment):
            return '{md5}'
        
        # Numeric ID
        if cls.NUMERIC_PATTERN.fullmatch(segment):
            return '{id}'
        
        # Keep as-is
        return segment
    
    @classmethod
    def normalize_query_params(cls, url: str) -> Dict[str, str]:
        """
        Normalize query parameters (keep param names, normalize values)
        
        Returns dict of param_name -> normalized_value_type
        """
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        normalized = {}
        for key, values in params.items():
            if not values:
                normalized[key] = "empty"
                continue
            
            # Take first value
            value = values[0]
            normalized[key] = cls._classify_value(value)
        
        return normalized
    
    @classmethod
    def _classify_value(cls, value: str) -> str:
        """Classify parameter value type"""
        if not value:
            return "empty"
        
        if cls.UUID_PATTERN.fullmatch(value):
            return "uuid"
        
        if cls.SHA256_PATTERN.fullmatch(value):
            return "sha256"
        
        if cls.SHA1_PATTERN.fullmatch(value):
            return "sha1"
        
        if cls.MD5_PATTERN.fullmatch(value):
            return "md5"
        
        if cls.NUMERIC_PATTERN.fullmatch(value):
            return "numeric"
        
        if '@' in value:
            return "email"
        
        if value.lower() in ('true', 'false'):
            return "boolean"
        
        return "string"
