"""
Custom exceptions for DSpace API interactions
"""


class DSpaceAPIError(Exception):
    """Base exception for DSpace API errors"""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


class AuthenticationError(DSpaceAPIError):
    """Raised when authentication fails"""
    pass


class NotFoundError(DSpaceAPIError):
    """Raised when requested resource is not found (404)"""
    pass


class RateLimitError(DSpaceAPIError):
    """Raised when API rate limit is exceeded (429)"""
    pass


class ServerError(DSpaceAPIError):
    """Raised when server returns 5xx error"""
    pass
