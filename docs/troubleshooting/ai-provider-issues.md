# AI Provider Issues

Use this page when digest generation fails during summarization, cover generation, or media processing.

## Common Symptoms

- digest generation starts but never completes successfully
- logs mention missing provider credentials
- Ollama requests fail
- media transcription falls back unexpectedly

## Check the Basics

Review your `ghostwriter/.env`:

- `AI_PROVIDER`
- `OPENAI_API_KEY` and `OPENAI_MODEL`
- `GEMINI_API_KEY` and `GEMINI_MODEL`
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL`

Only configure the variables relevant to the provider you are actually using.

## OpenAI

Check:

- the API key is set
- the selected model is valid for your account
- outbound network access works from the container or host

## Gemini

Check:

- the Gemini API key is set
- the model name matches the deployment you intend to use

## Ollama

If using the local Ollama sidecar:

```bash
cd ghostwriter
docker compose --profile with-ollama up -d
docker exec ollama ollama pull llama3.2
```

Then confirm the configured `OLLAMA_BASE_URL` is reachable from the Ghostwriter container.

## Related Pages

- [Ghostwriter Docker installation](../installation/ghostwriter-docker.md)
- [Startup and health checks](startup-and-health-checks.md)
