"""
Batch exporter for libsafe metadata and files
Implements incremental CSV writing for crash recovery and memory efficiency
"""

import csv
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, Dict, Any

from tqdm import tqdm

from ..config import Config
from ..validators import (
    validate_date,
    validate_handle,
    sanitize_filename,
    validate_safe_path,
)
from ..database import DatabaseConnection
from ..dspace import DSpaceClient
from ..dspace.exceptions import DSpaceAPIError

logger = logging.getLogger(__name__)


class BatchExporter:
    """
    Exports metadata and PDF files from DSpace repository to libsafe directory
    with incremental CSV writing for crash recovery
    """

    # Metadata fields to export
    WORK_FIELDS = {
        'Type': 'dc.type',
        'Title': 'dc.title',
        'Author': 'dc.contributor.author',
        'DOI': 'dc.identifier.doi',
        'Publication Date': 'dc.date.issued',
        'Repository Record Created': 'dc.date.accessioned',
    }

    CSV_FIELDNAMES = ['Handle', 'File'] + list(WORK_FIELDS.keys())

    def __init__(
        self,
        db: DatabaseConnection,
        dspace_client: DSpaceClient,
        export_dir: Path = None,
    ):
        """
        Initialize batch exporter

        Args:
            db: Database connection
            dspace_client: DSpace API client
            export_dir: Export directory path (defaults to config)
        """
        self.db = db
        self.dspace = dspace_client
        self.export_dir = export_dir or Config.LIBSAFE_EXPORT_DIRECTORY

        # Statistics
        self.stats = {
            'total': 0,
            'success': 0,
            'skipped': 0,
            'errors': 0,
        }

        # Timing
        self.start_time = None

    def _get_existing_handles_from_csv(self, csv_path: Path) -> Set[str]:
        """
        Read existing CSV and extract already-processed handle suffixes

        Args:
            csv_path: Path to CSV file

        Returns:
            Set of handle suffixes already in CSV
        """
        existing = set()

        if csv_path.exists():
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Extract handle suffix from full handle URL
                        handle_url = row.get('Handle', '')
                        if '/' in handle_url:
                            handle_suffix = handle_url.split('/')[-1]
                            existing.add(handle_suffix)

                logger.info(f"Found {len(existing)} existing records in CSV")
            except Exception as e:
                logger.warning(f"Could not read existing CSV: {e}")

        return existing

    def _get_existing_files(self) -> Set[str]:
        """
        Get set of existing PDF files in export directory

        Returns:
            Set of handle suffixes for existing files
        """
        existing_suffixes = set()

        try:
            for file_path in self.export_dir.iterdir():
                if file_path.is_file() and file_path.suffix == '.pdf':
                    # Extract handle suffix from filename (remove .pdf)
                    handle_suffix = file_path.stem
                    existing_suffixes.add(handle_suffix)

            logger.info(f"Found {len(existing_suffixes)} existing PDF files")
        except Exception as e:
            logger.warning(f"Could not scan export directory: {e}")

        return existing_suffixes

    def _get_metadata_for_handle(self, handle: str) -> Dict[str, str]:
        """
        Get metadata values for a handle

        Args:
            handle: DSpace handle

        Returns:
            Dictionary of metadata field values
        """
        metadata = {
            'Handle': f'http://hdl.handle.net/{handle}',
            'File': '',
        }

        for label, field in self.WORK_FIELDS.items():
            values = self.db.get_metadata_values(handle, field)

            # Join multiple values with semicolon
            combined = '; '.join(values)

            # Clean up whitespace
            combined = re.sub(r'\s+', ' ', combined).strip()

            # For Type field, take only the first value if multiple
            if label == 'Type' and '; ' in combined:
                combined = combined.split('; ')[0]

            metadata[label] = combined

        return metadata

    def _download_file(
        self,
        uuid: str,
        file_path: Path,
    ) -> bool:
        """
        Download a file from DSpace

        Args:
            uuid: Bitstream UUID
            file_path: Destination file path

        Returns:
            True if download successful
        """
        try:
            logger.debug(f"Downloading bitstream {uuid}")

            response = self.dspace.get_bitstream_content(uuid)

            if response['status'] == 'success':
                # Validate file size
                content = response['body']
                if len(content) > Config.MAX_FILE_SIZE:
                    logger.warning(f"File exceeds size limit: {len(content)} bytes")
                    return False

                # Write file atomically using temporary file
                temp_path = file_path.with_suffix('.tmp')
                temp_path.write_bytes(content)

                # Move to final location
                temp_path.rename(file_path)

                logger.info(f"Downloaded file: {file_path.name}")
                return True

        except DSpaceAPIError as e:
            logger.error(f"DSpace API error for {uuid}: {e}")
        except Exception as e:
            logger.error(f"Error downloading {uuid}: {e}")

        return False

    def export_batch(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 0,
    ) -> Dict[str, Any]:
        """
        Export metadata and files in batches with incremental CSV writing

        Args:
            start_date: Optional start date filter in YYYY-MM-DD format (inclusive)
            end_date: Optional end date filter in YYYY-MM-DD format (inclusive)
            limit: Maximum number of files to download (0 = unlimited)

        Returns:
            Dictionary with export statistics
        """
        self.start_time = time.time()

        # Validate dates if provided
        if start_date:
            start_date = validate_date(start_date)
        if end_date:
            end_date = validate_date(end_date)

        # Log date filter
        if start_date and end_date:
            logger.info(f"Filtering records added between {start_date} and {end_date}")
        elif start_date:
            logger.info(f"Filtering records added on or after {start_date}")
        elif end_date:
            logger.info(f"Filtering records added on or before {end_date}")

        # Get today's date for embargo check
        today = datetime.now().strftime('%Y-%m-%d')

        # CSV file path
        csv_path = self.export_dir / 'metadata.csv'

        # Get existing records to avoid re-processing
        existing_in_csv = self._get_existing_handles_from_csv(csv_path)
        existing_files = self._get_existing_files()

        # Track downloaded files for limit
        downloaded_count = 0

        # Get handles to export
        logger.info("Fetching handles from database...")
        all_handles = self.db.get_handles_for_export(start_date, end_date)
        logger.info(f"Found {len(all_handles)} total handles")
        if limit > 0:
            logger.info(f"Download limit: {limit} files")

        # Filter out embargoed handles
        embargoed = self.db.get_embargoed_handles(today)
        handles = [h for h in all_handles if h not in embargoed]
        logger.info(f"Unembargoed handles: {len(handles)}")

        # Open CSV file for incremental writing
        csv_mode = 'a' if csv_path.exists() else 'w'
        csv_file = open(csv_path, csv_mode, newline='', encoding='utf-8')
        writer = csv.DictWriter(csv_file, fieldnames=self.CSV_FIELDNAMES)

        # Write header only for new files
        if csv_mode == 'w':
            writer.writeheader()
            csv_file.flush()

        try:
            # Process each handle with progress bar
            for handle in tqdm(handles, desc="Exporting", unit="record"):
                # Check if limit reached
                if limit > 0 and downloaded_count >= limit:
                    logger.info(f"Download limit of {limit} files reached. Stopping export.")
                    break

                self.stats['total'] += 1

                # Validate handle
                try:
                    validate_handle(handle)
                except Exception as e:
                    logger.warning(f"Invalid handle {handle}: {e}")
                    self.stats['errors'] += 1
                    continue

                # Extract handle suffix
                handle_suffix = handle.split('/')[1]

                # Skip if already in CSV
                if handle_suffix in existing_in_csv:
                    logger.debug(f"Skipping {handle} (already in CSV)")
                    self.stats['skipped'] += 1
                    continue

                # Get metadata
                metadata = self._get_metadata_for_handle(handle)

                # Sanitize filename
                filename = sanitize_filename(f"{handle_suffix}.pdf")
                metadata['File'] = filename

                file_path = self.export_dir / filename

                # Validate file path is safe
                try:
                    validate_safe_path(file_path, self.export_dir)
                except Exception as e:
                    logger.error(f"Path validation failed for {filename}: {e}")
                    self.stats['errors'] += 1
                    continue

                # Check if file already exists
                if handle_suffix in existing_files:
                    # File exists, just add to CSV
                    writer.writerow(metadata)
                    csv_file.flush()
                    logger.info(f"Added existing file to CSV: {handle}")
                    self.stats['success'] += 1
                    downloaded_count += 1
                    continue

                # Download file
                uuids = self.db.get_bitstream_uuids(handle)

                if not uuids:
                    logger.warning(f"No PDF bitstreams found for {handle}")
                    self.stats['errors'] += 1
                    continue

                # Try to download the first PDF
                for uuid in uuids:
                    logger.info(f"Processing {handle} - UUID: {uuid}")

                    if self._download_file(uuid, file_path):
                        # SUCCESS: Write to CSV immediately after successful download
                        writer.writerow(metadata)
                        csv_file.flush()  # Force write to disk

                        self.stats['success'] += 1
                        downloaded_count += 1
                        logger.info(f"✓ Added {handle} to CSV")

                        # Only download the first successful file
                        break
                else:
                    # No files were successfully downloaded
                    logger.warning(f"Failed to download any files for {handle}")
                    self.stats['errors'] += 1

        finally:
            csv_file.close()
            logger.info("CSV file closed")

        # Calculate elapsed time
        elapsed = time.time() - self.start_time

        # Prepare summary
        summary = {
            'total_handles': len(handles),
            'processed': self.stats['total'],
            'successful': self.stats['success'],
            'skipped': self.stats['skipped'],
            'errors': self.stats['errors'],
            'elapsed_seconds': elapsed,
            'csv_path': str(csv_path),
            'limit': limit,
            'limit_reached': limit > 0 and downloaded_count >= limit,
        }

        logger.info(f"Export complete: {summary}")

        return summary
