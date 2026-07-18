FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# OCRmyPDF requires Tesseract/Ghostscript and related PDF/image utilities.
# libzbar0: runtime library for pyzbar (QR decoding).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ghostscript \
        jbig2 \
        tesseract-ocr \
        qpdf \
        pngquant \
        unpaper \
        libzbar0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app \
    && chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
