"""
Secure database connection with parameterized queries
Prevents SQL injection by using prepared statements
"""

import logging
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from ..config import Config

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database errors"""
    pass


class DatabaseConnection:
    """
    Secure database connection manager with parameterized queries
    """

    def __init__(
        self,
        host: str = "",
        user: str = "",
        port: int = 3306,
        password: str = "",
        database: str = "",
    ):
        """
        Initialize database connection

        Args:
            host: MySQL server hostname
            user: MySQL username
            port: MySQL port
            password: MySQL password
            database: Database name
        """
        self.host = host or Config.MYSQL_SERVER_IP
        self.user = user or Config.MYSQL_USER
        self.port = port or Config.MYSQL_PORT
        self.password = password or Config.MYSQL_PASSWORD
        self.database = database or Config.IRTS_DATABASE

        self.connection: Optional[Connection] = None

    def connect(self):
        """Establish database connection"""
        try:
            self.connection = pymysql.connect(  # type: ignore[call-overload]
                host=self.host,
                user=self.user,
                port=self.port,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                cursorclass=DictCursor,
            )
            logger.info(f"Connected to database: {self.database}")
        except pymysql.Error as e:
            raise DatabaseError(f"Failed to connect to database: {e}") from e

    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    @contextmanager
    def get_cursor(self):
        """
        Context manager for database cursor

        Yields:
            Database cursor
        """
        if not self.connection:
            self.connect()

        assert self.connection is not None, "Connection should be established"

        cursor = self.connection.cursor()
        try:
            yield cursor
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query with parameterized values (SQL injection safe)

        Args:
            query: SQL query with %s placeholders
            params: Tuple of parameters to bind to query

        Returns:
            List of result rows as dictionaries

        Example:
            results = db.execute_query(
                "SELECT * FROM metadata WHERE idInSource = %s AND field = %s",
                (handle, 'dc.title')
            )
        """
        with self.get_cursor() as cursor:
            logger.debug(f"Executing query: {query[:100]}...")
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            logger.debug(f"Query returned {len(results)} rows")
            return results  # type: ignore[return-value]

    def get_handles_for_export(
        self,
        from_date: Optional[str] = None,
    ) -> List[str]:
        """
        Get list of handles eligible for SDAIA export

        Args:
            from_date: Optional date filter (YYYY-MM-DD format)

        Returns:
            List of handle strings

        Note: Uses parameterized queries to prevent SQL injection
        """
        # Base query with parameterized community handles
        query = """
            SELECT DISTINCT(`idInSource`) FROM `metadata`
            WHERE `source` = 'repository'
            AND `field` = 'dc.type'
            AND `value` IN ('Article','Book','Book Chapter','Conference Paper','Dissertation','Patent','Preprint','Protocol','Report','Technical Report', 'Thesis')
            AND `idInSource` IN (
                SELECT `idInSource` FROM `metadata`
                WHERE `source` = 'repository'
                AND `field` = 'dspace.community.handle'
                AND `value` IN (%s, %s)
                AND `deleted` IS NULL
            )
            AND `deleted` IS NULL
        """

        params = [Config.KAUST_RESEARCH_HANDLE, Config.KAUST_ETD_HANDLE]

        # Add date filter if provided (using parameterized query)
        if from_date:
            query += """
                AND `idInSource` IN (
                    SELECT `idInSource` FROM `metadata`
                    WHERE `source` = 'repository'
                    AND `field` = 'dspace.bitstream.uuid'
                    AND value NOT IN (
                        SELECT `value` FROM `metadata`
                        WHERE `source` = 'repository'
                        AND `field` = 'dspace.bitstream.uuid'
                        AND `added` < %s
                    )
                    AND `added` > %s
                    AND `deleted` IS NULL
                )
            """
            params.extend([from_date, from_date])

        results = self.execute_query(query, tuple(params))
        return [row['idInSource'] for row in results]

    def get_embargoed_handles(self, today: str) -> List[str]:
        """
        Get list of handles with active embargoes

        Args:
            today: Current date in YYYY-MM-DD format

        Returns:
            List of embargoed handle strings
        """
        query = """
            SELECT idInSource FROM metadata
            WHERE `source` = 'repository'
            AND `field` = 'dc.rights.embargodate'
            AND `value` >= %s
            AND `deleted` IS NULL
        """

        results = self.execute_query(query, (today,))
        return [row['idInSource'] for row in results]

    def get_metadata_values(
        self,
        handle: str,
        field: str,
    ) -> List[str]:
        """
        Get metadata values for a specific handle and field

        Args:
            handle: DSpace handle
            field: Metadata field name

        Returns:
            List of metadata values
        """
        query = """
            SELECT `value` FROM `metadata`
            WHERE `source` = 'repository'
            AND `idInSource` = %s
            AND `field` = %s
            AND `deleted` IS NULL
            ORDER BY `rowID`
        """

        results = self.execute_query(query, (handle, field))
        return [row['value'] for row in results]

    def get_bitstream_uuids(self, handle: str) -> List[str]:
        """
        Get PDF bitstream UUIDs for a handle

        Args:
            handle: DSpace handle

        Returns:
            List of bitstream UUID strings
        """
        query = """
            SELECT value FROM `metadata`
            WHERE `source` = 'repository'
            AND `idInSource` = %s
            AND `field` = 'dspace.bitstream.uuid'
            AND deleted IS NULL
            AND parentRowID IN (
                SELECT rowID FROM metadata
                WHERE `source` = 'repository'
                AND `field` = 'dspace.bundle.name'
                AND value = 'ORIGINAL'
                AND `deleted` IS NULL
            )
            AND rowID IN (
                SELECT parentRowID FROM metadata
                WHERE `source` = 'repository'
                AND `field` = 'dspace.bitstream.name'
                AND value LIKE '%%.pdf'
                AND `deleted` IS NULL
            )
        """

        results = self.execute_query(query, (handle,))
        return [row['value'] for row in results]

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
