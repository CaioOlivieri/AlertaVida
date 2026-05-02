"""Detecção pura de mudanças entre lote CEMADEN e estado persistido (Camada 3)."""

from __future__ import annotations

from dataclasses import dataclass

from alertavida.domain.alerta import Alerta

RODADAS_PARA_RESOLVER: int = 3


@dataclass(frozen=True)
class AlertaSnapshot:
    cod_alerta: int
    nivel_risco: str
    tipo_evento: str
    ult_atualizacao: str | None
    rodadas_ausente: int
    status_interno: str


@dataclass(frozen=True)
class EventoDetectado:
    tipo: str
    cod_alerta: int
    payload: dict
    schema_versao: int = 1


@dataclass
class ResultadoDeteccao:
    eventos: list[EventoDetectado]
    codigos_vistos: set[int]
    codigos_ausentes: set[int]
    codigos_resolvidos: set[int]


def _payload_de(alerta: Alerta) -> dict:
    return {
        "cod_alerta": alerta.cod_alerta,
        "tipo_evento": alerta.tipo_evento.value,
        "nivel_risco": alerta.nivel_risco.value,
        "municipio": alerta.municipio.nome,
        "uf": alerta.municipio.uf,
        "data_criacao": alerta.data_criacao.isoformat(),
        "ult_atualizacao": (
            alerta.ult_atualizacao.isoformat()
            if alerta.ult_atualizacao is not None
            else None
        ),
    }


def detectar_mudancas(
    alertas_atuais: list[Alerta],
    snapshots_banco: list[AlertaSnapshot],
    rodadas_para_resolver: int = RODADAS_PARA_RESOLVER,
) -> ResultadoDeteccao:
    snapshots_por_codigo = {s.cod_alerta: s for s in snapshots_banco}
    codigos_atuais = {a.cod_alerta for a in alertas_atuais}
    eventos: list[EventoDetectado] = []
    codigos_vistos: set[int] = set()

    for alerta in alertas_atuais:
        cod = alerta.cod_alerta
        if cod not in snapshots_por_codigo:
            eventos.append(
                EventoDetectado(
                    tipo="AlertaCriado",
                    cod_alerta=cod,
                    payload=_payload_de(alerta),
                )
            )
        else:
            snapshot = snapshots_por_codigo[cod]
            if snapshot.status_interno == "RESOLVIDO":
                pass
            else:
                ult_cur = (
                    alerta.ult_atualizacao.isoformat()
                    if alerta.ult_atualizacao is not None
                    else None
                )
                if ult_cur != snapshot.ult_atualizacao:
                    eventos.append(
                        EventoDetectado(
                            tipo="AlertaAtualizado",
                            cod_alerta=cod,
                            payload=_payload_de(alerta),
                        )
                    )
        codigos_vistos.add(cod)

    codigos_ativos_no_banco = {
        s.cod_alerta for s in snapshots_banco if s.status_interno == "ATIVO"
    }
    codigos_ausentes_work = codigos_ativos_no_banco - codigos_atuais
    codigos_resolvidos: set[int] = set()

    for cod in codigos_ausentes_work:
        snapshot = snapshots_por_codigo[cod]
        if snapshot.rodadas_ausente + 1 >= rodadas_para_resolver:
            eventos.append(
                EventoDetectado(
                    tipo="AlertaResolvido",
                    cod_alerta=cod,
                    payload={
                        "cod_alerta": cod,
                        "rodadas_ausente": snapshot.rodadas_ausente + 1,
                    },
                )
            )
            codigos_resolvidos.add(cod)

    codigos_ausentes_final = codigos_ausentes_work - codigos_resolvidos

    return ResultadoDeteccao(
        eventos=eventos,
        codigos_vistos=codigos_vistos,
        codigos_ausentes=codigos_ausentes_final,
        codigos_resolvidos=codigos_resolvidos,
    )
