"""Teste de contrato: verifica que a API do CEMADEN ainda retorna
um schema compatível com Alerta.from_dict."""

import json

import pytest

from alertavida.domain.alerta import Alerta
from alertavida.monitor import URL, fetch_alertas_com_retry, normalize_alert_list


def _tenta_montar(item: dict) -> bool:
    try:
        Alerta.from_dict(item)
        return True
    except Exception:
        return False


@pytest.mark.integration
def test_contrato_cemaden_aceita_resposta_real():
    raw = fetch_alertas_com_retry(URL)
    payload = json.loads(raw.decode("utf-8"))
    itens = normalize_alert_list(payload)

    assert len(itens) > 0, "CEMADEN retornou lista vazia — API fora do ar?"

    aceitos = sum(1 for it in itens if _tenta_montar(it))
    taxa = aceitos / len(itens)

    assert taxa > 0.8, (
        f"Só {taxa:.0%} dos alertas foram aceitos pelo Alerta.from_dict "
        f"({aceitos}/{len(itens)}) — schema do CEMADEN pode ter mudado"
    )
