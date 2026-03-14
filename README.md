# Dark Web Scraper

A professional dark web scraping platform built with modern Python stack, following microservices architecture and DevOps best practices.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│   FastAPI   │   Celery    │  Selenium   │  Tor Proxy  │  Redis  │
│    API      │   Worker    │    Grid     │  (Privoxy)  │         │
│  :8000      │             │   :4444     │   :8118     │  :6379  │
├─────────────┴─────────────┴──────┬──────┴─────────────┴─────────┤
│                                  │                               │
│              PostgreSQL Database (:5432)                        │
└──────────────────────────────────────────────────────────────────┘
```

## Tech Stack

- **API**: FastAPI with async support
- **Task Queue**: Celery with Redis broker
- **Database**: PostgreSQL with SQLAlchemy 2.0 (async)
- **Scraping**: Selenium Grid (Standalone Chrome)
- **Anonymity**: Tor Proxy via Privoxy
- **Monitoring**: Flower (Celery monitoring)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd dark-web-scraper
   ```

2. Copy environment variables:
   ```bash
   cp .env.example .env
   ```

3. Start all services:
   ```bash
   docker-compose up -d
   ```

4. Access the services:
   - **Dashboard UI**: http://localhost:8501 ← *Start here!*
   - **API**: http://localhost:8000
   - **API Docs**: http://localhost:8000/docs
   - **Flower (Celery Monitor)**: http://localhost:5555
   - **Selenium Grid**: http://localhost:4444
   - **Selenium VNC**: http://localhost:7900

## API Endpoints

### Health Check
- `GET /api/health` - Full health check (DB, Redis, Selenium, Tor, Anonymity)
- `GET /api/health/live` - Liveness probe
- `GET /api/health/ready` - Readiness probe
- `GET /api/health/anonymity` - Dedicated anonymity status (real IP vs Tor IP)

### Scraper
- `POST /api/scraper/scrape` - Initiate a single scraping task
- `POST /api/scraper/bulk` - Bulk scrape multiple URLs
- `GET /api/scraper/results` - Get all scraped results (paginated, searchable)
- `GET /api/scraper/results/{id}` - Get specific scraped site
- `GET /api/scraper/stats` - Comprehensive statistics (sites + job breakdown)
- `DELETE /api/scraper/results/{id}` - Delete a scraped site

### Dark Web Search
- `POST /api/search/` - Search .onion search engines (Ahmia, Torch, Tor66, etc.)
- `GET /api/search/engines` - List available dark web search engines

### Jobs
- `GET /api/jobs/` - List all jobs (filterable by status)
- `GET /api/jobs/status/{task_id}` - Get Celery task status
- `POST /api/jobs/{task_id}/cancel` - Cancel a task
- `DELETE /api/jobs/{job_id}` - Delete a job record

### Configuration
- `GET /api/config/` - List configurations
- `POST /api/config/` - Create configuration
- `PUT /api/config/{id}` - Update configuration
- `DELETE /api/config/{id}` - Delete configuration

## Development

### Running Locally (without Docker)

1. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   .\venv\Scripts\activate   # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run FastAPI:
   ```bash
   uvicorn app.main:app --reload
   ```

4. Run Celery Worker:
   ```bash
   celery -A app.core.celery_app worker --loglevel=info
   ```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Project Structure

```
dark-web-scraper/
├── app/
│   ├── api/
│   │   ├── endpoints/
│   │   │   ├── config.py       # Configuration CRUD endpoints
│   │   │   ├── health.py       # Health + anonymity endpoints
│   │   │   ├── jobs.py         # Job management endpoints
│   │   │   ├── scraper.py      # Scrape + bulk scrape endpoints
│   │   │   └── search.py       # Dark web search endpoints
│   │   └── routes.py           # API router
│   ├── core/
│   │   ├── celery_app.py       # Celery + Beat configuration
│   │   ├── config.py           # Pydantic settings (env-based)
│   │   └── database.py         # SQLAlchemy 2.0 async engine
│   ├── models/
│   │   ├── base.py             # Base model + timestamp mixin
│   │   ├── scrape_job.py       # Job tracking model
│   │   ├── scraped_site.py     # Scraped data model
│   │   └── scraper_config.py   # Scraper config model
│   ├── services/
│   │   ├── search_engines.py   # .onion search engine integration
│   │   ├── selenium_scraper.py # Selenium + privacy hardening
│   │   └── tasks.py            # Celery tasks (scrape, search, bulk)
│   └── main.py                 # FastAPI app + logging
├── alembic/                    # Database migrations
├── docker-compose.yml          # 7 services orchestrated
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Security & Privacy

- **Tor anonymity** — all scraping traffic routed through Tor proxy
- **Pre-scrape IP verification** — aborts if your real IP is detected
- **IP blacklist** — configure `BLACKLISTED_IPS` in `.env` with your real IPs
- **Tor exit node enforcement** — scraper refuses to run if not on a verified exit node
- **WebRTC leak prevention** — Chrome flags disable WebRTC, canvas, WebGL, audio fingerprinting
- **User agent rotation** — random UA selected per session from a pool of 8 browsers
- **DNS leak prevention** — all DNS forced through proxy
- **Non-root Docker containers**
- **Environment-based configuration** — no hardcoded credentials

## Dashboard UI

The Streamlit dashboard provides a visual interface for the scraper:

- **🔒 Sidebar Health Monitor** — Real-time status of DB, Redis, Selenium, Tor, and anonymity
- **🎯 Scraper Control Center** — Input URLs, select engine (Auto/BS4/Selenium), launch scrapes
- **📊 Job Monitor** — View last 10 jobs with status indicators
- **📚 Data Gallery** — Browse scraped sites with content previews
- **🔍 Dark Web Search** — Search .onion engines and auto-scrape results

Access at: http://localhost:8501

## Monitoring

- **Flower**: http://localhost:5555 - Monitor Celery tasks
- **Selenium VNC**: http://localhost:7900 - View browser sessions
- **Dashboard**: http://localhost:8501 - Streamlit UI

## License

MIT
