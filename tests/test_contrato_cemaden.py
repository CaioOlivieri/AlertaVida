"""Teste de contrato: verifica que a API do CEMADEN ainda retorna
um schema compatível com CemadenSource.

Marcado @integration — roda apenas no job scheduled diário (09:00 UTC),
nunca em push. Faz request real ao endpoint público do CEMADEN.

Critério de saúde: pelo menos 80% dos itens recebidos devem ser aceitos
por CemadenSource. Abaixo disso, a falha pode ter duas causas:

1. Schema externo mudou — CEMADEN alterou nomes de campos, formatos, ou
   removeu campos obrigatórios. Investigar inspecionando payload bruto
   via scripts/inspect_cemaden_payload.py.

2. Validador interno ficou mais estrito — alguma mudança recente em
   Alerta.from_dict ou em campos obrigatórios. Investigar via git log
   em src/alertavida/domain/alerta.py.

Após B.1.b, este teste exercita o fluxo completo da CemadenSource (fetch,
parse, normalize, mapeamento), não apenas Alerta.from_dict isolado.
Aproxima o teste do contrato real usado em produção.
"""

import pytest

from alertavida.sources import FalhaDeColeta
from alertavida.sources.cemaden import URL_CEMADEN, CemadenSource


@pytest.mark.integration
def test_contrato_cemaden_aceita_resposta_real():
    source = CemadenSource()
    try:
        resultado = source.coletar()
    except FalhaDeColeta as exc:
        pytest.fail(
            f"Coleta falhou: {exc.causa}. Original: {exc.original!r}. "
            f"Verificar manualmente: {URL_CEMADEN}"
        )

    total = len(resultado.alertas) + resultado.descartados
    assert total > 0, (
        "CEMADEN retornou lista vazia — possível: API fora do ar, "
        f"endpoint mudou, ou janela sem alertas ativos. "
        f"Verificar manualmente: {URL_CEMADEN}"
    )

    taxa = len(resultado.alertas) / total
    assert taxa > 0.8, (
        f"Só {taxa:.0%} dos itens foram aceitos por CemadenSource "
        f"({len(resultado.alertas)}/{total}). Causa possível: "
        f"(1) schema do CEMADEN mudou — inspecionar payload via "
        f"scripts/inspect_cemaden_payload.py; "
        f"(2) validador interno ficou mais estrito — verificar git log "
        f"em src/alertavida/domain/alerta.py e domain/enums.py."
    )
