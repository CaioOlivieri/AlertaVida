"""Detecção pura de mudanças entre lote de alertas e estado persistido (Camada 3).

Atualizado em A.1.4: cod_alerta como string, fonte como parâmetro explícito,
payload enriquecido com coordenadas e escopo geográfico.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from alertavida.domain.alerta import Alerta
from alertavida.domain.enums import FonteDado

RODADAS_PARA_RESOLVER: int = 3


class TipoEventoDetectado(StrEnum):
    """Universo fechado de tipos de evento produzidos pelo ChangeDetector."""

    CRIADO = "AlertaCriado"
    ATUALIZADO = "AlertaAtualizado"
    RESOLVIDO = "AlertaResolvido"
    REATIVADO = "AlertaReativado"


@dataclass(frozen=True)
class AlertaSnapshot:
    cod_alerta: str
    fonte: FonteDado
    nivel_risco: str
    tipo_evento: str
    ult_atualizacao: str | None
    rodadas_ausente: int
    status_interno: str


@dataclass(frozen=True)
class EventoDetectado:
    tipo: TipoEventoDetectado
    cod_alerta: str
    fonte: FonteDado
    payload: dict
    schema_versao: int = 1


@dataclass
class ResultadoDeteccao:
    """Resultado de uma rodada de detecção de mudanças.

    Carrega TODOS os dados que `aplicar_resultado_deteccao` precisa para
    persistir a rodada — autocontido, sem necessidade de a infra consultar
    snapshots ou alertas separadamente para descobrir contexto.

    Princípio Tell, Don't Ask: o detector "diz" tudo que aconteceu (eventos,
    códigos vistos, códigos ausentes, e o mapa de fonte por código);
    a infra "executa" sem precisar adivinhar.
    """

    eventos: list[EventoDetectado]
    codigos_vistos: set[str]
    codigos_ausentes: set[str]
    codigos_resolvidos: set[str]
    fonte_por_codigo: dict[str, FonteDado]


def _payload_de(alerta: Alerta) -> dict:
    return {
        "cod_alerta": alerta.cod_alerta,
        "fonte": alerta.fonte.value,
        "tipo_evento": alerta.tipo_evento.value,
        "nivel_risco": alerta.nivel_risco.value,
        "municipio": alerta.municipio.nome if alerta.municipio else None,
        "uf": alerta.municipio.uf if alerta.municipio else None,
        "data_criacao": alerta.data_criacao.isoformat(),
        "ult_atualizacao": (
            alerta.ult_atualizacao.isoformat()
            if alerta.ult_atualizacao is not None
            else None
        ),
        "coordenadas": {
            "latitude": alerta.coordenadas.latitude,
            "longitude": alerta.coordenadas.longitude,
        },
        "escopo_geografico": alerta.escopo_geografico.value,
    }


def detectar_mudancas(
    alertas_atuais: list[Alerta],
    snapshots_banco: list[AlertaSnapshot],
    rodadas_para_resolver: int = RODADAS_PARA_RESOLVER,
) -> ResultadoDeteccao:
    snapshots_por_codigo = {s.cod_alerta: s for s in snapshots_banco}
    codigos_atuais = {a.cod_alerta for a in alertas_atuais}
    eventos: list[EventoDetectado] = []
    codigos_vistos: set[str] = set()

    for alerta in alertas_atuais:
        cod = alerta.cod_alerta
        if cod not in snapshots_por_codigo:
            eventos.append(
                EventoDetectado(
                    tipo=TipoEventoDetectado.CRIADO,
                    cod_alerta=cod,
                    fonte=alerta.fonte,
                    payload=_payload_de(alerta),
                )
            )
        else:
            snapshot = snapshots_por_codigo[cod]
            if snapshot.status_interno == "RESOLVIDO":
                eventos.append(
                    EventoDetectado(
                        tipo=TipoEventoDetectado.REATIVADO,
                        cod_alerta=cod,
                        fonte=alerta.fonte,
                        payload=_payload_de(alerta),
                    )
                )
            else:
                ult_cur = (
                    alerta.ult_atualizacao.isoformat()
                    if alerta.ult_atualizacao is not None
                    else None
                )
                if ult_cur != snapshot.ult_atualizacao:
                    eventos.append(
                        EventoDetectado(
                            tipo=TipoEventoDetectado.ATUALIZADO,
                            cod_alerta=cod,
                            fonte=alerta.fonte,
                            payload=_payload_de(alerta),
                        )
                    )
        codigos_vistos.add(cod)

    codigos_ativos_no_banco = {
        s.cod_alerta for s in snapshots_banco if s.status_interno == "ATIVO"
    }
    codigos_ausentes_work = codigos_ativos_no_banco - codigos_atuais
    codigos_resolvidos: set[str] = set()

    for cod in codigos_ausentes_work:
        snapshot = snapshots_por_codigo[cod]
        if snapshot.rodadas_ausente + 1 >= rodadas_para_resolver:
            eventos.append(
                EventoDetectado(
                    tipo=TipoEventoDetectado.RESOLVIDO,
                    cod_alerta=cod,
                    fonte=snapshot.fonte,
                    payload={
                        "cod_alerta": cod,
                        "fonte": snapshot.fonte.value,
                        "rodadas_ausente": snapshot.rodadas_ausente + 1,
                    },
                )
            )
            codigos_resolvidos.add(cod)

    codigos_ausentes_final = codigos_ausentes_work - codigos_resolvidos

    fonte_por_codigo: dict[str, FonteDado] = {}
    for alerta in alertas_atuais:
        fonte_por_codigo[alerta.cod_alerta] = alerta.fonte
    for snapshot in snapshots_banco:
        # Snapshots de códigos não vistos no feed atual também precisam
        # ter sua fonte conhecida (AlertaResolvido ou ausência simples).
        # Códigos presentes em ambos: alerta vence (mesma fonte, dict ok).
        if snapshot.cod_alerta not in fonte_por_codigo:
            fonte_por_codigo[snapshot.cod_alerta] = snapshot.fonte

    return ResultadoDeteccao(
        eventos=eventos,
        codigos_vistos=codigos_vistos,
        codigos_ausentes=codigos_ausentes_final,
        codigos_resolvidos=codigos_resolvidos,
        fonte_por_codigo=fonte_por_codigo,
    )
