"""Testes de contrato parametrizados — reutilizáveis por toda DataSource concreta.

Uso típico (em tests/sources/test_cemaden.py, B.1.b em diante):

    from tests.sources.contrato import verificar_contrato_data_source

    def test_cemaden_obedece_contrato(monkeypatch):
        monkeypatch.setattr(...)  # mock urllib retornando fixture
        verificar_contrato_data_source(lambda: CemadenSource())

Quando NasaEonetSource entrar (Parte C), basta:

    def test_eonet_obedece_contrato(monkeypatch):
        monkeypatch.setattr(...)
        verificar_contrato_data_source(lambda: NasaEonetSource())

Sem reescrever os testes do contrato. Mudanças no contrato (campo novo
em DataSource, invariante nova em ResultadoColeta) quebram TODAS as
sources em uma única definição. Manutenção centralizada.
"""

from datetime import datetime, timezone
from typing import Callable

from alertavida.domain.enums import FonteDado
from alertavida.sources import DataSource, ResultadoColeta


def verificar_contrato_data_source(
    source_factory: Callable[[], DataSource],
) -> None:
    """Roda invariantes do contrato em qualquer implementação de DataSource.

    A `source_factory` deve construir uma DataSource configurada para
    sucesso (com mocks/fixtures já aplicados no contexto de chamada).
    Levanta AssertionError com mensagem indicando qual invariante falhou.

    Invariantes verificadas:
    - DataSource é instância da ABC
    - fonte retorna FonteDado (não string)
    - fonte é uppercase e está no conjunto fechado FonteDado
    - coletar() retorna ResultadoColeta
    - Todos os alertas retornados têm fonte == source.fonte (consistência)
    - descartados é int não-negativo
    - coletado_em é datetime aware (tem tzinfo)
    """
    source = source_factory()

    # Invariante 1: instância da ABC
    assert isinstance(source, DataSource), (
        f"source_factory retornou {type(source).__name__}, "
        f"não DataSource"
    )

    # Invariante 2: fonte tipada como FonteDado
    fonte = source.fonte
    assert isinstance(fonte, FonteDado), (
        f"source.fonte é {type(fonte).__name__}, esperado FonteDado"
    )

    # Invariante 3: fonte no conjunto fechado
    assert fonte in list(FonteDado), (
        f"source.fonte={fonte} fora do conjunto FonteDado"
    )

    # Invariante 4: coletar retorna ResultadoColeta
    resultado = source.coletar()
    assert isinstance(resultado, ResultadoColeta), (
        f"coletar() retornou {type(resultado).__name__}, "
        f"esperado ResultadoColeta"
    )

    # Invariante 5: todos os alertas têm fonte consistente com a source
    for alerta in resultado.alertas:
        assert alerta.fonte == fonte, (
            f"Alerta {alerta.cod_alerta} tem fonte={alerta.fonte}, "
            f"mas source.fonte={fonte}. Inconsistência."
        )

    # Invariante 6: descartados é int não-negativo
    assert isinstance(resultado.descartados, int), (
        f"descartados é {type(resultado.descartados).__name__}, esperado int"
    )
    assert resultado.descartados >= 0, (
        f"descartados={resultado.descartados} < 0"
    )

    # Invariante 7: coletado_em é datetime aware
    assert isinstance(resultado.coletado_em, datetime), (
        f"coletado_em é {type(resultado.coletado_em).__name__}, "
        f"esperado datetime"
    )
    assert resultado.coletado_em.tzinfo is not None, (
        "coletado_em é datetime naive (sem tzinfo); "
        "esperado aware para evitar bugs de timezone"
    )
