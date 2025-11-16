"""
Input validation functions for IRTS SDAIA Export
Prevents injection attacks and validates data formats
"""

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID
from typing import Optional


class ValidationError(Exception):
    """Base exception for validation errors"""
    pass


class InvalidUUIDError(ValidationError):
    """Raised when UUID validation fails"""
    pass


class InvalidDateError(ValidationError):
    """Raised when date validation fails"""
    pass


class InvalidHandleError(ValidationError):
    """Raised when DSpace handle validation fails"""
    pass


class PathTraversalError(ValidationError):
    """Raised when path traversal attempt is detected"""
    pass


class InvalidMimeTypeError(ValidationError):
    """Raised when file MIME type is invalid"""
    pass


class FileSizeLimitError(ValidationError):
    """Raised when file exceeds size limit"""
    pass


def validate_uuid(uuid_string: str) -> str:
    """
    Validate that a string is a valid UUID

    Args:
        uuid_string: String to validate as UUID

    Returns:
        The validated UUID string

    Raises:
        InvalidUUIDError: If string is not a valid UUID
    """
    try:
        # This will raise ValueError if not a valid UUID
        UUID(uuid_string)
        return uuid_string
    except (ValueError, AttributeError, TypeError) as e:
        raise InvalidUUIDError(f"Invalid UUID format: {uuid_string}") from e


def validate_date(date_string: str, date_format: str = '%Y-%m-%d') -> str:
    """
    Validate that a string is a valid date in the expected format

    Args:
        date_string: String to validate as date
        date_format: Expected date format (default: YYYY-MM-DD)

    Returns:
        The validated date string

    Raises:
        InvalidDateError: If string is not a valid date
    """
    try:
        datetime.strptime(date_string, date_format)
        return date_string
    except (ValueError, TypeError) as e:
        raise InvalidDateError(
            f"Invalid date format: {date_string}. Expected format: {date_format}"
        ) from e


def validate_handle(handle: str) -> str:
    """
    Validate that a string is a valid DSpace handle (format: prefix/suffix)

    Args:
        handle: String to validate as DSpace handle

    Returns:
        The validated handle string

    Raises:
        InvalidHandleError: If string is not a valid handle
    """
    # DSpace handles are typically in format: 10754/123456
    pattern = r'^\d+/\d+$'

    if not re.match(pattern, handle):
        raise InvalidHandleError(
            f"Invalid DSpace handle format: {handle}. Expected format: prefix/suffix (e.g., 10754/123456)"
        )

    return handle


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing dangerous characters

    Args:
        filename: Filename to sanitize

    Returns:
        Sanitized filename
    """
    # Allow only alphanumeric, dots, hyphens, and underscores
    # This prevents path traversal and command injection
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '', filename)

    # Prevent leading dots (hidden files) or multiple dots (path traversal)
    sanitized = sanitized.lstrip('.')
    sanitized = re.sub(r'\.{2,}', '.', sanitized)

    return sanitized


def validate_safe_path(file_path: Path, allowed_directory: Path) -> Path:
    """
    Validate that a file path is within the allowed directory (prevents path traversal)

    Args:
        file_path: Path to validate
        allowed_directory: Directory that the path must be within

    Returns:
        The validated Path object

    Raises:
        PathTraversalError: If path attempts to escape the allowed directory
    """
    # Resolve to absolute paths
    try:
        resolved_path = file_path.resolve()
        allowed_dir = allowed_directory.resolve()

        # Check if the resolved path is within the allowed directory
        if not str(resolved_path).startswith(str(allowed_dir)):
            raise PathTraversalError(
                f"Path traversal detected: {file_path} is outside allowed directory {allowed_directory}"
            )

        return resolved_path

    except (OSError, RuntimeError) as e:
        raise PathTraversalError(f"Invalid path: {file_path}") from e


def validate_file_size(size: int, max_size: int) -> int:
    """
    Validate that file size is within allowed limit

    Args:
        size: File size in bytes
        max_size: Maximum allowed size in bytes

    Returns:
        The validated file size

    Raises:
        FileSizeLimitError: If file size exceeds limit
    """
    if size > max_size:
        raise FileSizeLimitError(
            f"File size {size} bytes exceeds maximum allowed size {max_size} bytes "
            f"({max_size / (1024*1024):.1f} MB)"
        )

    return size


def validate_mime_type(mime_type: str, allowed_types: list[str]) -> str:
    """
    Validate that MIME type is in the allowed list

    Args:
        mime_type: MIME type to validate
        allowed_types: List of allowed MIME types

    Returns:
        The validated MIME type

    Raises:
        InvalidMimeTypeError: If MIME type is not allowed
    """
    if mime_type not in allowed_types:
        raise InvalidMimeTypeError(
            f"Invalid MIME type: {mime_type}. Allowed types: {', '.join(allowed_types)}"
        )

    return mime_type
