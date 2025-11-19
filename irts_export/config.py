"""
Configuration management for IRTS SDAIA Export
Loads configuration from environment variables using python-dotenv
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class that loads all settings from environment variables"""

    # Database Configuration
    MYSQL_SERVER_IP = os.getenv('MYSQL_SERVER_IP', '')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
    MYSQL_USER = os.getenv('MYSQL_USER', '')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    IRTS_DATABASE = os.getenv('IRTS_DATABASE', 'prod_irts')

    # DSpace Repository API
    REPOSITORY_USER = os.getenv('REPOSITORY_USER', '')
    REPOSITORY_PASSWORD = os.getenv('REPOSITORY_PASSWORD', '')
    REPOSITORY_BASE_URL = os.getenv('REPOSITORY_BASE_URL', '')
    REPOSITORY_API_URL = os.getenv('REPOSITORY_API_URL', '')

    # Export Configuration
    LIBSAFE_EXPORT_DIRECTORY = Path(os.getenv('LIBSAFE_EXPORT_DIRECTORY', '/tmp/'))

    # Community Handles
    KAUST_RESEARCH_HANDLE = os.getenv('KAUST_RESEARCH_HANDLE', '10754/324602')
    KAUST_ETD_HANDLE = os.getenv('KAUST_ETD_HANDLE', '10754/124545')

    # Environment
    IRTS_TEST = os.getenv('IRTS_TEST', 'False').lower() in ('true', '1', 'yes')

    # HTTP Settings
    REQUEST_TIMEOUT = (5, 30)  # (connect timeout, read timeout) in seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF = 1.0  # seconds

    # File Settings
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    ALLOWED_MIME_TYPE = 'application/pdf'

    @classmethod
    def validate(cls):
        """Validate that all required configuration is present"""
        required_vars = [
            'MYSQL_SERVER_IP',
            'MYSQL_USER',
            'MYSQL_PASSWORD',
            'REPOSITORY_USER',
            'REPOSITORY_PASSWORD',
            'REPOSITORY_API_URL',
        ]

        missing = []
        for var in required_vars:
            if not getattr(cls, var):
                missing.append(var)

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Please check your .env file"
            )

        # Validate export directory exists or can be created
        if not cls.LIBSAFE_EXPORT_DIRECTORY.exists():
            raise ValueError(
                f"Export directory does not exist: {cls.LIBSAFE_EXPORT_DIRECTORY}"
            )

        return True


# Validate configuration on import
Config.validate()
