from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Callable

from alertavida.database import DB_PATH

logger = logging.getLogger(__name__)

Handler = Callable[[dict], None]


class EventBus:
    """Registro in-memory de handlers por tipo de evento.

    Uso:
        bus = EventBus()
        bus.subscribe("AlertaCriado", meu_handler)
        bus.publish({"tipo": "AlertaCriado", "cod_alerta": 42, ...})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, tipo: str, handler: Handler) -> None:
        self._handlers[tipo].append(handler)

    def publish(self, evento: dict) -> None:
        """Chama todos os handlers registrados para o tipo do evento.

        Erros em handlers individuais são logados mas não interrompem
        a entrega aos demais handlers.
        """
        tipo = evento.get("tipo", "")
        for handler in self._handlers.get(tipo, []):
            try:
                handler(evento)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Handler %s falhou para evento %s: %s",
                    handler.__name__,
                    tipo,
                    exc,
                )

    def handler_count(self, tipo: str) -> int:
        """Utilitário de teste — retorna quantos handlers estão registrados."""
        return len(self._handlers.get(tipo, []))


class OutboxDispatcher:
    """Lê eventos não processados da outbox e entrega ao EventBus.

    Projetado para rodar como job periódico no APScheduler.
    Single-publisher: sem concorrência, sem locking necessário.
    """

    def __init__(self, bus: EventBus, batch_size: int = 100) -> None:
        self._bus = bus
        self._batch_size = batch_size

    def processar_pendentes(self) -> int:
        """Processa até batch_size eventos pendentes.

        Retorna o número de eventos processados nesta chamada.
        Marca processado_em mesmo que handlers falhem — o log registra
        a falha, mas o evento não é reentregue (evita loop infinito
        em caso de handler com bug permanente).
        """
        agora = datetime.now().isoformat(timespec="seconds")
        processados = 0

        with sqlite3.connect(DB_PATH) as conexao:
            cursor = conexao.execute(
                """
                SELECT id, tipo, agregado_id, payload, schema_versao
                FROM eventos
                WHERE processado_em IS NULL
                ORDER BY criado_em ASC
                LIMIT ?
                """,
                (self._batch_size,),
            )
            rows = cursor.fetchall()

            for row in rows:
                id_, tipo, agregado_id, payload_json, schema_versao = row
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    payload = {}

                evento = {
                    "id": id_,
                    "tipo": tipo,
                    "agregado_id": agregado_id,
                    "payload": payload,
                    "schema_versao": schema_versao,
                }
                self._bus.publish(evento)

                conexao.execute(
                    "UPDATE eventos SET processado_em = ?, tentativas = tentativas + 1 WHERE id = ?",
                    (agora, id_),
                )
                processados += 1

            conexao.commit()

        return processados


def log_handler(evento: dict) -> None:
    logger.info(
        "[%s] cod_alerta=%s payload=%s",
        evento.get("tipo"),
        evento.get("agregado_id"),
        evento.get("payload"),
    )


bus = EventBus()
bus.subscribe("AlertaCriado", log_handler)
bus.subscribe("AlertaAtualizado", log_handler)
bus.subscribe("AlertaResolvido", log_handler)
bus.subscribe("AlertaReativado", log_handler)
