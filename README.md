# Dark Web Scraper

Full-stack scraping platform for .onion sites with built-in anonymity, entity extraction, and uptime monitoring. Runs everything in Docker — no manual Tor setup needed.

![Dashboard Overview](https://github.com/user-attachments/assets/2745feaa-3547-40d0-ad7f-5a6fe7805a73)

## What it does

- **Scrapes .onion sites** through Tor with automatic IP rotation
- **Smart scraping** — tries lightweight BS4 first, escalates to Selenium if JavaScript is needed
- **Entity extraction** — pulls crypto wallets, PGP keys, emails, onion links from scraped content
- **LLM analysis** (optional) — uses OpenAI to summarize pages, score legitimacy, categorize sites
- **Dark web search** — queries Ahmia, Torch, Tor66, and other .onion search engines
- **Site monitoring** — tracks uptime, detects content changes, stores version history
- **Circuit rotation** — requests a fresh Tor exit node before every scrape
- **Web dashboard** — Streamlit UI for launching scrapes, viewing results, monitoring jobs

## Stack

- FastAPI + Celery for async task processing
- PostgreSQL for data storage
- Selenium Grid for JavaScript-heavy sites
- Tor proxy with control port for circuit rotation
- Streamlit dashboard
- Redis for Celery broker
- Everything orchestrated via Docker Compose

## Getting started

**Requirements:** Docker + Docker Compose

```bash
git clone <your-repo-url>
cd dark-web-scraper
cp .env.example .env
docker compose up -d
```

Wait ~2 minutes for Tor to bootstrap, then open:

- **Dashboard**: http://localhost:8501 (main UI)
- **API docs**: http://localhost:8000/docs
- **Flower**: http://localhost:5555 (Celery monitoring)

## Features

### 1. Smart Scraping Strategy

The scraper tries BeautifulSoup4 first (fast, lightweight). If the page looks like it needs JavaScript (short content, JS-required patterns), it automatically escalates to Selenium.

You can also force a specific engine:
- `auto` — BS4 first, escalate if needed (default)
- `bs4` — lightweight only
- `selenium` — full browser rendering

### 2. Entity Extraction

Every scraped page is analyzed for:
- **Crypto wallets** (Bitcoin, Ethereum)
- **PGP public keys**
- **Email addresses**
- **Onion links** (other .onion sites mentioned)

If you set `LLM_API_KEY` in `.env`, it also sends the page to OpenAI for:
- One-sentence summary
- Legitimacy score (0-100)
- Category (Market, Forum, News, etc.)

### 3. Site Pulse Monitoring

Track .onion sites over time:
- Set check frequency (every N hours)
- Records uptime/downtime
- Detects content changes via SHA-256 hash comparison
- Stores version history with size deltas
- Visual uptime bar in the dashboard

![Monitor Tab](docs/screenshots/monitor-tab.png)

### 4. Tor Circuit Rotation

Before every scrape, the system sends a `SIGNAL NEWNYM` to Tor's control port, forcing a fresh exit node. This prevents IP-based blocking and improves anonymity.

The worker waits 3 seconds after the signal to let the new circuit stabilize.

### 5. Dark Web Search

Search multiple .onion search engines at once:
- Ahmia
- Torch
- Tor66
- Not Evil
- Candle
- Excavator

Results are deduplicated and can be auto-scraped with one click.

![Search Results](docs/screenshots/search-results.png)

## Configuration

Edit `.env` to customize:

```bash
# Tor circuit rotation
TOR_CONTROL_PORT=9051
TOR_CONTROL_PASSWORD=darkweb_tor_pass

# IP security — add your real IPs here (scraper will abort if detected)
BLACKLISTED_IPS=["1.2.3.4"]
REQUIRE_TOR_EXIT_NODE=true

# Smart scraping
DEFAULT_SCRAPE_ENGINE=auto
BS4_MIN_CONTENT_LENGTH=200

# Entity extraction (optional)
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

## API

Full REST API at `http://localhost:8000/docs`

**Key endpoints:**
- `POST /api/scraper/scrape` — queue a scrape
- `POST /api/scraper/bulk` — bulk scrape
- `GET /api/scraper/results` — list scraped sites
- `POST /api/search/` — search dark web
- `GET /api/monitor/` — list monitored sites
- `POST /api/monitor/{id}/check` — trigger manual check
- `GET /api/health` — system health + anonymity status

## How it works

1. **User submits a URL** via dashboard or API
2. **Celery worker** picks up the task
3. **Tor circuit rotates** — `SIGNAL NEWNYM` sent to control port, 3s sleep
4. **Smart scraper** tries BS4, escalates to Selenium if needed
5. **Anonymity check** — verifies we're on a Tor exit node, aborts if real IP detected
6. **Content extracted** — HTML, clean text, links, meta description
7. **Entity extraction** — regex pulls crypto/PGP/emails/onion links
8. **LLM analysis** (if enabled) — OpenAI summarizes and scores the page
9. **Data saved** to PostgreSQL with full metadata
10. **Job status updated** — visible in dashboard and Flower

## Security

- All traffic routed through Tor (SOCKS5 + HTTP proxy)
- Pre-scrape IP verification (aborts if your real IP leaks)
- Configurable IP blacklist
- Tor exit node enforcement
- WebRTC/Canvas/WebGL disabled in Chrome
- Random user agent rotation
- DNS forced through proxy
- Circuit rotation before every request

## Project structure

```
app/
├── api/endpoints/     # REST endpoints (scraper, search, monitor, jobs, health)
├── core/              # Config, database, Celery setup
├── models/            # SQLAlchemy models (ScrapedSite, ScrapeJob, SiteMonitor, UptimeRecord)
├── services/
│   ├── bs4_scraper.py          # Lightweight scraper
│   ├── selenium_scraper.py     # Full browser scraper
│   ├── smart_scraper.py        # Orchestrator (BS4 → Selenium escalation)
│   ├── entity_extractor.py     # Regex + LLM entity extraction
│   ├── search_engines.py       # .onion search integration
│   ├── tor_circuit.py          # NEWNYM signal handler
│   └── tasks.py                # Celery tasks
└── ui/dashboard.py    # Streamlit UI
```

## Dashboard tabs

### 🎯 Scraper
Paste a .onion URL, pick an engine (auto/bs4/selenium), launch the scrape. Bulk scrape mode lets you queue multiple URLs at once.

### 📊 Jobs
Live feed of the last 10 tasks with status (running/completed/failed). Shows scrape jobs, search jobs, and monitor checks.

### 📚 Gallery
Browse all scraped sites. Each card shows:
- Title, URL, meta description
- Status code, engine used, response time
- Content length, link count, HTML size
- Entity tags (crypto wallets, PGP keys, emails, onion links)
- AI analysis (if LLM enabled)

![Gallery View](docs/scree<img width="1884" height="784" alt="Screenshot 2026-03-20 123109" src="https://github.com/user-attachments/assets/2d1e7bff-873c-4066-8eca-b6eea543d9b6" />
nshots/gallery.png)

### 🔍 Search
Query multiple .onion search engines, view results inline, scrape them with one click.

### 💓 Monitor
Add URLs to track over time. Set check frequency, view uptime percentage, see content version history. Visual uptime bar shows last 7 days of checks (green = up, amber = changed/timeout, red = down).

## Monitoring tools

- **Flower** (http://localhost:5555) — Celery task queue, worker stats, task history
- **Selenium VNC** (http://localhost:7900) — watch browser sessions in real-time
- **Health endpoint** (`/api/health`) — JSON status of all services + anonymity check

## Development

Run without Docker (requires local PostgreSQL, Redis, Selenium, Tor):

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
celery -A app.core.celery_app worker --loglevel=info
celery -A app.core.celery_app beat --loglevel=info
streamlit run app/ui/dashboard.py
```

Database migrations (if you modify models):

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Troubleshooting

**Tor not connecting:** Wait 2-3 minutes after `docker compose up` for Tor to bootstrap. Check `docker compose logs tor-proxy`.

**IP leak detected:** Make sure `BLACKLISTED_IPS` in `.env` contains your real IP. The scraper will abort if it detects a leak.

**Selenium timeout:** Increase `SCRAPER_TIMEOUT` in `.env` or check `docker compose logs selenium-chrome`.

**Circuit rotation failing:** Verify `TOR_CONTROL_PASSWORD` matches in `.env` and `docker-compose.yml`. Check port 9051 is exposed.

## Disclaimer

This project is provided strictly for lawful research. You are solely responsible for how you use it. Accessing dark web content may be illegal in your jurisdiction, and sending sensitive data to third-party APIs (including LLMs) can expose information outside your control. Use at your own risk and make sure you comply with local laws, institutional policies, and any API terms of service.

## License

MIT
