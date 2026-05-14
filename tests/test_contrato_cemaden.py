"""Teste de contrato: verifica que a API do CEMADEN ainda retorna
um schema compatível com Alerta.from_dict.

Marcado @integration — roda apenas no job scheduled diário (09:00 UTC),
nunca em push. Faz request real ao endpoint público do CEMADEN.

Critério de saúde: pelo menos 80% dos itens recebidos devem ser aceitos
pelo Alerta.from_dict. Abaixo disso, a falha pode ter duas causas:

1. Schema externo mudou — CEMADEN alterou nomes de campos, formatos, ou
   removeu campos obrigatórios. Investigar inspecionando payload bruto
   via scripts/inspect_cemaden_payload.py.

2. Validador interno ficou mais estrito — alguma mudança recente em
   Alerta.from_dict ou em campos obrigatórios. Investigar via git log
   em src/alertavida/domain/alerta.py.

O teste NÃO captura exceções que não sejam ValueError. Bugs nossos
(TypeError em assinatura, AttributeError em campo, etc.) DEVEM propagar
imediatamente para diagnóstico claro — não devem ser silenciados como
'item rejeitado'.
"""

import json

import pytest

from alertavida.domain.alerta import Alerta
from alertavida.domain.enums import FonteDado
from alertavida.monitor import URL, fetch_alertas_com_retry, normalize_alert_list


def _tenta_montar(item: dict) -> bool:
    """Retorna True se o item passou pelo validador de Alerta, False se
    foi legitimamente rejeitado.

    Captura APENAS ValueError — única exceção que Alerta.from_dict
    documenta levantar para itens malformados ou incompletos. Qualquer
    outra exceção (TypeError, AttributeError, KeyError, etc.) é bug
    interno e propaga para diagnóstico imediato no CI.
    """
    try:
        Alerta.from_dict(item, fonte=FonteDado.CEMADEN)
        return True
    except ValueError:
        return False


@pytest.mark.integration
def test_contrato_cemaden_aceita_resposta_real():
    raw = fetch_alertas_com_retry(URL)
    payload = json.loads(raw.decode("utf-8"))
    itens = normalize_alert_list(payload)

    assert len(itens) > 0, (
        "CEMADEN retornou lista vazia — possível: API fora do ar, "
        "endpoint mudou, ou janela sem alertas ativos. "
        "Verificar manualmente: " + URL
    )

    aceitos = sum(1 for it in itens if _tenta_montar(it))
    taxa = aceitos / len(itens)

    assert taxa > 0.8, (
        f"Só {taxa:.0%} dos itens foram aceitos por Alerta.from_dict "
        f"({aceitos}/{len(itens)}). Causa possível: "
        f"(1) schema do CEMADEN mudou — inspecionar payload via "
        f"scripts/inspect_cemaden_payload.py; "
        f"(2) validador interno ficou mais estrito — verificar git log "
        f"em src/alertavida/domain/alerta.py e domain/enums.py."
    )
