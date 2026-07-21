import contextlib
import logging
import sqlite3

from alertavida.events import EventBus, OutboxDispatcher, log_handler


def test_subscribe_e_publish_chama_handler() -> None:
    bus = EventBus()
    chamadas: list[dict] = []

    def handler(evento: dict) -> None:
        chamadas.append(evento)

    evento = {"tipo": "AlertaCriado", "cod_alerta": 1}
    bus.subscribe("AlertaCriado", handler)
    bus.publish(evento)
    assert chamadas == [evento]


def test_publish_sem_handler_nao_levanta() -> None:
    bus = EventBus()
    bus.publish({"tipo": "TipoInexistente"})
    assert True


def test_handler_com_erro_nao_interrompe_outros() -> None:
    bus = EventBus()
    chamadas: list[dict] = []

    def handler_com_erro(_: dict) -> None:
        raise RuntimeError("erro")

    def handler_ok(evento: dict) -> None:
        chamadas.append(evento)

    evento = {"tipo": "AlertaCriado", "cod_alerta": 2}
    bus.subscribe("AlertaCriado", handler_com_erro)
    bus.subscribe("AlertaCriado", handler_ok)
    bus.publish(evento)
    assert chamadas == [evento]


def test_handler_count() -> None:
    bus = EventBus()

    def h1(_: dict) -> None:
        return None

    def h2(_: dict) -> None:
        return None

    def h3(_: dict) -> None:
        return None

    bus.subscribe("AlertaCriado", h1)
    bus.subscribe("AlertaCriado", h2)
    bus.subscribe("AlertaAtualizado", h3)
    assert bus.handler_count("AlertaCriado") == 2
    assert bus.handler_count("AlertaAtualizado") == 1
    assert bus.handler_count("AlertaResolvido") == 0


def test_dispatcher_processa_evento_pendente(db_temporario) -> None:
    db_path = db_temporario

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.execute(
            """
            INSERT INTO eventos (tipo, agregado_id, payload, schema_versao, criado_em, processado_em, tentativas)
            VALUES ('AlertaCriado', 1, '{"a":1}', 1, '2026-05-02T07:00:00', NULL, 0)
            """
        )
        conexao.commit()

    bus = EventBus()
    chamados: list[dict] = []

    def handler(evento: dict) -> None:
        chamados.append(evento)

    bus.subscribe("AlertaCriado", handler)
    dispatcher = OutboxDispatcher(bus)
    processados = dispatcher.processar_pendentes()

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        row = conexao.execute(
            "SELECT processado_em FROM eventos WHERE agregado_id = 1"
        ).fetchone()

    assert processados == 1
    assert len(chamados) == 1
    assert row is not None and row[0] is not None


def test_dispatcher_ignora_ja_processados(db_temporario) -> None:
    db_path = db_temporario

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.execute(
            """
            INSERT INTO eventos (tipo, agregado_id, payload, schema_versao, criado_em, processado_em, tentativas)
            VALUES ('AlertaCriado', 2, '{"a":2}', 1, '2026-05-02T07:00:00', '2026-05-02T07:01:00', 1)
            """
        )
        conexao.commit()

    bus = EventBus()
    chamados: list[dict] = []

    def handler(evento: dict) -> None:
        chamados.append(evento)

    bus.subscribe("AlertaCriado", handler)
    processados = OutboxDispatcher(bus).processar_pendentes()

    assert processados == 0
    assert chamados == []


def test_dispatcher_respeita_batch_size(db_temporario) -> None:
    db_path = db_temporario

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        for idx in range(5):
            conexao.execute(
                """
                INSERT INTO eventos (tipo, agregado_id, payload, schema_versao, criado_em, processado_em, tentativas)
                VALUES ('AlertaCriado', ?, '{"a":1}', 1, ?, NULL, 0)
                """,
                (idx + 1, f"2026-05-02T07:00:0{idx}"),
            )
        conexao.commit()

    processados = OutboxDispatcher(EventBus(), batch_size=3).processar_pendentes()

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        preenchidos = conexao.execute(
            "SELECT COUNT(*) FROM eventos WHERE processado_em IS NOT NULL"
        ).fetchone()[0]

    assert processados == 3
    assert preenchidos == 3


def test_dispatcher_payload_json_invalido_nao_quebra(db_temporario) -> None:
    db_path = db_temporario

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.execute(
            """
            INSERT INTO eventos (tipo, agregado_id, payload, schema_versao, criado_em, processado_em, tentativas)
            VALUES ('AlertaCriado', 99, '{quebrado', 1, '2026-05-02T07:00:00', NULL, 0)
            """
        )
        conexao.commit()

    bus = EventBus()
    dispatcher = OutboxDispatcher(bus)
    processados = dispatcher.processar_pendentes()

    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        row = conexao.execute(
            "SELECT processado_em, payload FROM eventos WHERE agregado_id = 99"
        ).fetchone()

    assert processados == 1
    assert row is not None and row[0] is not None
    assert row[1] == "{quebrado", "payload original preservado no banco"


def test_log_handler_loga_evento(caplog) -> None:
    caplog.set_level(logging.INFO, logger="alertavida.events")
    log_handler({"tipo": "AlertaCriado", "agregado_id": "C1", "payload": {}})
    assert "AlertaCriado" in caplog.text
    assert "C1" in caplog.text
