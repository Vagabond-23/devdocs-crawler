# DevDocs Distributed Web Crawler & Search Engine

A production-style distributed web crawler and search engine for documentation websites. Built with clean architecture, distributed systems patterns, and real engineering practices.

## Architecture

```
Seed URLs → URL Normalizer → Global Frontier (Redis)
                                    ↓
                          Host-Aware Scheduler
                         (Round-Robin + Rate Limiting)
                                    ↓
                          Async Crawl Workers (×8)
                            ↓              ↓
                      HTML Parser     Conditional Fetch
                     (selectolax)    (ETag/Last-Modified)
                            ↓
                    Content Deduplicator
                    (SHA-256 + SimHash)
                         ↓           ↓
                   PostgreSQL    Meilisearch
                         ↓
                    FastAPI Search API
                         ↓
                  Next.js Search UI
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend / API | Python 3.12, FastAPI |
| Crawler | asyncio, httpx, selectolax |
| Queue / Scheduling | Redis |
| Database | PostgreSQL |
| Search | Meilisearch |
| Frontend | Next.js (TypeScript) |
| Infrastructure | Docker, docker-compose |

## Key Features

- **Host-aware scheduling**: Fair round-robin across domains with per-host rate limiting
- **Politeness**: robots.txt support with caching and Crawl-delay
- **URL canonicalization**: Normalize trailing slashes, fragments, case, query params
- **Multi-level deduplication**: SHA-256 exact + SimHash near-duplicate detection
- **Incremental crawling**: ETag/Last-Modified conditional fetch with 304 support
- **Crawl state machine**: DISCOVERED → FETCHING → FETCHED → PARSED → INDEXED → COMPLETED
- **Retry with backoff**: Exponential backoff (5^n seconds) with max 3 retries
- **Observability**: Real-time metrics via `/stats` and Prometheus-format `/metrics`

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env

# 2. Start all services
docker compose up --build

# 3. Open the search UI
open http://localhost:3000

# 4. Start a crawl via API
curl -X POST http://localhost:8000/api/v1/crawl/start \
  -H "Content-Type: application/json" \
  -d '{"seed_urls": ["https://docs.python.org/3/", "https://fastapi.tiangolo.com/"]}'

# 5. Monitor progress
curl http://localhost:8000/api/v1/stats
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/search?q=...` | Full-text search |
| POST | `/api/v1/crawl/start` | Start crawl job |
| GET | `/api/v1/crawl/jobs` | List crawl jobs |
| GET | `/api/v1/crawl/jobs/{id}` | Get job status |
| GET | `/api/v1/stats` | System stats (JSON) |
| GET | `/api/v1/metrics` | Prometheus metrics |

## Project Structure

```
devdocs-crawler/
├── backend/
│   └── src/
│       ├── main.py              # FastAPI entry point
│       ├── config.py            # Pydantic settings
│       ├── models/              # SQLAlchemy ORM models
│       ├── schemas/             # Pydantic request/response
│       ├── api/                 # FastAPI routers
│       ├── crawler/             # Crawler engine
│       │   ├── engine.py        # Orchestrator
│       │   ├── worker.py        # Async fetch worker
│       │   ├── frontier.py      # Redis-backed URL queue
│       │   ├── scheduler.py     # Host-aware scheduler
│       │   ├── robots.py        # robots.txt manager
│       │   ├── rate_limiter.py  # Token bucket
│       │   ├── parser.py        # HTML parsing
│       │   ├── deduplicator.py  # SHA-256 + SimHash
│       │   └── indexer.py       # Meilisearch indexing
│       ├── db/                  # Database setup
│       └── metrics/             # Observability
├── frontend/                    # Next.js search UI
├── docker-compose.yml
└── .env.example
```

## Allowed Hosts

This crawler ONLY crawls allowlisted documentation sites:
- `docs.python.org`
- `developer.mozilla.org`
- `fastapi.tiangolo.com`
- `kubernetes.io`

## License

MIT
