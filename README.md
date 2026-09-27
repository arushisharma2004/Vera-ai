# Vera — magicpin AI Challenge

A public HTTP implementation of the Vera merchant-AI assistant.

## API
- `POST /v1/context` — idempotent, versioned context ingestion
- `POST /v1/tick` — proactive trigger evaluation
- `POST /v1/reply` — synchronous multi-turn response
- `GET /v1/healthz` — liveness
- `GET /v1/metadata` — bot identity

## Design
The bot uses the challenge's four-context model: category, merchant, trigger, and optional customer. Trigger kinds route to category-appropriate message strategies, while the actual copy is grounded in supplied fields such as offers, performance, dates, research metadata, customer state, and available slots.

The implementation intentionally has no runtime dependency on an external LLM or third-party API. This keeps latency predictable and makes the behavior reproducible under judge replay. Unknown trigger kinds use a grounded fallback rather than inventing facts.

Customer messages are conservative: they use explicit relationship/trigger information and avoid making unsupported claims. Merchant messages prioritize specific service+price offers, concrete metrics, and explicit intent handoff.

## Deploy
Deploy as a Python web service with:
`pip install -r requirements.txt`
and:
`gunicorn app:app`

The service listens on the platform-provided `PORT`.
