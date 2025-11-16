"""
DSpace API client module
"""

from .client import DSpaceClient
from .exceptions import (
    DSpaceAPIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

__all__ = [
    'DSpaceClient',
    'DSpaceAPIError',
    'AuthenticationError',
    'NotFoundError',
    'RateLimitError',
]
