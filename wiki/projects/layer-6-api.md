status: blocked
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-06-11

# Layer 6: API Layer (blocked)

FastAPI-based REST API. Planned endpoints:

- `GET /alertas/ativos`
- `GET /alertas/por-municipio/{ibge}`
- `GET /alertas/historico`
- `GET /alertas/proximos?lat={lat}&lon={lon}&raio={km}`

Auto-documentation via OpenAPI/Swagger. Existing `BackgroundScheduler` continues working alongside FastAPI.
