# libsafe Metadata and Files Export

Secure Python implementation of the PHP `exportMetadataAndPublicFilesInBatches` script for exporting DSpace repository metadata and PDF files.

## Features

### Security Improvements ✓

- **SQL Injection Prevention**: All database queries use parameterized statements
- **URL Injection Prevention**: UUIDs and handles are validated before use in API calls
- **Path Traversal Protection**: Filenames are sanitized and paths validated
- **Input Validation**: All user inputs validated with strict type checking
- **Credential Management**: Secrets stored in `.env` file (not in code)

### Reliability Improvements ✓

- **Incremental CSV Writing**: Each record written to CSV immediately after successful download
- **Crash Recovery**: Can resume by reading existing CSV and skipping processed records
- **Atomic File Operations**: Files written to temp location, then moved atomically
- **Retry Logic**: Automatic retry with exponential backoff for transient failures
- **Connection Pooling**: Efficient HTTP session management

### Usability Improvements ✓

- **Progress Tracking**: Real-time progress bar with tqdm
- **Comprehensive Logging**: Detailed logs to both console and file
- **Resume Capability**: Automatically skips already-processed records
- **Memory Efficiency**: Streams data instead of building large arrays in memory

## Project Structure

```
export_libsafe/
├── .env                          # Credentials (DO NOT COMMIT)
├── .env.example                  # Template for credentials
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── export_libsafe.py            # Main entry point script
├── README.md                     # This file
└── irts_export/                  # Main package
    ├── __init__.py
    ├── config.py                 # Configuration from environment
    ├── validators.py             # Input validation functions
    ├── dspace/                   # DSpace API client
    │   ├── __init__.py
    │   ├── client.py             # API client with auth
    │   └── exceptions.py         # Custom exceptions
    ├── database/                 # Database module
    │   ├── __init__.py
    │   └── connection.py         # Parameterized queries
    └── export/                   # Export logic
        ├── __init__.py
        └── batch_exporter.py     # Main export class
```

## Installation

### 1. Install Python Dependencies

```bash
cd /home/garcm0b/Work/export_libsafe
pip install -r requirements.txt
```

Or with virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

The `.env` file has been pre-configured with your credentials. If you need to modify:

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env
```

### 3. Verify Export Directory Exists

```bash
# Make sure this directory exists and is writable
ls -la /data/exports/libsafe/
```

## Usage

### Basic Export (All Unembargoed Records)

```bash
python export_libsafe.py
```

### Export Records Added After Specific Date

```bash
python export_libsafe.py --from-date 2024-01-01
```

### Enable Verbose Logging

```bash
python export_libsafe.py --verbose
```

### Resume After Crash

Simply re-run the same command. The script will:
1. Read existing `metadata.csv`
2. Skip handles already in CSV
3. Continue from where it left off

```bash
uv run export_libsafe.py --verbose
```

## How It Works

### Incremental CSV Writing

Unlike the PHP version which builds an array in memory and writes at the end, this implementation:

1. Opens CSV file at start (append mode if exists)
2. For each handle:
   - Download PDF file
   - **Immediately** write metadata row to CSV after successful download
   - Flush to disk (ensures data is saved)
3. If script crashes, next run skips already-processed records

### Security Features

#### SQL Injection Prevention

```python
# ✓ SECURE: Parameterized query
query = "SELECT * FROM metadata WHERE idInSource = %s AND field = %s"
db.execute_query(query, (handle, field))

# ✗ INSECURE (PHP version): String concatenation
# query = "... WHERE added > '" . $_GET['from'] . "'"
```

#### URL Injection Prevention

```python
# ✓ SECURE: UUID validation + URL encoding
validated_uuid = validate_uuid(bitstream_uuid)
encoded_uuid = quote(validated_uuid, safe='')
url = f'core/bitstreams/{encoded_uuid}/content'

# ✗ INSECURE (PHP version): Direct concatenation
# url = 'core/bitstreams/' . $id . '/content'
```

#### Path Traversal Prevention

```python
# ✓ SECURE: Filename sanitization + path validation
filename = sanitize_filename(f"{handle_suffix}.pdf")
file_path = export_dir / filename
validate_safe_path(file_path, export_dir)

# ✗ INSECURE (PHP version): No validation
# $fileName = $handleSuffix . '.pdf';
```

## Output

### CSV File

Location: `/data/exports/libsafe/metadata.csv`

Columns:
- Handle
- File
- Type
- Title
- Author
- DOI
- Publication Date
- Repository Record Created

### PDF Files

Location: `/data/exports/libsafe/*.pdf`

Naming: `{handle_suffix}.pdf` (e.g., `123456.pdf` for handle `10754/123456`)

### Log File

Location: `export_libsafe.log` (in current directory)

Contains detailed execution log for debugging.

## Error Handling

The script handles various error conditions:

- **Invalid UUID**: Validation error, record skipped
- **Invalid date format**: Script exits with error message
- **Network errors**: Automatic retry (3 attempts with exponential backoff)
- **File too large**: Warning logged, file skipped
- **Database errors**: Logged with full traceback
- **Authentication failures**: Clear error message

## Monitoring Progress

### Real-time Progress

```bash
# Watch CSV file grow
tail -f /data/exports/libsafe/metadata.csv

# Count processed records
wc -l /data/exports/libsafe/metadata.csv
```

### Log Monitoring

```bash
# Follow log file
tail -f export_libsafe.log

# Search for errors
grep ERROR export_libsafe.log
```

## Comparison with PHP Version

| Feature | PHP Version | Python Version |
|---------|-------------|----------------|
| CSV Writing | At end (all in memory) | Incremental (after each download) |
| Resume Capability | ✗ No | ✓ Yes (reads existing CSV) |
| SQL Injection | ✗ Vulnerable | ✓ Protected (parameterized) |
| URL Injection | ✗ Vulnerable | ✓ Protected (validated) |
| Path Traversal | ✗ Vulnerable | ✓ Protected (sanitized) |
| Memory Usage | High (array in memory) | Low (streaming) |
| Credentials | Hardcoded | `.env` file |
| Error Handling | Basic | Comprehensive with retry |
| Logging | Echo statements | Structured logging |
| Progress Tracking | Echo count | Progress bar + logs |

## Troubleshooting

### "Missing required environment variables"

```bash
# Check .env file exists
ls -la .env

# Verify all variables are set
cat .env
```

### "Export directory does not exist"

```bash
# Create directory
sudo mkdir -p /data/exports/libsafe/
sudo chown $USER:$USER /data/exports/libsafe/
```

### "Database connection failed"

```bash
# Test MySQL connectivity
mysql -h 10.127.6.29 -u irts -p prod_irts

# Check .env credentials match
```

### "Authentication failed"

```bash
# Verify DSpace credentials
# Check REPOSITORY_USER and REPOSITORY_PASSWORD in .env
```

## Development

### Running Tests

```python
# TODO: Add unit tests for validators, database queries, etc.
pytest tests/
```

### Code Style

```bash
# Format code
black irts_export/

# Lint code
flake8 irts_export/
```

## Security Notes

⚠️ **IMPORTANT**: Never commit the `.env` file to version control!

The `.gitignore` is configured to exclude `.env`, but double-check:

```bash
git status  # .env should NOT appear here
```

## License

Same as parent IRTS project.

## Support

For issues or questions, contact the KAUST Library development team.
