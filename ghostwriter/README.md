# Ghostwriter

RSS digest generation service for Epilogue. Aggregates RSS feeds, extracts article content, generates AI summaries, and compiles them into daily EPUB digests.

## Features

- **RSS/Atom Feed Aggregation** - Parse and deduplicate articles from multiple feeds
- **Content Extraction** - Clean article extraction via Trafilatura
- **AI Summarization** - Provider-agnostic AI via LiteLLM (OpenAI, Gemini, Ollama)
- **EPUB Generation** - Compile articles into e-reader friendly digests
- **Scheduled Jobs** - Automatic morning/noon/evening digest generation
- **REST API** - Full API for feed management and digest downloads

## Quick Start

### With Docker (Recommended)

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your settings

# Start with local Ollama
docker compose up -d

# Pull the Ollama model (first time only)
docker exec ollama ollama pull llama3.2

# Verify health
curl http://localhost:8080/health
```

### Cloud AI Only (No Ollama)

```bash
# Set your API key
export OPENAI_API_KEY=sk-...

# Start without Ollama
docker compose -f docker-compose.cloud.yml up -d
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export AI_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434

# Run
uvicorn app.main:app --reload --port 8080
```

## API Reference

### Feeds

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/feeds` | List all feeds |
| `POST` | `/feeds` | Create a feed |
| `POST` | `/feeds/sync` | Bulk sync from client |
| `DELETE` | `/feeds/{id}` | Remove a feed |

### Digests

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/digests/trigger` | Start manual digest |
| `GET` | `/digests` | List digests |
| `GET` | `/digests/latest` | Get latest completed |
| `GET` | `/digests/{id}/status` | Poll job progress |
| `GET` | `/digests/{filename}` | Download EPUB |
| `DELETE` | `/digests/{filename}` | Delete digest |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health |
| `GET` | `/config` | Current configuration |

## Configuration

All configuration via environment variables. See `.env.example` for full list.

### Key Settings

```bash
# AI Provider: openai, gemini, ollama
AI_PROVIDER=ollama

# Scheduling (24h format)
SCHEDULE_MORNING=07:00
SCHEDULE_EVENING=18:00

# API Authentication
API_KEY=your-secret-key
```

## Architecture

```
app/
├── api/            # FastAPI routes
├── core/           # Config, database, security
├── models/         # SQLModel schemas
├── services/       # LLM, content processor, EPUB
└── worker/         # Bindery pipeline, scheduler
```

## License

MIT
