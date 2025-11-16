"""
DSpace REST API client with secure authentication and request handling
"""

import logging
from typing import Optional, Dict, Any
from urllib.parse import urljoin, quote

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..config import Config
from ..validators import validate_uuid
from .exceptions import (
    DSpaceAPIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

logger = logging.getLogger(__name__)


class DSpaceClient:
    """
    Secure DSpace REST API client with authentication and error handling
    """

    def __init__(
        self,
        api_url: str = None,
        username: str = None,
        password: str = None,
    ):
        """
        Initialize DSpace client

        Args:
            api_url: DSpace REST API base URL (defaults to config)
            username: DSpace username (defaults to config)
            password: DSpace password (defaults to config)
        """
        self.api_url = api_url or Config.REPOSITORY_API_URL
        self.username = username or Config.REPOSITORY_USER
        self.password = password or Config.REPOSITORY_PASSWORD

        # Ensure API URL ends with /
        if not self.api_url.endswith('/'):
            self.api_url += '/'

        # Session for connection pooling and cookie management
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache',
        })

        # Authentication tokens
        self.bearer_token: Optional[str] = None
        self.csrf_token: Optional[str] = None

    def authenticate(self) -> bool:
        """
        Authenticate with DSpace API and get bearer token

        Returns:
            True if authentication successful

        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            login_url = urljoin(self.api_url, 'authn/login')

            response = self.session.post(
                login_url,
                auth=(self.username, self.password),
                timeout=Config.REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                # Extract bearer token from response
                self.bearer_token = response.headers.get('Authorization')

                # Extract CSRF token if present
                csrf_cookie = response.cookies.get('DSPACE-XSRF-COOKIE')
                if csrf_cookie:
                    self.csrf_token = csrf_cookie
                    self.session.headers.update({
                        'X-XSRF-TOKEN': self.csrf_token,
                    })

                # Update session with bearer token
                if self.bearer_token:
                    self.session.headers.update({
                        'Authorization': self.bearer_token,
                    })

                logger.info("Successfully authenticated with DSpace API")
                return True
            else:
                raise AuthenticationError(
                    f"Authentication failed with status {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text,
                )

        except requests.RequestException as e:
            raise AuthenticationError(f"Authentication request failed: {e}") from e

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response and raise appropriate exceptions

        Args:
            response: Response object from requests

        Returns:
            Dictionary with status and response data

        Raises:
            Various DSpaceAPIError subclasses based on status code
        """
        # Update tokens if present in response headers
        if 'Authorization' in response.headers:
            self.bearer_token = response.headers['Authorization']
            self.session.headers.update({
                'Authorization': self.bearer_token,
            })

        csrf_cookie = response.cookies.get('DSPACE-XSRF-COOKIE')
        if csrf_cookie:
            self.csrf_token = csrf_cookie
            self.session.headers.update({
                'X-XSRF-TOKEN': self.csrf_token,
            })

        # Handle different status codes
        if response.status_code == 200:
            return {
                'status': 'success',
                'body': response.content,
                'headers': dict(response.headers),
                'status_code': response.status_code,
            }
        elif response.status_code == 401:
            raise AuthenticationError(
                "Authentication required or token expired",
                status_code=response.status_code,
                response_body=response.text,
            )
        elif response.status_code == 404:
            raise NotFoundError(
                "Resource not found",
                status_code=response.status_code,
                response_body=response.text,
            )
        elif response.status_code == 429:
            raise RateLimitError(
                "API rate limit exceeded",
                status_code=response.status_code,
                response_body=response.text,
            )
        elif 500 <= response.status_code < 600:
            raise ServerError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )
        else:
            raise DSpaceAPIError(
                f"API request failed with status {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((RateLimitError, ServerError, requests.RequestException)),
        reraise=True,
    )
    def get_bitstream_content(
        self,
        bitstream_uuid: str,
        short_lived_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get bitstream content from DSpace API with validation

        Args:
            bitstream_uuid: UUID of the bitstream (validated)
            short_lived_token: Optional short-lived authentication token

        Returns:
            Dictionary with status, body, and headers

        Raises:
            InvalidUUIDError: If UUID is invalid
            DSpaceAPIError: If API request fails
        """
        # Validate UUID to prevent injection
        validated_uuid = validate_uuid(bitstream_uuid)

        # URL-encode the UUID (though it should be safe after validation)
        encoded_uuid = quote(validated_uuid, safe='')

        # Build the URL safely
        endpoint = f'core/bitstreams/{encoded_uuid}/content'

        # Add short-lived token if provided
        if short_lived_token:
            # Validate token format (basic check)
            if not short_lived_token.replace('-', '').replace('_', '').isalnum():
                raise ValueError("Invalid short-lived token format")

            endpoint += f'?authentication-token={quote(short_lived_token, safe="")}'

        url = urljoin(self.api_url, endpoint)

        logger.debug(f"Fetching bitstream content: {bitstream_uuid}")

        try:
            # Attempt authentication if not already authenticated
            if not self.bearer_token and not short_lived_token:
                self.authenticate()

            response = self.session.get(
                url,
                timeout=Config.REQUEST_TIMEOUT,
            )

            return self._handle_response(response)

        except requests.RequestException as e:
            logger.error(f"Request failed for bitstream {bitstream_uuid}: {e}")
            raise DSpaceAPIError(f"Request failed: {e}") from e

    def close(self):
        """Close the session"""
        self.session.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session"""
        self.close()
