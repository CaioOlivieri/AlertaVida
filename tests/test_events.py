import contextlib
import logging
import sqlite3

from alertavida.database import TIPOS_EVENTO_INCIDENTE
from alertavida.domain.detector import TipoEventoDetectado
from alertavida.events import (
    EventBus,
    OutboxDispatcher,
    criar_bus_producao,
    log_handler,
)


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
            INSERT INTO eventos (
                tipo, agregado_id, payload, schema_versao,
                criado_em, processado_em, tentativas
            )
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
            INSERT INTO eventos (
                tipo, agregado_id, payload, schema_versao,
                criado_em, processado_em, tentativas
            )
            VALUES (
                'AlertaCriado', 2, '{"a":2}', 1,
                '2026-05-02T07:00:00', '2026-05-02T07:01:00', 1
            )
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
                INSERT INTO eventos (
                    tipo, agregado_id, payload, schema_versao,
                    criado_em, processado_em, tentativas
                )
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
            INSERT INTO eventos (
                tipo, agregado_id, payload, schema_versao,
                criado_em, processado_em, tentativas
            )
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


def test_criar_bus_producao_inscreve_alertas_e_incidentes() -> None:
    bus = criar_bus_producao()

    assert bus.handler_count("AlertaCriado") == 1
    assert bus.handler_count("AlertaAtualizado") == 1
    assert bus.handler_count("AlertaResolvido") == 1
    assert bus.handler_count("AlertaReativado") == 1
    for tipo in TIPOS_EVENTO_INCIDENTE:
        assert bus.handler_count(tipo) == 1


def test_todo_tipo_de_evento_que_a_outbox_grava_tem_handler() -> None:
    """#131: a lista de inscrições sai das fontes de verdade. Um tipo novo em
    TipoEventoDetectado ou TIPOS_EVENTO_INCIDENTE não pode ficar sem handler."""
    bus = criar_bus_producao()
    tipos = [t.value for t in TipoEventoDetectado] + sorted(TIPOS_EVENTO_INCIDENTE)

    assert len(tipos) == 9
    assert all(bus.handler_count(tipo) == 1 for tipo in tipos)


def test_criar_bus_producao_devolve_instancias_independentes() -> None:
    """Sem singleton: um bus não enxerga os handlers registrados no outro."""
    primeiro = criar_bus_producao()
    segundo = criar_bus_producao()

    def handler_extra(_: dict) -> None:
        return None

    primeiro.subscribe("AlertaCriado", handler_extra)

    assert primeiro is not segundo
    assert primeiro.handler_count("AlertaCriado") == 2
    assert segundo.handler_count("AlertaCriado") == 1


def _inserir_pendentes(db_path, n: int) -> None:
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.executemany(
            "INSERT INTO eventos (tipo, agregado_id, payload, schema_versao, criado_em, "
            "processado_em, tentativas) VALUES ('AlertaCriado', ?, '{}', 1, ?, NULL, 0)",
            [(i, f"2026-11-23T00:00:0{i}") for i in range(1, n + 1)],
        )
        conexao.commit()


def test_handlers_rodam_sem_transacao_de_escrita_aberta(db_temporario) -> None:
    """#132: enquanto um handler roda, ninguém pode estar segurando o lock de
    escrita — senão um handler lento trava a rodada de ingestão. O handler
    tenta escrever por outra conexão SEM esperar (timeout=0); no código
    antigo isso falhava a partir do 2º evento, porque o UPDATE do 1º já
    tinha aberto a transação."""
    _inserir_pendentes(db_temporario, 3)
    escritas_ok: list[bool] = []

    def handler_que_escreve(_: dict) -> None:
        with contextlib.closing(sqlite3.connect(db_temporario, timeout=0)) as outra:
            try:
                outra.execute("BEGIN IMMEDIATE")
                outra.execute("ROLLBACK")
                escritas_ok.append(True)
            except sqlite3.OperationalError:
                escritas_ok.append(False)

    bus = EventBus()
    bus.subscribe("AlertaCriado", handler_que_escreve)

    assert OutboxDispatcher(bus).processar_pendentes() == 3
    assert escritas_ok == [True, True, True]


def test_lote_inteiro_marcado_de_uma_vez(db_temporario) -> None:
    _inserir_pendentes(db_temporario, 3)
    bus = EventBus()

    assert OutboxDispatcher(bus).processar_pendentes() == 3
    assert OutboxDispatcher(bus).processar_pendentes() == 0  # nada reentregue

    with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
        linhas = conexao.execute(
            "SELECT COUNT(DISTINCT processado_em), MIN(tentativas), MAX(tentativas), "
            "SUM(processado_em IS NULL) FROM eventos"
        ).fetchone()
    assert linhas == (1, 1, 1, 0)


def test_sem_pendentes_nao_abre_transacao_de_escrita(db_temporario, monkeypatch) -> None:
    chamadas = []
    import alertavida.events as events_module

    original = events_module.conectar

    def conectar_contado():
        chamadas.append(1)
        return original()

    monkeypatch.setattr(events_module, "conectar", conectar_contado)
    assert OutboxDispatcher(EventBus()).processar_pendentes() == 0
    assert len(chamadas) == 1  # só a leitura
