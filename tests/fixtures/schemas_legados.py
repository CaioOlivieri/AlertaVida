"""Schemas históricos da tabela `alertas` para testes de regressão.

Reconstruídos a partir do git log de src/alertavida/database.py (inspeção
em 12/05/2026). Cada função aplica via SQL bruto o schema EXATO que existia
em um commit específico, simulando o estado de um banco que rodou aquela
versão do código.

Uso pretendido: testes de tests/test_database.py que verificam o
comportamento de criar_banco() / _verificar_compatibilidade_schema()
contra bancos pré-existentes.
"""

import sqlite3


def aplicar_schema_pre_camada_3(conexao: sqlite3.Connection) -> None:
    """Schema da tabela `alertas` no commit 6604e18 (01/05/2026).

    Estado: Camada 2 fechada. Sem colunas de ciclo de vida (status_interno,
    visto_ultima_vez, rodadas_ausente, assinatura), sem coordenadas
    (codibge, latitude, longitude), sem ult_atualizacao.
    """
    conexao.execute(
        """
        CREATE TABLE alertas (
            cod_alerta INTEGER PRIMARY KEY,
            municipio TEXT,
            uf TEXT,
            evento TEXT,
            nivel TEXT,
            datahoracriacao TEXT,
            detectado_em TEXT NOT NULL
        )
        """
    )
    conexao.execute("CREATE INDEX idx_uf ON alertas (uf)")
    conexao.execute("CREATE INDEX idx_evento ON alertas (evento)")
    conexao.execute("CREATE INDEX idx_nivel ON alertas (nivel)")
    conexao.commit()


def aplicar_schema_pos_camada_3(conexao: sqlite3.Connection) -> None:
    """Schema da tabela `alertas` no commit 70df503 (02/05/2026).

    Estado: Camada 3 fechada (outbox + ChangeDetector integrados). Tem
    colunas de ciclo de vida e coordenadas, mas PK ainda é cod_alerta
    INTEGER, sem coluna `id` surrogate, sem `fonte`, sem `escopo_geografico`.
    """
    conexao.execute(
        """
        CREATE TABLE alertas (
            cod_alerta          INTEGER PRIMARY KEY,
            municipio           TEXT,
            uf                  TEXT,
            evento              TEXT,
            nivel               TEXT,
            datahoracriacao     TEXT,
            detectado_em        TEXT NOT NULL,
            codibge             INTEGER,
            latitude            REAL,
            longitude           REAL,
            ult_atualizacao     TEXT,
            status_interno      TEXT NOT NULL DEFAULT 'ATIVO',
            visto_ultima_vez    TEXT NOT NULL DEFAULT '',
            rodadas_ausente     INTEGER NOT NULL DEFAULT 0,
            assinatura          TEXT
        )
        """
    )
    conexao.execute("CREATE INDEX idx_uf ON alertas (uf)")
    conexao.execute("CREATE INDEX idx_evento ON alertas (evento)")
    conexao.execute("CREATE INDEX idx_nivel ON alertas (nivel)")
    conexao.execute(
        """
        CREATE TABLE eventos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo            TEXT NOT NULL,
            agregado_id     INTEGER NOT NULL,
            payload         TEXT NOT NULL,
            schema_versao   INTEGER NOT NULL DEFAULT 1,
            criado_em       TEXT NOT NULL,
            processado_em   TEXT NULL,
            tentativas      INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conexao.execute(
        "CREATE INDEX idx_eventos_pendentes ON eventos (processado_em, criado_em)"
    )
    conexao.commit()


def aplicar_schema_pos_a1_pre_a2(conexao: sqlite3.Connection) -> None:
    """Schema da tabela `alertas` no commit a5c1af5 (09/05/2026).

    Estado: A.1 fechada. Tem `id` surrogate, `fonte`, `escopo_geografico`,
    UNIQUE(fonte, cod_alerta). Não tem ainda `cobrade_codigo` nem
    `fonte_classificacao` (vieram em A.2 / commit eb64f7a, 11/05/2026).

    Este caso deve PASSAR pela verificação de compatibilidade e ser
    aditivamente migrado por _migrar_banco() para o schema atual.
    """
    conexao.execute(
        """
        CREATE TABLE alertas (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fonte               TEXT NOT NULL DEFAULT 'CEMADEN',
            cod_alerta          TEXT NOT NULL,
            municipio           TEXT,
            uf                  TEXT,
            evento              TEXT,
            nivel               TEXT,
            datahoracriacao     TEXT,
            detectado_em        TEXT NOT NULL,
            codibge             INTEGER,
            latitude            REAL NOT NULL,
            longitude           REAL NOT NULL,
            escopo_geografico   TEXT NOT NULL DEFAULT 'INDETERMINADO',
            ult_atualizacao     TEXT,
            status_interno      TEXT NOT NULL DEFAULT 'ATIVO',
            visto_ultima_vez    TEXT NOT NULL DEFAULT '',
            rodadas_ausente     INTEGER NOT NULL DEFAULT 0,
            assinatura          TEXT,
            UNIQUE (fonte, cod_alerta)
        )
        """
    )
    conexao.execute("CREATE INDEX idx_uf ON alertas (uf)")
    conexao.execute("CREATE INDEX idx_evento ON alertas (evento)")
    conexao.execute("CREATE INDEX idx_nivel ON alertas (nivel)")
    conexao.execute("CREATE INDEX idx_fonte ON alertas (fonte)")
    conexao.execute("CREATE INDEX idx_escopo_geografico ON alertas (escopo_geografico)")
    conexao.execute(
        """
        CREATE TABLE eventos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo            TEXT NOT NULL,
            agregado_id     INTEGER NOT NULL,
            payload         TEXT NOT NULL,
            schema_versao   INTEGER NOT NULL DEFAULT 1,
            criado_em       TEXT NOT NULL,
            processado_em   TEXT NULL,
            tentativas      INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conexao.execute(
        "CREATE INDEX idx_eventos_pendentes ON eventos (processado_em, criado_em)"
    )
    conexao.commit()
