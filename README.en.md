# Job Research Agent · 职探

A Chinese-language job research workspace powered by GPT Researcher, FastAPI, SQLite and server-sent events. It generates job profiles, skill matrices, candidate gap analyses and an eight-week action plan.

## Quick start

Requires Python 3.11 or 3.12 and uv.

```bash
uv sync --frozen
cp .env.example .env
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010 and keep demo mode enabled. No API keys or paid calls are required for the demo. For live research, configure OpenAI and Tavily keys in `.env` and disable demo mode.

## Scope

This application adds recruitment-specific inputs and prompts, task APIs, streaming progress, report history, source classification and offline evaluation around GPT Researcher. It is not a from-scratch research engine or a candidate resume search system.

Uploaded files and histories are shared within a deployment. Local document mode can still send data to external model providers. Use only with trusted users; it is not an anonymous public service. Use one worker and one instance. See [security notes](SECURITY.md) before handling personal data.

## Checks and packaging

```bash
uv run pytest -q
node --check static/app.js
uv run python evals/run_eval.py
python3 scripts/build_release.py
```

The source archive excludes credentials and runtime data. Offline evaluation checks report structure, not factual correctness. Live API and Docker runtime validation are separate checks.

Application code: Apache License 2.0. See [third-party notices](THIRD_PARTY_NOTICES.md) for upstream attribution and the license metadata inconsistency in GPT Researcher 0.14.7.

See the [Chinese README](README.md) for configuration, Docker setup, architecture and limitations.
