import json
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alertavida.database import alerta_existe, criar_banco, salvar_alerta
from alertavida.domain import Alerta

if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"


def pick_value(item, possible_keys, default="N/A"):
    for key in possible_keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return default


def montar_alerta(item: dict) -> Alerta:
    """Converte item bruto do CEMADEN em Alerta de domínio.

    Levanta ValueError se o item não tiver os campos obrigatórios.
    """
    if not isinstance(item, dict):
        raise ValueError(f"item deve ser dict, recebido {type(item).__name__}")
    return Alerta.from_dict(item)


def normalize_alert_list(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("alertas", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    return []


def fetch_alertas_com_retry(
    url: str,
    max_tentativas: int = 4,
    backoff_inicial: float = 2.0,
) -> bytes:
    ultima_excecao = None
    request = Request(url, headers={"User-Agent": "monitor-alertas/1.0"})

    for tentativa in range(max_tentativas):
        tentativa_humana = tentativa + 1
        print(f"[Tentativa {tentativa_humana}/{max_tentativas}]")
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            ultima_excecao = exc
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                raise
        except (URLError, socket.timeout) as exc:
            ultima_excecao = exc

        if tentativa_humana < max_tentativas:
            espera = backoff_inicial * (2**tentativa)
            print(f"Aguardando {espera:g}s antes da próxima tentativa...")
            time.sleep(espera)

    assert ultima_excecao is not None
    raise ultima_excecao


def executar_ingestao():
    criar_banco()
    try:
        raw = fetch_alertas_com_retry(URL)
    except (HTTPError, URLError, socket.timeout) as exc:
        print(f"Erro ao consultar a API após múltiplas tentativas: {exc}")
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
    erros = 0

    if not alertas:
        print("Nenhum alerta encontrado.")
    else:
        for alerta in alertas:
            try:
                mapeado = montar_alerta(alerta)
            except ValueError:
                descartados += 1
                continue

            cod = mapeado.cod_alerta
            mun = mapeado.municipio.nome
            uf = mapeado.municipio.uf
            ev = mapeado.tipo_evento.value
            try:
                if alerta_existe(cod):
                    ja_existentes += 1
                    print(f"[JÁ VISTO] {mun} | {uf} | {ev}")
                else:
                    salvar_alerta(mapeado)
                    novos += 1
                    print(f"[NOVO] {mun} | {uf} | {ev}")
            except Exception as exc:  # noqa: BLE001 — captura por item, segue o loop
                erros += 1
                print(f"[ERRO] cod_alerta={cod} — {exc}")

    print()
    print("=== Resumo ===")
    print(f"Total recebido: {total_recebido}")
    print(f"Novos salvos: {novos}")
    print(f"Já existentes: {ja_existentes}")
    print(f"Descartados: {descartados}")
    print(f"Erros: {erros}")

    assert novos + ja_existentes + descartados + erros == total_recebido, (
        f"Contadores inconsistentes: {novos}+{ja_existentes}+{descartados}+{erros} != {total_recebido}"
    )


main = executar_ingestao


if __name__ == "__main__":
    executar_ingestao()
