"""Testes do ChangeDetector (detecção pura de mudanças).

Atualizado em A.1.4: cod_alerta como string, payload com fonte/coordenadas/escopo.
Atualizado em B.0.a: fonte como atributo de Alerta e AlertaSnapshot (não mais parâmetro).
Atualizado em B.0.b: ResultadoDeteccao.fonte_por_codigo populado pelo detector.
"""

from datetime import datetime, timezone

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.detector import (
    RODADAS_PARA_RESOLVER,
    AlertaSnapshot,
    TipoEventoDetectado,
    detectar_mudancas,
)
from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento


def _payload_base_cemaden(cod: int | str) -> dict:
    return {
        "codigoalerta": cod,
        "municipio": "Recife",
        "estado": "PE",
        "tipoevento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }


def test_alerta_novo_gera_evento_criado() -> None:
    payload = {
        **_payload_base_cemaden(9001),
        "ult_atualizacao": "2026-04-29T11:00:00+00:00",
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    res = detectar_mudancas([alerta], [])
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo is TipoEventoDetectado.CRIADO
    assert res.eventos[0].cod_alerta == "9001"
    assert res.eventos[0].payload["fonte"] == "CEMADEN"
    assert res.eventos[0].payload["coordenadas"]["latitude"] == -8.05


def test_alerta_inalterado_nao_gera_evento() -> None:
    ult = "2026-04-29T11:00:00+00:00"
    payload = {**_payload_base_cemaden(9002), "ult_atualizacao": ult}
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    snap = AlertaSnapshot(
        cod_alerta="9002",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=ult,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([alerta], [snap])
    assert res.eventos == []


def test_alerta_atualizado_gera_evento_atualizado() -> None:
    payload = {
        **_payload_base_cemaden(9003),
        "ult_atualizacao": "2026-05-01T14:00:00+00:00",
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    snap = AlertaSnapshot(
        cod_alerta="9003",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao="2026-04-29T09:00:00+00:00",
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([alerta], [snap])
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo is TipoEventoDetectado.ATUALIZADO
    assert res.eventos[0].cod_alerta == "9003"


def test_alerta_ausente_incrementa_ausente() -> None:
    cod = "9004"
    snap = AlertaSnapshot(
        cod_alerta=cod,
        fonte=FonteDado.CEMADEN,
        ult_atualizacao="2026-04-29T09:00:00+00:00",
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([], [snap])
    assert res.codigos_ausentes == {cod}
    assert res.codigos_resolvidos == set()


def test_alerta_ausente_resolve_apos_limite() -> None:
    cod = "9005"
    snap = AlertaSnapshot(
        cod_alerta=cod,
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=None,
        rodadas_ausente=2,
        status_interno="ATIVO",
    )
    res = detectar_mudancas([], [snap], rodadas_para_resolver=3)
    assert res.codigos_resolvidos == {cod}
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo is TipoEventoDetectado.RESOLVIDO
    assert res.eventos[0].payload["fonte"] == "CEMADEN"
    assert res.codigos_ausentes == set()


def test_alerta_resolvido_que_reaparece_emite_reativado() -> None:
    payload = {
        **_payload_base_cemaden(9006),
        "ult_atualizacao": "2026-05-02T08:00:00+00:00",
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    snap = AlertaSnapshot(
        cod_alerta="9006",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=None,
        rodadas_ausente=0,
        status_interno="RESOLVIDO",
    )
    res = detectar_mudancas([alerta], [snap])
    assert len(res.eventos) == 1
    assert res.eventos[0].tipo is TipoEventoDetectado.REATIVADO
    assert res.eventos[0].cod_alerta == "9006"
    assert res.eventos[0].payload["fonte"] == "CEMADEN"


def test_multiplos_alertas_mix() -> None:
    ult_existente = "2026-04-29T12:00:00+00:00"
    novo_payload = {
        **_payload_base_cemaden(9100),
        "ult_atualizacao": "2026-05-03T09:00:00+00:00",
    }
    existe_payload = {
        **_payload_base_cemaden(9200),
        "ult_atualizacao": ult_existente,
    }
    alerta_novo = Alerta.from_dict(novo_payload, fonte=FonteDado.CEMADEN)
    alerta_igual = Alerta.from_dict(existe_payload, fonte=FonteDado.CEMADEN)

    snap_igual = AlertaSnapshot(
        cod_alerta="9200",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=ult_existente,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )
    snap_ausente = AlertaSnapshot(
        cod_alerta="9300",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=None,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )

    res = detectar_mudancas(
        [alerta_novo, alerta_igual],
        [snap_igual, snap_ausente],
        rodadas_para_resolver=RODADAS_PARA_RESOLVER,
    )

    tipos = [e.tipo for e in res.eventos]
    assert tipos.count(TipoEventoDetectado.CRIADO) == 1
    assert tipos.count(TipoEventoDetectado.ATUALIZADO) == 0
    assert res.codigos_ausentes == {"9300"}
    assert res.codigos_resolvidos == set()


# ============================================================
# Camada 4 B.0.a — fonte propagada via objetos
# ============================================================


def test_detectar_propaga_fonte_em_alerta_criado():
    """EventoDetectado.fonte para AlertaCriado vem do Alerta atual."""
    alerta = Alerta(
        cod_alerta="X1",
        fonte=FonteDado.CEMADEN,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
        data_criacao=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )

    resultado = detectar_mudancas(
        alertas_atuais=[alerta],
        snapshots_banco=[],
    )

    assert len(resultado.eventos) == 1
    evento = resultado.eventos[0]
    assert evento.tipo is TipoEventoDetectado.CRIADO
    assert evento.fonte == FonteDado.CEMADEN
    assert evento.payload["fonte"] == "CEMADEN"


def test_detectar_propaga_fonte_em_alerta_resolvido():
    """EventoDetectado.fonte para AlertaResolvido vem do AlertaSnapshot.

    Caso crítico: alerta desapareceu do feed atual; fonte só pode vir
    do snapshot persistido.
    """
    snapshot = AlertaSnapshot(
        cod_alerta="Y1",
        fonte=FonteDado.EONET,
        ult_atualizacao=None,
        rodadas_ausente=2,
        status_interno="ATIVO",
    )

    resultado = detectar_mudancas(
        alertas_atuais=[],
        snapshots_banco=[snapshot],
    )

    resolvidos = [e for e in resultado.eventos if e.tipo is TipoEventoDetectado.RESOLVIDO]
    assert len(resolvidos) == 1
    assert resolvidos[0].fonte == FonteDado.EONET
    assert resolvidos[0].payload["fonte"] == "EONET"


# ============================================================
# Camada 4 B.0.b — ResultadoDeteccao.fonte_por_codigo
# ============================================================


def test_resultado_inclui_fonte_por_codigo_de_alertas_atuais():
    """fonte_por_codigo é populado para todo Alerta em alertas_atuais."""
    a1 = Alerta(
        cod_alerta="X1",
        fonte=FonteDado.CEMADEN,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
        data_criacao=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )
    a2 = Alerta(
        cod_alerta="X2",
        fonte=FonteDado.EONET,
        tipo_evento=TipoEvento.METEOROLOGICO,
        nivel_risco=NivelRisco.MODERADO,
        coordenadas=Coordenadas(latitude=-5.0, longitude=-35.0),
        data_criacao=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )

    resultado = detectar_mudancas(alertas_atuais=[a1, a2], snapshots_banco=[])

    assert resultado.fonte_por_codigo == {
        "X1": FonteDado.CEMADEN,
        "X2": FonteDado.EONET,
    }


def test_resultado_inclui_fonte_por_codigo_de_snapshots_ausentes():
    """Snapshots cujo código não aparece em alertas_atuais ainda têm
    sua fonte registrada em fonte_por_codigo. Essencial para que
    aplicar_resultado_deteccao consiga fazer UPDATE em alertas ausentes.
    """
    snapshot = AlertaSnapshot(
        cod_alerta="Z1",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=None,
        rodadas_ausente=1,
        status_interno="ATIVO",
    )

    resultado = detectar_mudancas(
        alertas_atuais=[],
        snapshots_banco=[snapshot],
    )

    assert resultado.fonte_por_codigo == {"Z1": FonteDado.CEMADEN}


def test_resultado_fonte_por_codigo_alerta_vence_snapshot():
    """Quando código está em alertas_atuais E em snapshots_banco,
    a fonte vem do Alerta atual. Em B.0 ambas devem ser iguais (single
    fonte por rodada), mas o teste documenta a precedência.
    """
    alerta = Alerta(
        cod_alerta="W1",
        fonte=FonteDado.CEMADEN,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
        data_criacao=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )
    snapshot = AlertaSnapshot(
        cod_alerta="W1",
        fonte=FonteDado.CEMADEN,
        ult_atualizacao=None,
        rodadas_ausente=0,
        status_interno="ATIVO",
    )

    resultado = detectar_mudancas(
        alertas_atuais=[alerta],
        snapshots_banco=[snapshot],
    )

    assert resultado.fonte_por_codigo["W1"] == FonteDado.CEMADEN
