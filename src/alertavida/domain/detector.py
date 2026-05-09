"""Detecção pura de mudanças entre lote de alertas e estado persistido (Camada 3).

Atualizado em A.1.4: cod_alerta como string, fonte como parâmetro explícito,
payload enriquecido com coordenadas e escopo geográfico.
"""

from __future__ import annotations

from dataclasses import dataclass

from alertavida.domain.alerta import Alerta

RODADAS_PARA_RESOLVER: int = 3


@dataclass(frozen=True)
class AlertaSnapshot:
    cod_alerta: str
    nivel_risco: str
    tipo_evento: str
    ult_atualizacao: str | None
    rodadas_ausente: int
    status_interno: str


@dataclass(frozen=True)
class EventoDetectado:
    tipo: str
    cod_alerta: str
    payload: dict
    schema_versao: int = 1


@dataclass
class ResultadoDeteccao:
    eventos: list[EventoDetectado]
    codigos_vistos: set[str]
    codigos_ausentes: set[str]
    codigos_resolvidos: set[str]


def _payload_de(alerta: Alerta, fonte: str) -> dict:
    return {
        "cod_alerta": alerta.cod_alerta,
        "fonte": fonte,
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
    fonte: str,
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
                    tipo="AlertaCriado",
                    cod_alerta=cod,
                    payload=_payload_de(alerta, fonte),
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
                            payload=_payload_de(alerta, fonte),
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
                    tipo="AlertaResolvido",
                    cod_alerta=cod,
                    payload={
                        "cod_alerta": cod,
                        "fonte": fonte,
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
