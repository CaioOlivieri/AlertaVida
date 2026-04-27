import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"


def pick_value(item, possible_keys, default="N/A"):
    for key in possible_keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return default


def normalize_alert_list(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("alertas", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    return []


def main():
    request = Request(URL, headers={"User-Agent": "monitor-alertas/1.0"})

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
    except HTTPError as exc:
        print(f"Erro HTTP ao consultar a API: {exc.code} {exc.reason}")
        sys.exit(1)
    except URLError as exc:
        print(f"Erro de conexao ao consultar a API: {exc.reason}")
        sys.exit(1)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"Falha ao interpretar JSON: {exc}")
        sys.exit(1)

    alertas = normalize_alert_list(payload)
    if not alertas:
        print("Nenhum alerta encontrado.")
        return

    primeiro_alerta = next((a for a in alertas if isinstance(a, dict)), None)
    if primeiro_alerta:
        print("Chaves do primeiro alerta:")
        print(", ".join(sorted(primeiro_alerta.keys())))
        print("-" * 80)

    for alerta in alertas:
        if not isinstance(alerta, dict):
            continue

        municipio = pick_value(alerta, ("municipio", "nome_municipio", "city", "cidade"))
        estado = pick_value(alerta, ("uf", "estado", "state"))
        tipo_evento = pick_value(
            alerta,
            ("tipo_evento", "evento", "tipo", "desastre", "event_type"),
        )
        nivel = pick_value(alerta, ("nivel", "nivel_alerta", "severity", "grau"))
        data_criacao = pick_value(
            alerta,
            (
                "data_criacao",
                "dataCriacao",
                "datahoracriacao",
                "created_at",
                "dt_criacao",
            ),
        )

        print(
            f"Municipio: {municipio} | Estado: {estado} | "
            f"Evento: {tipo_evento} | Nivel: {nivel} | Criacao: {data_criacao}"
        )


if __name__ == "__main__":
    main()
