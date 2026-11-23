"""Contrato com o endpoint real de avisos do INMET (issue #153).

Roda só com `-m integration` (job diário `contrato` do CI). O endpoint é o
backend do portal, não uma API documentada: este teste é o aviso de mudança.
"""

import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from alertavida.sources._http import fetch_com_retry, opener_padrao
from alertavida.sources.inmet import (
    URL_INMET_AVISOS,
    USER_AGENT_INMET,
    InmetSource,
    montar_aviso,
)

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
URL_CAP = "https://apiprevmet3.inmet.gov.br/avisos/rss/{id}"


@pytest.mark.integration
def test_contrato_inmet_envelope_e_avisos_validos():
    avisos, descartados = InmetSource().coletar()
    assert descartados == 0, "o INMET publicou um aviso que o coletor não entende"
    for aviso in avisos:
        assert aviso.codigo_cap.startswith("urn:oid:2.49.0.0.76.0."), aviso.codigo_cap
        assert aviso.codigos_ibge, f"{aviso.codigo_cap} sem geocodes"


@pytest.mark.integration
def test_contrato_inmet_horario_do_json_concorda_com_o_cap():
    """O `inicio` lido como UTC-3 tem de ser o `onset` do CAP oficial — é a
    prova de que o `Z` de `data_inicio` continua mentindo e de que a nossa
    leitura continua certa."""
    import json

    from alertavida.domain.enums import FonteDado

    raw = fetch_com_retry(
        URL_INMET_AVISOS, fonte=FonteDado.INMET, opener=opener_padrao, user_agent=USER_AGENT_INMET
    )
    payload = json.loads(raw)
    itens = payload["hoje"] + payload["futuro"]
    if not itens:
        pytest.skip("nenhum aviso ativo no INMET agora — nada para comparar")
    item = itens[0]
    cap = ET.fromstring(
        fetch_com_retry(
            URL_CAP.format(id=item["id"]),
            fonte=FonteDado.INMET,
            opener=opener_padrao,
            user_agent=USER_AGENT_INMET,
        )
    )
    assert cap.findtext("cap:identifier", namespaces=CAP_NS) == item["codigo"]
    onset = datetime.fromisoformat(cap.findtext("cap:info/cap:onset", namespaces=CAP_NS))
    expires = datetime.fromisoformat(cap.findtext("cap:info/cap:expires", namespaces=CAP_NS))
    aviso = montar_aviso(item)
    assert aviso.inicio == onset
    assert aviso.fim == expires
