"""Backup de teste com o schema real (issue #158) — base comum da exportação e do site."""

import contextlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alertavida import database as db_module
from alertavida.domain.aviso import AvisoMeteorologico, SeveridadeAviso

RJ, SP = 3304557, 3550308
NOME_BACKUP = "alertavida-20261124T000500Z.db"


def utc(texto: str) -> datetime:
    return datetime.fromisoformat(texto).astimezone(UTC)


def _inserir_alerta(conexao, id_, cod, codibge, municipio, inicio, status="ATIVO"):
    conexao.execute(
        """
        INSERT INTO alertas (
            id, fonte, cod_alerta, municipio, uf, evento, nivel, datahoracriacao,
            detectado_em, codibge, latitude, longitude, escopo_geografico,
            ult_atualizacao, status_interno, visto_ultima_vez, cobrade_codigo,
            fonte_classificacao
        ) VALUES (?, 'CEMADEN', ?, ?, 'RJ', 'HIDROLOGICO', 'MODERADO', ?, ?, ?,
                  -22.9, -43.4, 'BRASIL', ?, ?, ?, '1.2.0.0.0', 'MAPEADA_POR_NOME')
        """,
        (id_, cod, municipio, inicio, inicio, codibge, inicio, status, inicio),
    )


def criar_backup(diretorio: Path, monkeypatch, municipio_a1: str = "RIO DE JANEIRO") -> Path:
    """Dois alertas (A1 ativo sob um aviso, A2 resolvido antes dele), um aviso
    do INMET e duas rodadas, salvos com o nome que deploy/backup.py usa."""
    caminho = diretorio / NOME_BACKUP
    diretorio.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(caminho))
    db_module.criar_banco()
    db_module.registrar_avisos(
        [
            AvisoMeteorologico(
                codigo_cap="urn:oid:2.49.0.0.76.0.2026.1.1",
                id_aviso=1,
                id_sequencia=1,
                evento="Tempestade",
                severidade=SeveridadeAviso.PERIGO,
                inicio=utc("2026-11-23T12:00:00+00:00"),
                fim=utc("2026-11-24T02:59:00+00:00"),
                codigos_ibge=frozenset({RJ, SP}),
                encerrado=False,
            )
        ],
        "2026-11-23T13:46:19.807354+00:00",
    )
    with contextlib.closing(sqlite3.connect(caminho)) as conexao:
        _inserir_alerta(conexao, 1, "A1", RJ, municipio_a1, "2026-11-23T15:00:00.730000+00:00")
        _inserir_alerta(
            conexao, 2, "A2", SP, "SÃO PAULO", "2026-11-22T10:00:00+00:00", "RESOLVIDO"
        )
        conexao.execute(
            "INSERT INTO eventos (tipo, agregado_id, payload, criado_em) "
            "VALUES ('AlertaResolvido', 2, '{}', '2026-11-22T11:00:00+00:00')"
        )
        conexao.commit()
    db_module.registrar_rodada(
        "2026-11-23T23:56:17.000001+00:00",
        "2026-11-23T23:56:18+00:00",
        [("CEMADEN", 30), ("EONET", None)],
    )
    db_module.registrar_rodada(
        "2026-11-24T00:01:17+00:00", "2026-11-24T00:01:18+00:00", [("CEMADEN", None)]
    )
    return caminho
