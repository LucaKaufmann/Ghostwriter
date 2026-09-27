# Synthetic reading and listening journey

This harness exercises Ghostwriter with temporary SQLite storage and files. The API test triggers the real Bindery pipeline, verifies its persisted article and EPUB, requests a PDF through the real renderer, queues a podcast episode, observes an injected provider failure, retries, and checks the private feed and retention protection. The browser test runs a disposable FastAPI process behind a transparent same-origin Playwright proxy. It generates a digest from the UI, reads the local HTML source in reader mode, and uses the Episodes screen to retry the visible failure.

Only external boundaries are synthetic: the RSS transport returns fixed XML, which the real feed parser and Bindery selection process; content extraction returns a deterministic paragraph; cover generation and script creation use fixed results; the audio provider first raises an error and then uses `ffmpeg` to produce 61 seconds of valid silent MP3. The real pipeline, SQLModel storage, EPUB and PDF renderers, reader fetch and Readability extraction, episode state machine, audio streaming, and private RSS endpoints still execute. No source account, provider key, real article, or paid API is used. The fixture server disables `.env` loading, clears all configured settings and provider/proxy environment variables, and restricts socket sends/connections and DNS calls to loopback before app imports. `ALLOW_PRIVATE_HOSTS=true` applies only inside that disposable server so its reader can fetch its own HTML source; the backend test suite's global network guard is unchanged.

From `ghostwriter` run the API check with a Python environment containing `requirements.txt`, pytest, and `ffmpeg`:

```sh
python -m pytest -q tests/test_reading_listening_journey.py
```

From `ghostwriter/frontend`, after `npm ci`, run the live browser check with the same Python environment selected explicitly:

```sh
JOURNEY_PYTHON=/path/to/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts
```

The backend binds a free loopback port and uses a temporary data/output directory. The frontend uses port 4187 by default; set `JOURNEY_FRONTEND_PORT` to another free port when needed. Playwright always starts its own preview server. Both tests bound polling to 60 attempts. The browser test writes `journey-reader.png`, `journey-failure.png`, `journey-ready.png`, and `trace.zip` under `frontend/test-results/`; the three inspected synthetic screenshots are also kept in [fixture-journey-assets](fixture-journey-assets/). The trace is generated afresh per run and contains only disposable fixture credentials, so do not reuse it with a real environment.

The harness verifies rendered web reading and server-side episode delivery. It does not measure real speech quality, paid-provider behavior, offline clients, or device scheduling. Its audio is intentionally silent, while the episode metadata truthfully reports the generated file's 61-second duration.
