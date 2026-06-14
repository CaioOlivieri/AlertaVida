"""Fixtures sintéticas mínimas da NASA EONET v3 — Camada 4 Parte C.1.a.

NÃO são amostras reais (essas ficam em data/samples/eonet/, gitignored).
São eventos construídos à mão, mínimos e determinísticos, cobrindo os
casos que NasaEonetSource precisa tratar:

- evento Point dentro do Brasil   → escopo BRASIL
- evento Point no exterior        → escopo INTERNACIONAL
- evento com N fixes              → source usa o fix MAIS RECENTE (por data)
- evento sem geometry             → descartado (sem coordenadas)
- categoria fora do mapeamento    → tipo_evento INDETERMINADO

Shape fiel ao payload v3 confirmado em scripts/inspect_eonet_payload.py
(_first_geometry_point, _category_ids) e no relatório empírico
tests/fixtures/eonet/README.md / wiki/raw/analise-eonet-2026-05-18.md:

    {"events": [
        {"id": "EONET_...", "title": ..., "closed": null,
         "categories": [{"id": "wildfires", "title": ...}],
         "geometry": [
             {"type": "Point", "coordinates": [lon, lat], "date": "...Z",
              "magnitudeValue": ..., "magnitudeUnit": ...}
         ]}
    ]}

Atenção: coordinates segue ordem GeoJSON [longitude, latitude].
"""

from __future__ import annotations

from typing import Any


def fix_point(
    coordinates: tuple[float, float],
    date: str,
    *,
    magnitude_value: float | None = None,
    magnitude_unit: str | None = None,
) -> dict[str, Any]:
    """Um fix de geometria Point. `coordinates` em ordem GeoJSON (lon, lat)."""
    fix: dict[str, Any] = {
        "type": "Point",
        "coordinates": [coordinates[0], coordinates[1]],
        "date": date,
    }
    if magnitude_value is not None:
        fix["magnitudeValue"] = magnitude_value
        fix["magnitudeUnit"] = magnitude_unit
    return fix


def evento(
    *,
    id: str,
    categoria: str,
    geometry: list[dict[str, Any]],
    title: str = "Evento sintético de teste",
    closed: str | None = None,
) -> dict[str, Any]:
    """Um evento EONET v3 com uma única categoria."""
    return {
        "id": id,
        "title": title,
        "closed": closed,
        "categories": [{"id": categoria, "title": categoria}],
        "geometry": geometry,
    }


def payload(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    """Envelope de resposta da API EONET v3: {"events": [...]}."""
    return {"title": "EONET Events (synthetic)", "events": list(eventos)}


# ---------------------------------------------------------------------------
# Eventos canônicos — um por cenário que a source precisa cobrir
# ---------------------------------------------------------------------------

# Point dentro do bbox do Brasil (lat -3, lon -60: Amazonas) → escopo BRASIL.
INCENDIO_BRASIL: dict[str, Any] = evento(
    id="EONET_BR_FIRE",
    categoria="wildfires",
    title="Wildfire - Amazonas, Brazil",
    geometry=[
        fix_point(
            (-60.0, -3.0), "2026-05-18T00:00:00Z", magnitude_value=1200.0, magnitude_unit="acres"
        ),
    ],
)

# Point fora do Brasil (lat 38, lon -120: California) → escopo INTERNACIONAL.
INCENDIO_EXTERIOR: dict[str, Any] = evento(
    id="EONET_US_FIRE",
    categoria="wildfires",
    title="Wildfire - California, USA",
    geometry=[fix_point((-120.0, 38.0), "2026-05-18T00:00:00Z")],
)

# Múltiplos fixes em ordem NÃO-cronológica: o mais recente (índice 1) está no
# meio da lista de propósito, para que o teste verifique seleção POR DATA, não
# por posição. Fix mais recente: 2026-05-18T12:00:00Z em (-42, -22), no Brasil.
TEMPESTADE_MULTI_FIX: dict[str, Any] = evento(
    id="EONET_STORM_MULTI",
    categoria="severeStorms",
    title="Severe Storm - South Atlantic",
    geometry=[
        fix_point((-41.0, -21.0), "2026-05-17T00:00:00Z"),
        fix_point((-42.0, -22.0), "2026-05-18T12:00:00Z"),  # mais recente (data)
        fix_point((-40.0, -20.0), "2026-05-16T00:00:00Z"),
    ],
)

# Sem geometry → sem coordenadas → deve ser descartado pela source.
EVENTO_SEM_GEOMETRY: dict[str, Any] = evento(
    id="EONET_NO_GEOM",
    categoria="wildfires",
    title="Malformado - sem geometry",
    geometry=[],
)

# Categoria fora do mapeamento conhecido → tipo_evento INDETERMINADO.
CATEGORIA_DESCONHECIDA: dict[str, Any] = evento(
    id="EONET_UNKNOWN_CAT",
    categoria="waterColor",
    title="Categoria não mapeada",
    geometry=[fix_point((-45.0, -23.0), "2026-05-18T00:00:00Z")],
)
