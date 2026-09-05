"""Orquestrador de ingestão multi-fonte — Camada 4 Parte B.2.

Coordena a pipeline completa por fonte: coleta → detecção de mudanças →
persistência. Cada fonte é tratada em transação independente; falha de
uma não aborta as demais. Apenas FalhaDeColeta é capturada — exceções
inesperadas propagam (bug deve quebrar ruidosamente).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Sequence

from alertavida.database import (
    adicionar_membro_incidente,
    aplicar_resultado_deteccao,
    avaliar_candidatos_correlacao,
    buscar_alertas_orfaos,
    buscar_incidente_atual,
    buscar_snapshots,
    criar_incidente,
    fundir_incidentes,
    reativar_incidente,
    resolver_incidente,
    status_incidente,
    todos_membros_resolvidos,
)
from alertavida.domain.correlacao import ResultadoDecisao
from alertavida.domain.detector import TipoEventoDetectado, detectar_mudancas
from alertavida.domain.enums import FonteDado
from alertavida.sources.base import DataSource, FalhaDeColeta

if TYPE_CHECKING:
    from alertavida.domain import Alerta
    from alertavida.domain.detector import EventoDetectado


@dataclass(frozen=True, slots=True)
class RelatorioFonte:
    """Resultado da ingestão de uma única fonte numa rodada."""

    fonte: FonteDado
    coletados: int
    novos: int
    atualizados: int
    inalterados: int
    descartados: int
    falha_coleta: bool
    coletado_em: datetime | None
    duracao_segundos: float
    reativados: int = 0
    incidentes_criados: int = 0
    incidentes_juntados: int = 0
    incidentes_fundidos: int = 0
    incidentes_revisao: int = 0
    incidentes_orfaos_recuperados: int = 0

    def __post_init__(self) -> None:
        if not self.falha_coleta:
            soma = (
                self.novos + self.atualizados + self.reativados
                + self.inalterados + self.descartados
            )
            if soma != self.coletados:
                raise ValueError(
                    f"Invariante violada para fonte {self.fonte.value}: "
                    f"coletados={self.coletados} mas "
                    f"novos+atualizados+reativados+inalterados+descartados={soma}"
                )
            if self.coletado_em is None:
                raise ValueError(
                    f"coletado_em obrigatório quando falha_coleta=False "
                    f"(fonte={self.fonte.value})"
                )
        else:
            zerados = (
                self.coletados,
                self.novos,
                self.atualizados,
                self.reativados,
                self.inalterados,
                self.descartados,
                self.incidentes_criados,
                self.incidentes_juntados,
                self.incidentes_fundidos,
                self.incidentes_revisao,
                self.incidentes_orfaos_recuperados,
            )
            if any(z != 0 for z in zerados):
                raise ValueError(
                    f"falha_coleta=True exige todos os contadores zerados "
                    f"(fonte={self.fonte.value}); recebido {zerados}"
                )
            if self.coletado_em is not None:
                raise ValueError(
                    f"falha_coleta=True exige coletado_em=None "
                    f"(fonte={self.fonte.value})"
                )
        if self.duracao_segundos < 0:
            raise ValueError(
                f"duracao_segundos não pode ser negativa "
                f"(fonte={self.fonte.value}, recebido={self.duracao_segundos})"
            )


@dataclass(frozen=True, slots=True)
class RelatorioIngestao:
    """Resultado agregado de uma rodada de ingestão multi-fonte."""

    por_fonte: tuple[RelatorioFonte, ...]
    agora: datetime

    def __post_init__(self) -> None:
        if self.agora.tzinfo is None:
            raise ValueError("agora deve ser timezone-aware")

    @property
    def total(self) -> int:
        """Soma de alertas coletados em todas as fontes da rodada."""
        return sum(r.coletados for r in self.por_fonte)


def _abrir_ou_juntar_incidente(alerta_id: int, agora: str) -> tuple[str, bool]:
    """Avalia candidatos de correlação (#60) para `alerta_id` e age sobre o
    resultado (Round 1, Q6 — forward-only: entra, abre ou funde).

    VINCULA contra um único Incidente aberto: junta-se a ele. VINCULA contra
    dois Incidentes distintos ao mesmo tempo: o próprio alerta é a evidência
    de que os dois descrevem o mesmo evento físico — funde-os, sobrevivendo
    o de menor id (o mais antigo). Ausência de VINCULA abre um novo
    Incidente, mesmo havendo observações REVISAO (Round 2 — bias para
    separar: REVISAO nunca auto-vincula).

    Retorna a ação tomada ("criado"/"juntado"/"fundido") e se alguma
    observação desta chamada de blocking caiu em REVISAO, para os
    contadores de `RelatorioFonte`.
    """
    observacoes = avaliar_candidatos_correlacao(alerta_id, agora)
    teve_revisao = any(
        o.decisao.resultado is ResultadoDecisao.REVISAO for o in observacoes
    )
    vinculados = [
        o for o in observacoes if o.decisao.resultado is ResultadoDecisao.VINCULA
    ]

    if not vinculados:
        criar_incidente(alerta_id, 1.0, "fundador", agora)
        return "criado", teve_revisao

    incidentes_vinculados: list[int] = []
    for o in vinculados:
        assert o.incidente_id is not None  # VINCULA sempre tem candidato real
        incidentes_vinculados.append(o.incidente_id)
    incidentes_vinculados.sort()
    sobrevivente_id = incidentes_vinculados[0]
    melhor = max(vinculados, key=lambda o: o.decisao.score)
    adicionar_membro_incidente(
        sobrevivente_id, alerta_id, melhor.decisao.score, melhor.decisao.motivo, agora
    )
    for fundido_id in incidentes_vinculados[1:]:
        fundir_incidentes(sobrevivente_id, fundido_id, alerta_id, agora)

    if len(incidentes_vinculados) > 1:
        return "fundido", teve_revisao
    return "juntado", teve_revisao


def _acumular_contadores(
    criados: int,
    juntados: int,
    fundidos: int,
    revisao: int,
    acao: str,
    teve_revisao: bool,
) -> tuple[int, int, int, int]:
    """Soma o resultado de uma chamada a `_abrir_ou_juntar_incidente` aos
    quatro contadores de `_correlacionar_rodada` (CRIADO e o ramo
    REATIVADO-sem-membership prévia compartilham essa contagem)."""
    return (
        criados + (acao == "criado"),
        juntados + (acao == "juntado"),
        fundidos + (acao == "fundido"),
        revisao + teve_revisao,
    )


def _correlacionar_rodada(
    eventos: Sequence[EventoDetectado],
    ids_por_codigo: dict[str, int],
    agora: str,
    fonte: FonteDado,
) -> tuple[int, int, int, int, int]:
    """Aplica o ciclo de vida de Incidente (Round 1, Q6 — forward-only)
    sobre os eventos de UMA fonte já persistidos nesta rodada.

    CRIADO sempre passa por `_abrir_ou_juntar_incidente` — nunca teve
    membership antes. REATIVADO segue um dos dois caminhos: se já é membro
    de um Incidente (correlacionado antes de resolver), só reativa esse
    Incidente quando ele estava RESOLVIDO (Round 1, Q5) — não re-roda
    blocking contra novos candidatos; caso contrário (nunca correlacionado
    antes — ex. banco anterior à #61) segue o mesmo caminho do CRIADO.
    RESOLVIDO relê `status_incidente` antes de agir — mesma guarda que
    REATIVADO já usa — para que a segunda (e demais) visita ao mesmo
    Incidente já RESOLVIDO seja descartada antes de pagar o CTE recursivo de
    `todos_membros_resolvidos`; só resolve o Incidente quando ele ainda está
    ATIVO e TODOS os membros estão resolvidos, nunca quando apenas este
    membro resolve.

    ATUALIZADO não participa (decisão v1, ver PR #61): posição e onset são
    imutáveis após a criação (`latitude`/`longitude`/`datahoracriacao` só
    são escritos no INSERT do CRIADO — nunca no branch ATUALIZADO/REATIVADO
    de `aplicar_resultado_deteccao`), os dois únicos campos que o blocking
    usa para gerar candidatos; `tipo_evento`/`cobrade_codigo` SÃO
    reescritos a cada ATUALIZADO, mas na prática mudam de nível de risco
    muito mais que de categoria para um mesmo alerta já rastreado. Re-rodar
    blocking em todo ATUALIZADO reproduziria quase sempre a mesma decisão
    ao custo de O(incidentes abertos) extra por alerta já vinculado, a cada
    rodada. Uma virada real de categoria não fica se corrigir sozinha em
    v1 — gap aceito dado o viés para separar (Round 2) e REVISAO ser
    barato; dado a #63 calibrar.

    ANTES de processar os eventos desta rodada: varredura de reconciliação
    (issue #87, ver [[decisions/incident-boundary-reconciliation-sweep]]).
    É RECUPERAÇÃO, não prevenção — pega um órfão deixado por uma rodada
    ANTERIOR (processo morto entre `avaliar_candidatos_correlacao` e
    `criar_incidente`/`adicionar_membro_incidente`), nunca da rodada
    corrente. Um alerta CRIADO NESTA rodada já está persistido e `ATIVO`
    (via `aplicar_resultado_deteccao`, que roda antes desta função) mas
    ainda sem membership — exatamente a forma de um órfão — então o
    `WHERE` de `buscar_alertas_orfaos` sozinho não distingue "órfão de
    rodada passada" de "CRIADO desta rodada, ainda não processado pelo
    loop abaixo". Os ids em `ids_por_codigo` (todos desta rodada) são
    excluídos explicitamente do resultado da varredura por isso — sem essa
    exclusão, o loop abaixo tentaria correlacionar o mesmo `alerta_id` uma
    segunda vez e violaria `UNIQUE (alerta_id)` em `incidente_membros`.
    Roda por fonte, reaproveitando o loop desta função — uma query a mais
    por fonte por rodada, vazia no caso normal.
    """
    criados = juntados = fundidos = revisao = 0
    orfaos_recuperados = 0
    ids_desta_rodada = set(ids_por_codigo.values())

    for alerta_id in buscar_alertas_orfaos(fonte):
        if alerta_id in ids_desta_rodada:
            continue
        acao, teve_revisao = _abrir_ou_juntar_incidente(alerta_id, agora)
        criados, juntados, fundidos, revisao = _acumular_contadores(
            criados, juntados, fundidos, revisao, acao, teve_revisao
        )
        orfaos_recuperados += 1

    for evento in eventos:
        if evento.tipo is TipoEventoDetectado.CRIADO:
            alerta_id = ids_por_codigo[evento.cod_alerta]
            acao, teve_revisao = _abrir_ou_juntar_incidente(alerta_id, agora)
            criados, juntados, fundidos, revisao = _acumular_contadores(
                criados, juntados, fundidos, revisao, acao, teve_revisao
            )

        elif evento.tipo is TipoEventoDetectado.REATIVADO:
            alerta_id = ids_por_codigo[evento.cod_alerta]
            incidente_id = buscar_incidente_atual(alerta_id)
            if incidente_id is None:
                acao, teve_revisao = _abrir_ou_juntar_incidente(alerta_id, agora)
                criados, juntados, fundidos, revisao = _acumular_contadores(
                    criados, juntados, fundidos, revisao, acao, teve_revisao
                )
            elif status_incidente(incidente_id) == "RESOLVIDO":
                reativar_incidente(incidente_id, alerta_id, agora)

        elif evento.tipo is TipoEventoDetectado.RESOLVIDO:
            alerta_id = ids_por_codigo[evento.cod_alerta]
            incidente_id = buscar_incidente_atual(alerta_id)
            if (
                incidente_id is not None
                and status_incidente(incidente_id) == "ATIVO"
                and todos_membros_resolvidos(incidente_id)
            ):
                resolver_incidente(incidente_id, alerta_id, agora)

    return criados, juntados, fundidos, revisao, orfaos_recuperados


def executar_ingestao(
    sources: Sequence[DataSource],
    *,
    agora: datetime | None = None,
) -> RelatorioIngestao:
    """Executa uma rodada de ingestão sobre as fontes dadas.

    Cada fonte é processada em transação independente: falha de uma não
    afeta as outras. Apenas FalhaDeColeta é capturada — qualquer outra
    exceção propaga (bug deve quebrar ruidosamente).

    O timestamp `agora` é gerado uma vez no início da rodada e propagado
    para todas as fontes, garantindo coerência temporal no campo
    `visto_ultima_vez` dos snapshots.
    """
    agora_da_rodada = agora if agora is not None else datetime.now(UTC)
    relatorios: list[RelatorioFonte] = []

    for source in sources:
        inicio = time.monotonic()
        fonte = source.fonte

        try:
            resultado_coleta = source.coletar()
        except FalhaDeColeta:
            relatorios.append(
                RelatorioFonte(
                    fonte=fonte,
                    coletados=0,
                    novos=0,
                    atualizados=0,
                    inalterados=0,
                    descartados=0,
                    falha_coleta=True,
                    coletado_em=None,
                    duracao_segundos=time.monotonic() - inicio,
                )
            )
            continue

        alertas_deduplicados: list[Alerta] = []
        codigos_vistos_neste_batch: set[str] = set()
        descartados_dedup = 0
        for a in resultado_coleta.alertas:
            if a.cod_alerta in codigos_vistos_neste_batch:
                descartados_dedup += 1
            else:
                codigos_vistos_neste_batch.add(a.cod_alerta)
                alertas_deduplicados.append(a)
        descartados_total = resultado_coleta.descartados + descartados_dedup

        snapshots = buscar_snapshots(fonte)
        resultado_det = detectar_mudancas(alertas_deduplicados, snapshots)
        alertas_por_codigo = {a.cod_alerta: a for a in alertas_deduplicados}
        agora_iso = agora_da_rodada.isoformat()
        ids_por_codigo = aplicar_resultado_deteccao(
            resultado_det,
            alertas_por_codigo,
            agora_iso,
        )
        (
            incidentes_criados,
            incidentes_juntados,
            incidentes_fundidos,
            incidentes_revisao,
            incidentes_orfaos_recuperados,
        ) = _correlacionar_rodada(resultado_det.eventos, ids_por_codigo, agora_iso, fonte)

        criados_count = sum(
            1 for e in resultado_det.eventos if e.tipo is TipoEventoDetectado.CRIADO
        )
        atualizados_count = sum(
            1 for e in resultado_det.eventos if e.tipo is TipoEventoDetectado.ATUALIZADO
        )
        reativados_count = sum(
            1 for e in resultado_det.eventos if e.tipo is TipoEventoDetectado.REATIVADO
        )
        inalterados_count = (
            len(resultado_det.codigos_vistos) - criados_count - atualizados_count - reativados_count
        )

        relatorios.append(
            RelatorioFonte(
                fonte=fonte,
                coletados=len(resultado_coleta.alertas) + resultado_coleta.descartados,
                novos=criados_count,
                atualizados=atualizados_count,
                reativados=reativados_count,
                inalterados=inalterados_count,
                descartados=descartados_total,
                falha_coleta=False,
                coletado_em=resultado_coleta.coletado_em,
                duracao_segundos=time.monotonic() - inicio,
                incidentes_criados=incidentes_criados,
                incidentes_juntados=incidentes_juntados,
                incidentes_fundidos=incidentes_fundidos,
                incidentes_revisao=incidentes_revisao,
                incidentes_orfaos_recuperados=incidentes_orfaos_recuperados,
            )
        )

    return RelatorioIngestao(
        por_fonte=tuple(relatorios),
        agora=agora_da_rodada,
    )
