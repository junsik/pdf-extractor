# pdf-extractor

PDF extraction/parsing service intended to be used as a reusable ELT component in a data stack.

## What is included

- `web`: Next.js (standalone build)
- `api`: FastAPI (Uvicorn)
- Reverse proxy: Caddy (single entrypoint)

## Run (multi-container, compose)

```bash
docker compose up -d --build
```

Open:
- http://localhost:8090

## Run (single-container, all-in-one)

Build:

```bash
docker build -f Dockerfile.allinone -t pdf-extractor-aio .
```

Run:

```bash
docker run --rm -p 8090:8080 pdf-extractor-aio
```

Open:
- http://localhost:8090

