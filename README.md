# async-pdf-ocr

Async PDF toolkit API built with FastAPI: OCR, QR extraction, split, merge, and
native text extraction. Designed for Docker/Kubernetes and offline-capable
deployments (automation tools such as Apache NiFi and n8n).

Temporary files are deleted after each response; uploads are not retained.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## Quickstart

1. Install dependencies (uv creates `.venv` automatically):

   ```bash
   uv sync --group dev
   ```

2. Configure environment:

   ```bash
   cp .env.example .env
   ```

3. Run the API:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

4. Open the demo UI, docs, or health check:

   - UI: http://127.0.0.1:8000/
   - OpenAPI (offline Swagger): http://127.0.0.1:8000/docs
   - Health: `curl http://127.0.0.1:8000/health`

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_NAME` | `Async PDF Toolkit API` | OpenAPI title |
| `APP_ENV` | `development` | Environment label |
| `APP_DEBUG` | `false` | FastAPI debug |
| `API_KEY` | _(unset)_ | When set, job endpoints require `X-API-Key`; leave unset for local/open demos |
| `MAX_UPLOAD_BYTES` | `20000000` | Max size per uploaded file |
| `MAX_PDF_PAGES` | `100` | Max pages per job (merged total for `/merge`) |
| `MAX_CONCURRENT_JOBS` | `2` | Global in-process job concurrency |
| `RATE_LIMIT_PER_MINUTE` | `30` | Per-IP request limit (in-memory; single replica) |
| `JOB_TIMEOUT_SECONDS` | `300` | Max seconds per processing job |

## Demo UI

The same-origin demo at `/` covers OCR, QR, Split, Merge, and Extract text:
upload → progress → download (PDF/ZIP) or JSON result.

If the server has `API_KEY` set, expand **API key (optional)** in the UI and
paste the key (stored in `sessionStorage` for that tab only). Public demos
should leave `API_KEY` unset and rely on tight limits instead.

## Docker (Local)

The container image includes OCRmyPDF's runtime tools, including optional
optimizers (`jbig2`, `pngquant`) to avoid degraded compression warnings.

Build the image:

```bash
docker build -t async-pdf-ocr:local .
```

Run the container:

```bash
docker run --rm -p 8000:8000 --name async-pdf-ocr async-pdf-ocr:local
```

Published images (on `main` / version tags) are also available from GitHub
Container Registry as `ghcr.io/<owner>/<repo>` for your fork or upstream.

Verify:

```bash
curl http://127.0.0.1:8000/health
# open http://127.0.0.1:8000/ in a browser
```

## Public demo / self-host tips

This project is meant to stay usable offline and self-hosted without accounts.
A public “try it” instance should stay **open** (`API_KEY` unset) and rely on
limits plus a reverse proxy—not billing or ads.

Recommended tighter limits for a free-tier / portfolio demo:

```bash
docker run --rm -p 8000:8000 \
  -e MAX_UPLOAD_BYTES=5000000 \
  -e MAX_PDF_PAGES=25 \
  -e MAX_CONCURRENT_JOBS=1 \
  -e RATE_LIMIT_PER_MINUTE=10 \
  -e JOB_TIMEOUT_SECONDS=120 \
  --name async-pdf-ocr \
  async-pdf-ocr:local
```

**Privacy:** uploads are written to temporary files, processed, returned, and
deleted. Nothing is retained for later download.

**Edge protection:** put Cloudflare (or any reverse proxy) in front for TLS,
bot mitigation, and edge rate limits. In-app rate limiting is in-memory and
single-replica only—do not rely on it alone across many pods.

For a semi-private share, set `API_KEY` and send `X-API-Key` (UI field or curl
`-H`). Self-host and local/dev can leave it unset.

## OCR Endpoint

Process a PDF with OCRmyPDF:

```bash
curl -X POST "http://127.0.0.1:8000/ocr?language=eng&deskew=true&force_ocr=false&optimize=1" \
  -F "file=@/path/to/input.pdf" \
  --output ocr-output.pdf
```

When `API_KEY` is set, add `-H "X-API-Key: your-key"`.

### Supported query params

- `language` (optional string): OCR language code, e.g. `eng`
- `deskew` (optional bool, default `false`)
- `force_ocr` (optional bool, default `false`)
- `optimize` (optional int `0-3`)

For non-Docker installs, make sure OCRmyPDF's system dependencies are available
on `PATH`, including optional optimizers such as `jbig2` and `pngquant`.

## QR Code Endpoint

Scan a PDF for QR codes and return the decoded text for each (JSON). If none are
found or scanning cannot run, the response is an empty list (HTTP 200). The
container image includes `libzbar0` for QR decoding; on bare-metal installs,
install your platform’s `zbar` library if `pyzbar` cannot load it.

```bash
curl -X POST "http://127.0.0.1:8000/qr" -F "file=@/path/to/input.pdf"
```

## Split Endpoint

Split a PDF into one file per page and return a ZIP archive:

```bash
curl -X POST "http://127.0.0.1:8000/split" \
  -F "file=@/path/to/input.pdf" \
  --output split-pages.zip
```

## Merge Endpoint

Merge two or more PDFs (order = upload order) into a single PDF:

```bash
curl -X POST "http://127.0.0.1:8000/merge" \
  -F "files=@/path/to/a.pdf" \
  -F "files=@/path/to/b.pdf" \
  --output merged.pdf
```

## Extract Text Endpoint

Extract native PDF text (not OCR). Use `/ocr` first for scanned documents.

```bash
# Joined text (default)
curl -X POST "http://127.0.0.1:8000/extract-text" \
  -F "file=@/path/to/input.pdf"

# Per-page JSON
curl -X POST "http://127.0.0.1:8000/extract-text?join_pages=false" \
  -F "file=@/path/to/input.pdf"
```

### Supported query params

- `join_pages` (optional bool, default `true`): when `true`, response is
  `{"text": "..."}`; when `false`, `{"pages": ["...", ...]}`

## Tests

Run tests with:

```bash
uv run pytest
```

## Project Structure

- `src/app/main.py` - FastAPI app creation, middleware, UI mount, and routers
- `src/app/config.py` - environment-driven settings
- `src/app/middleware/api_key.py` - optional `X-API-Key` gate
- `src/app/middleware/rate_limit.py` - per-IP rate limiting
- `src/app/services/pdf_jobs.py` - shared upload/temp/limit helpers
- `src/app/services/limits.py` - concurrency and rate-limit state
- `src/app/static/ui/` - demo web UI (HTML/CSS/JS)
- `src/app/static/swagger-ui/` - offline OpenAPI assets
- `src/app/api/health.py` - async health endpoint
- `src/app/api/ocr.py` - OCR upload endpoint
- `src/app/api/qr.py` - QR code scan upload endpoint
- `src/app/api/split.py` - PDF split-to-ZIP endpoint
- `src/app/api/merge.py` - PDF merge endpoint
- `src/app/api/extract_text.py` - native text extraction endpoint
- `tests/` - API tests
