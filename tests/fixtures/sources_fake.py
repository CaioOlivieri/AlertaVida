"""FakeDataSource — implementação determinística para testes do orquestrador.

Não faz I/O. Não chama urllib. Retorna alertas pré-configurados ou
levanta FalhaDeColeta sob comando do teste.

Por que Fake e não Mock:
- unittest.mock.Mock é genérico — qualquer atributo acessado retorna
  outro Mock, escondendo erros de assinatura (ex: source.coletor() em
  vez de source.coletar() passaria silenciosamente).
- FakeDataSource implementa a interface real (DataSource). Se DataSource
  mudar (método novo, assinatura nova), o fake quebra imediatamente
  dando feedback claro.
- Princípio: testes verdadeiros usam dublês fiéis ao contrato real.

Uso típico (em tests/ingestao/test_orquestrador.py, B.2):

    from tests.fixtures.sources_fake import FakeDataSource

    def test_orquestrador_isola_falha_por_fonte():
        ok = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=[alerta1, alerta2])
        falha = FakeDataSource(fonte=FonteDado.EONET, falhar=True)
        relatorio = executar_ingestao([ok, falha])
        assert relatorio.por_fonte[0].falha_coleta is False
        assert relatorio.por_fonte[1].falha_coleta is True
"""

from datetime import datetime, timezone

from alertavida.domain.alerta import Alerta
from alertavida.domain.enums import FonteDado
from alertavida.sources import DataSource, FalhaDeColeta, ResultadoColeta


class FakeDataSource(DataSource):
    """DataSource determinística para testes. Não faz I/O.

    Parâmetros do construtor:
        fonte: identificador da fonte (FonteDado).
        alertas: lista de Alertas a retornar em coletar(). Default vazio.
        descartados: contador de descartes a reportar. Default 0.
        falhar: se True, coletar() levanta FalhaDeColeta. Default False.
        causa_falha: mensagem usada se falhar=True. Default genérica.
        coletado_em: timestamp fixo para reprodutibilidade em testes.
            Default datetime.now(timezone.utc) na construção (mas pode
            ser passado explícito para determinismo total).
    """

    def __init__(
        self,
        fonte: FonteDado,
        alertas: list[Alerta] | None = None,
        descartados: int = 0,
        falhar: bool = False,
        causa_falha: str = "falha forçada em teste",
        coletado_em: datetime | None = None,
    ) -> None:
        self._fonte = fonte
        self._alertas = alertas if alertas is not None else []
        self._descartados = descartados
        self._falhar = falhar
        self._causa_falha = causa_falha
        self._coletado_em = (
            coletado_em
            if coletado_em is not None
            else datetime.now(timezone.utc)
        )

    @property
    def fonte(self) -> FonteDado:
        return self._fonte

    def coletar(self) -> ResultadoColeta:
        if self._falhar:
            raise FalhaDeColeta(
                fonte=self._fonte,
                causa=self._causa_falha,
            )
        return ResultadoColeta(
            alertas=list(self._alertas),
            descartados=self._descartados,
            coletado_em=self._coletado_em,
        )
