# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**libsafe Export** is a secure Python implementation of the PHP `exportMetadataAndPublicFilesInBatches` script. It exports metadata and PDF files from the KAUST DSpace repository to a local directory for the libsafe project.

### Key Features
- **Security-first design**: Prevents SQL injection, URL injection, and path traversal attacks
- **Incremental CSV writing**: Each record written immediately after download (crash-recoverable)
- **Resume capability**: Automatically skips already-processed records
- **Memory efficient**: Streams data instead of loading everything into memory
- **Proper error handling**: Retry logic with exponential backoff

### Origin
Migrated from PHP (`updates/exportMetadataAndPublicFilesInBatches.php` and `functions/shared/dspace/dspaceGetBitstreamsContent.php` in the IRTSv2 repository) to Python with major security improvements.

## Commands

This is a Python project using `uv` for dependency management:

### Run Export
```bash
# Basic export (all unembargoed records)
uv run export_libsafe.py

# Export records added after specific date
uv run export_libsafe.py --from-date 2024-01-01

# Verbose logging
uv run export_libsafe.py --verbose

# Alternative: use shell script
./run_export.sh --verbose
```

### Install Dependencies
```bash
# Using uv (recommended)
uv sync

# Using pip
pip install -r requirements.txt
```

### Monitor Progress
```bash
# Watch CSV file grow
tail -f /data/exports/libsafe/metadata.csv

# Monitor logs
tail -f export_libsafe.log

# Count exported records
wc -l /data/exports/libsafe/metadata.csv
```

## Architecture

### Entry Point
- **`export_libsafe.py`** - Main script with CLI argument parsing and logging setup

### Core Modules

1. **`irts_export/config.py`**
   - Loads configuration from `.env` file using `python-dotenv`
   - Validates required environment variables
   - Provides typed configuration constants

2. **`irts_export/validators.py`**
   - Input validation functions (UUIDs, dates, handles, paths)
   - Custom exception classes for validation errors
   - Prevents injection attacks

3. **`irts_export/dspace/`**
   - **`client.py`** - DSpace REST API client with authentication
   - **`exceptions.py`** - DSpace-specific exceptions
   - Handles public and authenticated file downloads
   - Automatic retry with exponential backoff

4. **`irts_export/database/`**
   - **`connection.py`** - Secure database connection with parameterized queries
   - All queries use `%s` placeholders (SQL injection safe)
   - Context manager support for proper resource cleanup

5. **`irts_export/export/`**
   - **`batch_exporter.py`** - Main export logic
   - Implements incremental CSV writing
   - Progress tracking with tqdm
   - Atomic file operations

### Configuration

Configuration is managed through environment variables (`.env` file):

```bash
# Database
MYSQL_SERVER_IP=localhost
MYSQL_PORT=3336
MYSQL_USER=irts
MYSQL_PASSWORD=<password>
IRTS_DATABASE=prod_irts

# DSpace Repository
REPOSITORY_USER=repository@kaust.edu.sa
REPOSITORY_PASSWORD=<password>
REPOSITORY_API_URL=https://repository.kaust.edu.sa/server/api/

# Export
LIBSAFE_EXPORT_DIRECTORY=/data/exports/libsafe/

# Community Handles
KAUST_RESEARCH_HANDLE=10754/324602
KAUST_ETD_HANDLE=10754/124545
```

### Output

**Directory**: `/data/exports/libsafe/`

**Files**:
- `metadata.csv` - CSV file with metadata (Handle, File, Type, Title, Author, DOI, etc.)
- `*.pdf` - PDF files named by handle suffix (e.g., `123456.pdf` for handle `10754/123456`)

**Log**: `export_libsafe.log` (in project directory)

## Security Features

### Implemented Protections

1. **SQL Injection Prevention**
   - All queries use parameterized statements with `%s` placeholders
   - Example: `cursor.execute(query, (handle, field))`
   - Literal `%` in LIKE patterns doubled: `'%%.pdf'`

2. **URL Injection Prevention**
   - UUID validation before use in API calls
   - URL encoding with `urllib.parse.quote()`
   - Example: `validate_uuid(bitstream_uuid)` before API request

3. **Path Traversal Prevention**
   - Filename sanitization: `re.sub(r'[^a-zA-Z0-9._-]', '', filename)`
   - Path validation: ensures resolved path is within allowed directory
   - Example: `validate_safe_path(file_path, export_dir)`

4. **Input Validation**
   - UUIDs: Validated with `uuid.UUID()` constructor
   - Dates: Strict format checking with `datetime.strptime()`
   - Handles: Regex pattern validation `^\d+/\d+$`

5. **Credential Management**
   - All secrets in `.env` file (gitignored)
   - No hardcoded credentials in code
   - Environment variable validation on startup

### Comparison with PHP Version

| Feature | PHP Version | Python Version |
|---------|-------------|----------------|
| SQL queries | String concatenation ❌ | Parameterized ✅ |
| API URLs | Direct concatenation ❌ | Validated & encoded ✅ |
| File paths | No validation ❌ | Sanitized & validated ✅ |
| Credentials | Hardcoded ❌ | .env file ✅ |
| CSV writing | All at end ❌ | Incremental ✅ |
| Resume | Not supported ❌ | Automatic ✅ |

## Data Flow

1. **Query Database** (parameterized queries)
   - Get handles for export (filtered by type, community, date)
   - Filter out embargoed records
   - Get existing records from CSV (for resume)

2. **For Each Handle**
   - Retrieve metadata from database
   - Get bitstream UUIDs for PDF files
   - Download PDF from DSpace API (try unauthenticated first)
   - Write file atomically (temp file → rename)
   - **Immediately** write metadata row to CSV
   - Flush CSV to disk

3. **Error Handling**
   - Network errors: Retry with exponential backoff (3 attempts)
   - Authentication errors: Try unauthenticated, then authenticate
   - File errors: Log and skip, continue with next record
   - Validation errors: Log and skip

## Development Notes

### Type Hints
- Comprehensive type annotations throughout
- PyMySQL type stubs have limitations (some `# type: ignore` comments added)
- Pylance validation enabled

### Testing
- Manual testing against production repository
- Can be tested against DSpace test instance by changing `IRTS_TEST=True`
- Resume capability tested by interrupting and restarting

### Dependencies
- **requests**: HTTP client with session management
- **PyMySQL**: MySQL database connector
- **tenacity**: Retry logic with exponential backoff
- **python-dotenv**: Environment variable management
- **tqdm**: Progress bar display

### File Naming Conventions
- Module files: lowercase with underscores (`batch_exporter.py`)
- Class names: PascalCase (`BatchExporter`, `DSpaceClient`)
- Constants: UPPER_CASE (`LIBSAFE_EXPORT_DIRECTORY`)
- Functions: lowercase with underscores (`get_bitstream_content`)

### Important Implementation Details

1. **Incremental CSV Writing**
   - CSV file opened at start (append mode if exists)
   - Each record written immediately after successful file download
   - `csv_file.flush()` called after each write
   - Enables crash recovery and real-time monitoring

2. **DSpace Authentication**
   - Tries unauthenticated request first (for public files)
   - Only authenticates if 401/403 received
   - Bearer token cached in session for subsequent requests

3. **Database Connection**
   - Connection pool managed via context manager
   - Auto-commit after successful queries
   - Auto-rollback on errors
   - Charset set to `utf8mb4`

4. **PDF Selection**
   - Only downloads PDFs from "ORIGINAL" bundle
   - Takes first successful PDF if multiple exist
   - Validates file size (max 100MB)

## Related Projects

- **IRTSv2** (`/home/garcm0b/Work/IRTSv2/`) - Parent PHP project
- **Original PHP scripts**:
  - `updates/exportMetadataAndPublicFilesInBatches.php`
  - `functions/shared/dspace/dspaceGetBitstreamsContent.php`

## Troubleshooting

### Common Issues

1. **Authentication 403 errors**
   - Public files should work without authentication
   - Check `REPOSITORY_USER` and `REPOSITORY_PASSWORD` in `.env`

2. **SQL errors with % in LIKE**
   - Literal `%` must be doubled: `'%%.pdf'` not `'%.pdf'`

3. **Path does not exist**
   - Ensure `/data/exports/libsafe/` exists and is writable
   - `mkdir -p /data/exports/libsafe/`

4. **Pylance type errors**
   - Some PyMySQL type stubs are incomplete
   - `# type: ignore` comments are intentional and safe

## Performance

- **Typical throughput**: ~50-100 records/minute (depends on file sizes)
- **Memory usage**: Low (~50MB) due to streaming
- **Network**: Concurrent downloads not implemented (sequential for stability)
- **Database**: Connection reused across all queries

## Future Improvements

Potential enhancements (not currently implemented):
- Concurrent file downloads with asyncio
- Checksums for file integrity verification
- Email notifications on completion/errors
- Metrics/statistics export
- Unit test suite
- Docker containerization
