#!/usr/bin/env python3
"""
libsafe Metadata and Files Batch Export Script

Secure Python implementation of the PHP exportMetadataAndPublicFilesInBatches script.
Features:
- Incremental CSV writing (write each record immediately after download)
- SQL injection prevention via parameterized queries
- Input validation for all user-provided data
- Crash recovery (resume from existing CSV)
- Proper error handling and logging
"""

import argparse
import logging
import sys
from datetime import datetime

from irts_export.config import Config
from irts_export.database import DatabaseConnection
from irts_export.dspace import DSpaceClient
from irts_export.export import BatchExporter


def setup_logging(verbose: bool = False):
    """Configure logging"""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('export_libsafe.log'),
        ]
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Export libsafe metadata and PDF files from DSpace repository'
    )
    # Date filtering arguments
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        '--from-date',
        type=str,
        dest='start',
        help='Alias for --start (for backward compatibility)',
    )
    date_group.add_argument(
        '-s', '--start',
        type=str,
        help='Only export records added on or after this date (format: YYYY-MM-DD)',
    )
    parser.add_argument(
        '-e', '--end',
        type=str,
        help='Only export records added on or before this date (format: YYYY-MM-DD)',
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        default=0,
        help='Limit the number of files to download (0 = unlimited, default: 0)',
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging',
    )

    args = parser.parse_args()

    # Validate number argument
    if args.number < 0:
        parser.error("--number must be >= 0")

    # Validate date range
    if args.start and args.end:
        # Both provided, ensure start <= end
        if args.start > args.end:
            parser.error("--start date must be before or equal to --end date")

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("libsafe Metadata and Files Export")
    logger.info("=" * 60)

    try:
        # Validate configuration
        Config.validate()
        logger.info(f"Export directory: {Config.LIBSAFE_EXPORT_DIRECTORY}")

        # Log date filter if provided
        if args.start and args.end:
            logger.info(f"Date range filter: {args.start} to {args.end}")
        elif args.start:
            logger.info(f"Date filter: records added on or after {args.start}")
        elif args.end:
            logger.info(f"Date filter: records added on or before {args.end}")

        if args.number > 0:
            logger.info(f"File download limit: {args.number}")

        # Connect to database
        logger.info("Connecting to database...")
        with DatabaseConnection() as db:
            logger.info("Database connection established")

            # Create DSpace client
            logger.info("Initializing DSpace API client...")
            with DSpaceClient() as dspace:
                logger.info("DSpace client initialized")

                # Create exporter
                exporter = BatchExporter(db, dspace)

                # Run export
                logger.info("Starting export...")
                summary = exporter.export_batch(
                    start_date=args.start,
                    end_date=args.end,
                    limit=args.number,
                )

                # Print summary
                logger.info("=" * 60)
                logger.info("EXPORT SUMMARY")
                logger.info("=" * 60)
                logger.info(f"Total handles:       {summary['total_handles']}")
                logger.info(f"Processed:           {summary['processed']}")
                logger.info(f"Successful:          {summary['successful']}")
                logger.info(f"Skipped (existing):  {summary['skipped']}")
                logger.info(f"Errors:              {summary['errors']}")
                if summary['limit'] > 0:
                    logger.info(f"Download limit:      {summary['limit']}")
                    if summary['limit_reached']:
                        logger.info(f"Limit reached:       YES")
                logger.info(f"Elapsed time:        {summary['elapsed_seconds']:.2f} seconds")
                logger.info(f"CSV file:            {summary['csv_path']}")
                logger.info("=" * 60)

                # Exit with appropriate code
                if summary['errors'] > 0:
                    logger.warning("Export completed with errors")
                    sys.exit(1)
                else:
                    logger.info("Export completed successfully")
                    sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\nExport interrupted by user")
        sys.exit(130)

    except Exception as e:
        logger.exception(f"Export failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
