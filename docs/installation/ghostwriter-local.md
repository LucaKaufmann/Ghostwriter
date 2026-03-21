# Ghostwriter Installation from Source

This path is best for local evaluation and development. For normal self-hosted use, prefer [Ghostwriter with Docker](ghostwriter-docker.md).

## Prerequisites

- Python 3
- Node.js and npm for the web UI
- System libraries required by WeasyPrint if you plan to render PDFs outside Docker

Recommended system libraries for host-based runs:

- `cairo`
- `pango`
- `gdk-pixbuf`
- system fonts such as DejaVu

## Backend Setup

```bash
cd ghostwriter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your environment:

```bash
export AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export JWT_SECRET=change-this
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8080
```

## Frontend Setup

In a separate terminal:

```bash
cd ghostwriter/frontend
npm install
npm run dev
```

The frontend dev server proxies `/api` to `http://localhost:8080`.

## When to Use This Path

Use this install mode if you need to:

- inspect server behavior locally
- develop new features
- test configuration changes without rebuilding containers

## Next Step

For contributor workflow, continue with [Development and contributing](../development/contributing.md).
