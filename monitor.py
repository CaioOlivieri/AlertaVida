import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from database import alerta_existe, criar_banco, salvar_alerta


URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"


def pick_value(item, possible_keys, default="N/A"):
    for key in possible_keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return default


def montar_alerta(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None

    raw_cod = pick_value(
        item, ("codigoalerta", "cod_alerta", "id", "codigo"), default=None
    )
    if raw_cod is None or raw_cod == "":
        return None
    try:
        cod_alerta = int(raw_cod)
    except (TypeError, ValueError):
        return None

    return {
        "cod_alerta": cod_alerta,
        "municipio": str(
            pick_value(item, ("municipio", "nome_municipio", "cidade"), default="N/A")
        ),
        "uf": str(pick_value(item, ("uf", "estado", "state"), default="N/A")),
        "evento": str(
            pick_value(
                item,
                (
                    "tipo_evento",
                    "evento",
                    "tipo",
                    "desastre",
                    "tipoevento",
                ),
                default="N/A",
            )
        ),
        "nivel": str(
            pick_value(item, ("nivel", "nivel_alerta", "severity", "grau"), default="N/A")
        ),
        "datahoracriacao": str(
            pick_value(
                item,
                (
                    "datahoracriacao",
                    "data_criacao",
                    "dataCriacao",
                    "dt_criacao",
                ),
                default="N/A",
            )
        ),
    }


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
    criar_banco()
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
    total_recebido = len(alertas)
    novos = 0
    ja_existentes = 0
    descartados = 0

    if not alertas:
        print("Nenhum alerta encontrado.")
    else:
        for alerta in alertas:
            mapeado = montar_alerta(alerta)
            if mapeado is None:
                descartados += 1
                continue

            cod = mapeado["cod_alerta"]
            mun = mapeado["municipio"]
            uf = mapeado["uf"]
            ev = mapeado["evento"]
            try:
                if alerta_existe(cod):
                    ja_existentes += 1
                    print(f"[JÁ VISTO] {mun} | {uf} | {ev}")
                else:
                    salvar_alerta(mapeado)
                    novos += 1
                    print(f"[NOVO] {mun} | {uf} | {ev}")
            except Exception as exc:  # noqa: BLE001 — captura por item, segue o loop
                print(f"[ERRO] cod_alerta={cod} — {exc}")

    print()
    print("=== Resumo ===")
    print(f"Total recebido: {total_recebido}")
    print(f"Novos salvos: {novos}")
    print(f"Já existentes: {ja_existentes}")
    print(f"Descartados: {descartados}")


if __name__ == "__main__":
    main()

