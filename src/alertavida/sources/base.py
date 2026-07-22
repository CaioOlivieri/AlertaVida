"""Interface DataSource e tipos relacionados — Camada 4 Parte B.1.a.

DataSource é o ponto de extensão para adicionar novas fontes de dados ao
AlertaVida. Cada implementação concreta encapsula:
- Transporte (HTTP, FTP, arquivo, etc.)
- Parsing do payload bruto
- Mapeamento para o domínio Alerta (incluindo classificação COBRADE
  e cálculo de escopo geográfico)
- Retry/backoff específico da fonte

A interface NÃO expõe o transporte usado — subclasses podem usar urllib,
httpx, ler de disco, etc. Isso permite substituição em testes via
subclasse-fake (FakeDataSource em tests/fixtures/sources_fake.py),
sem precisar mockar bibliotecas de rede.

Fontes JSON-sobre-HTTP (CemadenSource, NasaEonetSource, e futuras
INMET/INPE) não implementam DataSource diretamente: estendem
`HttpDataSource` (sources/_http.py), que consolida o template method de
coletar() sem violar a promessa desta ABC de não expor transporte — a
classe intermediária vive no módulo de transporte, não aqui
(wiki/decisions/template-method-http-datasource.md).

Design decisions registradas em wiki/decisions/datasource-adapter-falha-de-coleta.md:
- DataSource como ABC com ResultadoColeta tipado, não list[Alerta]
- FalhaDeColeta como exceção tipada do domínio
- Síncrono (não async) — Camada 6 pode usar run_in_threadpool se necessário
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from alertavida.domain.alerta import Alerta
from alertavida.domain.enums import FonteDado


@dataclass(frozen=True)
class ResultadoColeta:
    """Resultado de uma rodada de coleta de uma DataSource.

    Frozen — imutável após construção. Carrega contabilidade explícita
    (alertas válidos + contagem de descartes) para que o orquestrador
    preserve a assertion sanitária por fonte:
        coletados == novos + atualizados + inalterados + descartados + erros

    Sem `descartados`, o orquestrador teria que adivinhar quantos itens
    a source filtrou — informação que apenas a source tem.

    Atributos:
        alertas: lista de Alertas já validados pelo Pydantic, prontos
            para o pipeline detector → database. Cada Alerta carrega
            fonte=DataSource.fonte populada pela source.
        descartados: número de itens brutos que a source filtrou por
            malformação (campos obrigatórios ausentes, tipos inválidos).
            Logging interno é responsabilidade da source.
        coletado_em: timestamp aware (com tzinfo) do momento em que a
            coleta foi concluída. Usado pelo orquestrador em logs e
            relatórios.
    """

    alertas: list[Alerta]
    descartados: int
    coletado_em: datetime


class FalhaDeColeta(Exception):
    """Falha irrecuperável durante coleta de uma DataSource.

    A source levanta isso após esgotar retries internos (rede caída,
    schema rejeitado pela response, JSON corrompido). O orquestrador
    (Parte B.2) captura `FalhaDeColeta`, registra a falha contra a
    fonte específica via RelatorioFonte(falha_coleta=True), e continua
    com as próximas fontes na mesma rodada.

    Falhas INDIVIDUAIS de alerta dentro de uma rodada NÃO sobem como
    FalhaDeColeta — são contadas em ResultadoColeta.descartados.
    FalhaDeColeta é reservado para falhas de RODADA INTEIRA.

    Atributos:
        fonte: qual DataSource originou a falha. Permite ao orquestrador
            identificar a fonte sem rastrear contexto externo.
        causa: descrição curta legível (ex: "rede esgotada após 4 tentativas",
            "schema rejeitado: JSON inválido").
        original: exceção original que causou a falha (URLError, HTTPError,
            JSONDecodeError, etc.). Preservada via exception chain para
            debug — sem isso, perde-se o stack trace original.

    Uso típico em uma implementação:
        try:
            raw = self._fetch_com_retry()
        except (URLError, socket.timeout) as exc:
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa="rede esgotada após retries",
                original=exc,
            ) from exc
    """

    def __init__(
        self,
        fonte: FonteDado,
        causa: str,
        original: Exception | None = None,
    ) -> None:
        self.fonte = fonte
        self.causa = causa
        self.original = original
        super().__init__(f"Falha de coleta em {fonte.value}: {causa}")


class DataSource(ABC):
    """Interface comum para fontes de dados de alertas.

    Cada implementação concreta encapsula tudo que é específico de uma
    fonte: transporte, parsing, mapeamento de tipos para COBRADE,
    classificação geográfica, retry/backoff.

    Contrato:
    - `fonte` é estável durante o ciclo de vida da instância. Não muda.
    - `coletar()` é síncrono. Faz I/O de rede de LEITURA apenas.
    - `coletar()` NÃO escreve em banco, NÃO imprime (usa logging), NÃO
      modifica filesystem. Pureza de side effects exceto rede.
    - Falhas individuais de alerta são contadas em
      ResultadoColeta.descartados; não sobem como exceção.
    - Falha de rodada inteira sobe como FalhaDeColeta; orquestrador
      captura e continua.
    - Qualquer outra exceção é bug e propaga (regra de
      wiki/patterns/resilience-invariants.md: nunca bare except).
    """

    @property
    @abstractmethod
    def fonte(self) -> FonteDado:
        """Identificador estável da fonte. Vai para Alerta.fonte e
        para a coluna `fonte` no banco. Property abstrata força
        declaração explícita pela subclasse.
        """

    @abstractmethod
    def coletar(self) -> ResultadoColeta:
        """Executa uma rodada completa de coleta.

        Retorna ResultadoColeta com Alertas já validados e enriquecidos
        (cobrade_codigo, escopo_geografico, fonte_classificacao populados
        pela source). Levanta FalhaDeColeta em falha de rodada.
        """
