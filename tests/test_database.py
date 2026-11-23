"""Testes diretos de src/alertavida/database.py.

Cobre:
- Verificação de compatibilidade de schema (_verificar_compatibilidade_schema)
- Migration aditiva (_migrar_banco) sobre schemas legados que SÃO compatíveis
- Criação do schema atual via criar_banco() em banco vazio
- Idempotência: criar_banco() rodado N vezes não altera schema nem dados
"""

import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from alertavida import database as db_module
from alertavida.database import SchemaIncompativelError, conectar
from alertavida.domain.enums import FonteDado, TipoEvento
from alertavida.sources.cemaden import CemadenSource

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _colunas_de(db_path: Path, tabela: str) -> set[str]:
    """Retorna o conjunto de nomes de coluna de uma tabela."""
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        cursor = conexao.execute(f"PRAGMA table_info({tabela})")
        return {row[1] for row in cursor.fetchall()}


def _indices_de(db_path: Path, tabela: str) -> set[str]:
    """Retorna o conjunto de nomes de índice de uma tabela."""
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        cursor = conexao.execute(f"PRAGMA index_list({tabela})")
        return {row[1] for row in cursor.fetchall()}


def _patch_db_path(monkeypatch, db_path: Path) -> None:
    """Aponta o banco para o caminho temporário via env var (issue #22)."""
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(db_path))


def _inserir_alerta(db_path: Path, cod_alerta: str) -> int:
    """Insere um alerta mínimo via SQL cru e devolve o id gerado.

    Helper só para os testes de persistência de Incidente (issue #59), que
    precisam de um alerta_id real para satisfazer as FKs de
    incidente_membros/eventos.
    """
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        cursor = conexao.execute(
            """
            INSERT INTO alertas (fonte, cod_alerta, latitude, longitude, detectado_em)
            VALUES ('CEMADEN', ?, -10.0, -40.0, '2026-08-12T00:00:00')
            """,
            (cod_alerta,),
        )
        conexao.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


class TestCriacaoSchemaAtual:
    """criar_banco() em banco vazio produz schema A.2 completo."""

    def test_cria_tabela_alertas_com_todas_as_colunas_a2(
        self, tmp_path, monkeypatch
    ):
        db_path = tmp_path / "novo.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()

        colunas = _colunas_de(db_path, "alertas")
        assert "assinatura" not in colunas  # removida na manutenibilidade #8 B1
        # Colunas críticas do schema atual
        esperadas = {
            "id", "fonte", "cod_alerta", "escopo_geografico",
            "cobrade_codigo", "fonte_classificacao", "descricao",
        }
        assert esperadas.issubset(colunas)

        indices = _indices_de(db_path, "alertas")
        # Índices especulativos nunca criados (manutenibilidade #11 D3, #89)
        assert not {"idx_uf", "idx_evento", "idx_nivel"} & indices
        assert not {"idx_fonte", "idx_escopo_geografico"} & indices
        assert "sqlite_autoindex_alertas_1" in indices

    def test_cria_tabela_eventos(self, tmp_path, monkeypatch):
        db_path = tmp_path / "novo.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()

        colunas = _colunas_de(db_path, "eventos")
        assert {"id", "tipo", "agregado_id", "payload"}.issubset(colunas)


class TestIdempotencia:
    """criar_banco() rodado N vezes não altera schema nem dados."""

    def test_criar_banco_duas_vezes_em_banco_vazio(self, tmp_path, monkeypatch):
        db_path = tmp_path / "idem.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()
        colunas_1 = _colunas_de(db_path, "alertas")

        db_module.criar_banco()  # segunda vez — deve ser no-op
        colunas_2 = _colunas_de(db_path, "alertas")

        assert colunas_1 == colunas_2

class TestPersistenciaDescricao:
    """Manutenibilidade #11 D4: descricao é persistida no INSERT de AlertaCriado."""

    def test_criado_persiste_descricao(self, db_temporario, monkeypatch):
        from alertavida.database import aplicar_resultado_deteccao
        from alertavida.domain.alerta import Alerta
        from alertavida.domain.coordenadas import Coordenadas
        from alertavida.domain.detector import (
            EventoDetectado,
            ResultadoDeteccao,
            TipoEventoDetectado,
        )
        from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento

        alerta = Alerta(
            cod_alerta="E1",
            fonte=FonteDado.EONET,
            tipo_evento=TipoEvento.CLIMATOLOGICO,
            nivel_risco=NivelRisco.INDETERMINADO,
            coordenadas=Coordenadas(latitude=-3.0, longitude=-60.0),
            data_criacao=datetime(2026, 5, 18, tzinfo=timezone.utc),
            descricao="Wildfire - Amazonas, Brazil",
        )
        resultado = ResultadoDeteccao(
            eventos=[
                EventoDetectado(
                    tipo=TipoEventoDetectado.CRIADO,
                    cod_alerta="E1",
                    fonte=FonteDado.EONET,
                    payload={"cod_alerta": "E1", "fonte": "EONET"},
                )
            ],
            codigos_vistos={"E1"},
            codigos_ausentes=set(),
            fonte_por_codigo={"E1": FonteDado.EONET},
        )

        aplicar_resultado_deteccao(resultado, {"E1": alerta}, "2026-05-18T00:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            row = conexao.execute(
                "SELECT descricao FROM alertas WHERE cod_alerta = 'E1'"
            ).fetchone()

        assert row[0] == "Wildfire - Amazonas, Brazil"

    def test_criado_sem_descricao_persiste_null(self, db_temporario, monkeypatch):
        from alertavida.database import aplicar_resultado_deteccao
        from alertavida.domain.alerta import Alerta
        from alertavida.domain.coordenadas import Coordenadas
        from alertavida.domain.detector import (
            EventoDetectado,
            ResultadoDeteccao,
            TipoEventoDetectado,
        )
        from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento

        alerta = Alerta(
            cod_alerta="C1",
            fonte=FonteDado.CEMADEN,
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.MODERADO,
            coordenadas=Coordenadas(latitude=-8.0, longitude=-34.0),
            data_criacao=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        resultado = ResultadoDeteccao(
            eventos=[
                EventoDetectado(
                    tipo=TipoEventoDetectado.CRIADO,
                    cod_alerta="C1",
                    fonte=FonteDado.CEMADEN,
                    payload={"cod_alerta": "C1", "fonte": "CEMADEN"},
                )
            ],
            codigos_vistos={"C1"},
            codigos_ausentes=set(),
            fonte_por_codigo={"C1": FonteDado.CEMADEN},
        )

        aplicar_resultado_deteccao(resultado, {"C1": alerta}, "2026-05-01T00:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            row = conexao.execute(
                "SELECT descricao FROM alertas WHERE cod_alerta = 'C1'"
            ).fetchone()

        assert row[0] is None


class TestReativado:
    """REATIVADO volta status para ATIVO e zera rodadas_ausente."""

    def test_reativado_reativa_alerta_resolvido(self, db_temporario, monkeypatch):
        from alertavida.database import aplicar_resultado_deteccao
        from alertavida.domain.alerta import Alerta
        from alertavida.domain.coordenadas import Coordenadas
        from alertavida.domain.detector import (
            EventoDetectado,
            ResultadoDeteccao,
            TipoEventoDetectado,
        )
        from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            conexao.execute(
                """
                INSERT INTO alertas (
                    fonte, cod_alerta, latitude, longitude, detectado_em,
                    status_interno, rodadas_ausente
                ) VALUES (?, ?, ?, ?, ?, 'RESOLVIDO', 3)
                """,
                ("CEMADEN", "R1", -10.0, -40.0, "2026-06-11T10:00:00"),
            )
            conexao.commit()

        alerta = Alerta(
            cod_alerta="R1",
            fonte=FonteDado.CEMADEN,
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
            data_criacao=datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc),
        )
        resultado = ResultadoDeteccao(
            eventos=[
                EventoDetectado(
                    tipo=TipoEventoDetectado.REATIVADO,
                    cod_alerta="R1",
                    fonte=FonteDado.CEMADEN,
                    payload={"cod_alerta": "R1", "fonte": "CEMADEN"},
                )
            ],
            codigos_vistos={"R1"},
            codigos_ausentes=set(),
            fonte_por_codigo={"R1": FonteDado.CEMADEN},
        )

        aplicar_resultado_deteccao(resultado, {"R1": alerta}, "2026-06-11T11:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            row = conexao.execute(
                "SELECT status_interno, rodadas_ausente, nivel, evento "
                "FROM alertas WHERE cod_alerta = 'R1'"
            ).fetchone()

        assert row[0] == "ATIVO", f"Esperado ATIVO, obtido {row[0]}"
        assert row[1] == 0, f"Esperado rodadas_ausente=0, obtido {row[1]}"
        assert row[2] == "ALTO"
        assert row[3] == "HIDROLOGICO"

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            count = conexao.execute(
                "SELECT COUNT(*) FROM eventos WHERE tipo = 'AlertaReativado'"
            ).fetchone()[0]
        assert count == 1


    def test_criar_banco_preserva_dados(self, tmp_path, monkeypatch):
        db_path = tmp_path / "com_dados.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()
        with contextlib.closing(sqlite3.connect(db_path)) as conexao:
            conexao.execute(
                """
                INSERT INTO alertas (
                    fonte, cod_alerta, latitude, longitude, detectado_em
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("CEMADEN", "999", -10.0, -40.0, "2026-05-12T10:00:00"),
            )
            conexao.commit()

        db_module.criar_banco()  # não pode apagar dados

        with contextlib.closing(sqlite3.connect(db_path)) as conexao:
            n = conexao.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
        assert n == 1


class TestRollbackAtomicidade:
    """Issue #40: rollback-on-exception de `conectar()` é load-bearing —
    mantém INSERT em alertas + INSERT em eventos atômicos (outbox pattern,
    wiki/patterns/resilience-invariants.md #4)."""

    def test_excecao_no_meio_reverte_toda_a_transacao(self, db_temporario):
        from alertavida.database import aplicar_resultado_deteccao
        from alertavida.domain.alerta import Alerta
        from alertavida.domain.coordenadas import Coordenadas
        from alertavida.domain.detector import (
            EventoDetectado,
            ResultadoDeteccao,
            TipoEventoDetectado,
        )
        from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento

        alerta_ok = Alerta(
            cod_alerta="OK1",
            fonte=FonteDado.CEMADEN,
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.MODERADO,
            coordenadas=Coordenadas(latitude=-8.0, longitude=-34.0),
            data_criacao=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        resultado = ResultadoDeteccao(
            eventos=[
                EventoDetectado(
                    tipo=TipoEventoDetectado.CRIADO,
                    cod_alerta="OK1",
                    fonte=FonteDado.CEMADEN,
                    payload={"cod_alerta": "OK1", "fonte": "CEMADEN"},
                ),
                EventoDetectado(
                    tipo=TipoEventoDetectado.CRIADO,
                    cod_alerta="FALTANDO",
                    fonte=FonteDado.CEMADEN,
                    payload={"cod_alerta": "FALTANDO", "fonte": "CEMADEN"},
                ),
            ],
            codigos_vistos={"OK1", "FALTANDO"},
            codigos_ausentes=set(),
            fonte_por_codigo={"OK1": FonteDado.CEMADEN, "FALTANDO": FonteDado.CEMADEN},
        )

        # alertas_por_codigo só contém OK1 -> KeyError ao processar o segundo
        # evento, no meio da transação (após o INSERT de OK1 já ter rodado).
        with pytest.raises(KeyError):
            aplicar_resultado_deteccao(
                resultado, {"OK1": alerta_ok}, "2026-05-01T00:00:00"
            )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            n_alertas = conexao.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
            n_eventos = conexao.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]

        assert n_alertas == 0, "INSERT de OK1 deveria ter sido revertido pelo rollback"
        assert n_eventos == 0, "INSERT em eventos deveria ter sido revertido pelo rollback"


class TestForeignKeyEventos:
    """Issue #22 item B: `eventos.agregado_id` -> `alertas.id` via FOREIGN KEY.

    A garantia é POR CONEXÃO: vale para quem passa por `conectar()`
    (PRAGMA foreign_keys=ON), não para conexões cruas do sqlite3.
    """

    def test_banco_novo_declara_a_fk(self, db_temporario):
        """criar_banco() deixa a FK declarada para alertas(id).

        Desde a #59, `eventos` também carrega uma segunda FK opcional para
        `incidentes(id)` (`agregado_incidente_id`) — ver
        TestPersistenciaIncidente.TestSchemaIncidente para a cobertura dela.
        """
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            fks = conexao.execute("PRAGMA foreign_key_list(eventos)").fetchall()

        # foreign_key_list: (id, seq, table, from, to, on_update, on_delete, match)
        fks_para_alertas = [fk for fk in fks if fk[2] == "alertas"]
        assert len(fks_para_alertas) == 1, "eventos deveria ter exatamente uma FK para alertas"
        _, _, tabela, coluna_filha, coluna_pai, *_rest = fks_para_alertas[0]
        assert tabela == "alertas"
        assert coluna_filha == "agregado_id"
        assert coluna_pai == "id"

    def test_conectar_impoe_a_fk_no_insert_orfao(self, db_temporario):
        """Via conectar() (FK ON), inserir evento com agregado_id órfão levanta."""
        with pytest.raises(sqlite3.IntegrityError):
            with conectar() as conexao:
                conexao.execute(
                    """
                    INSERT INTO eventos (tipo, agregado_id, payload, criado_em)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("AlertaCriado", 99999, "{}", "2026-07-28T00:00:00"),
                )

    def test_conexao_crua_nao_impoe_a_fk(self, db_temporario):
        """Contraprova: a mesma inserção órfã por conexão crua NÃO levanta.

        Documenta que o enforcement é por conexão (foreign_keys OFF por
        default no sqlite3) — é o que mantém verdes as fixtures de teste que
        inserem eventos sem alerta pai via conexão crua.
        """
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            conexao.execute(
                """
                INSERT INTO eventos (tipo, agregado_id, payload, criado_em)
                VALUES (?, ?, ?, ?)
                """,
                ("AlertaCriado", 99999, "{}", "2026-07-28T00:00:00"),
            )
            conexao.commit()
            n = conexao.execute(
                "SELECT COUNT(*) FROM eventos WHERE agregado_id = 99999"
            ).fetchone()[0]

        assert n == 1

# ----------------------------------------------------------------------
# Persistência de Incidente (issue #59) — tabelas, proveniência, redirect
# de fusão, eventos de outbox.
# ----------------------------------------------------------------------

class TestSchemaIncidente:
    """Tabelas incidentes/incidente_membros + FKs + índices.

    Mesmo estilo de TestCriacaoSchemaAtual/TestMigrationAditiva.
    """

    def test_cria_tabela_incidentes(self, db_temporario):
        colunas = _colunas_de(db_temporario, "incidentes")
        esperadas = {"id", "status", "criado_em", "atualizado_em", "resolvido_em", "fundido_em"}
        assert esperadas.issubset(colunas)

    def test_incidentes_tem_fk_autorreferente_fundido_em(self, db_temporario):
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            fks = conexao.execute("PRAGMA foreign_key_list(incidentes)").fetchall()

        assert len(fks) == 1, "incidentes deveria ter exatamente uma FOREIGN KEY"
        _, _, tabela, coluna_filha, coluna_pai, *_rest = fks[0]
        assert tabela == "incidentes"
        assert coluna_filha == "fundido_em"
        assert coluna_pai == "id"

    def test_incidentes_tem_indices_de_fundido_em_e_candidatos(self, db_temporario):
        indices = _indices_de(db_temporario, "incidentes")
        assert "idx_incidentes_fundido_em" in indices
        assert "idx_incidentes_status_fundido" in indices

    def test_cria_tabela_incidente_membros(self, db_temporario):
        colunas = _colunas_de(db_temporario, "incidente_membros")
        esperadas = {"id", "incidente_id", "alerta_id", "score", "motivo", "criado_em"}
        assert esperadas.issubset(colunas)

    def test_incidente_membros_tem_as_duas_fks(self, db_temporario):
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            fks = conexao.execute("PRAGMA foreign_key_list(incidente_membros)").fetchall()

        tabelas_referenciadas = {fk[2] for fk in fks}
        assert tabelas_referenciadas == {"incidentes", "alertas"}

    def test_incidente_membros_tem_unique_em_alerta_id(self, db_temporario):
        """UNIQUE(alerta_id): um Alerta pertence a no máximo um Incidente vivo."""
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            indices = conexao.execute("PRAGMA index_list(incidente_membros)").fetchall()

        # PRAGMA index_list: (seq, name, unique, origin, partial) — origin='u'
        # é o índice autogerado pela constraint UNIQUE da coluna.
        indices_unicos = [idx for idx in indices if idx[2] == 1]
        assert len(indices_unicos) == 1

    def test_incidente_membros_tem_indice_no_incidente_id(self, db_temporario):
        indices = _indices_de(db_temporario, "incidente_membros")
        assert "idx_incidente_membros_incidente_id" in indices

    def test_eventos_tem_fk_para_incidentes(self, db_temporario):
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            fks = conexao.execute("PRAGMA foreign_key_list(eventos)").fetchall()

        fks_para_incidentes = [fk for fk in fks if fk[2] == "incidentes"]
        assert len(fks_para_incidentes) == 1
        _, _, tabela, coluna_filha, coluna_pai, *_rest = fks_para_incidentes[0]
        assert coluna_filha == "agregado_incidente_id"
        assert coluna_pai == "id"

    def test_eventos_tem_indice_no_agregado_incidente_id(self, db_temporario):
        indices = _indices_de(db_temporario, "eventos")
        assert "idx_eventos_agregado_incidente_id" in indices

    def test_criar_banco_duas_vezes_e_idempotente(self, tmp_path, monkeypatch):
        db_path = tmp_path / "idem_incidente.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()
        incidentes_1 = _colunas_de(db_path, "incidentes")
        membros_1 = _colunas_de(db_path, "incidente_membros")

        db_module.criar_banco()  # segunda vez — deve ser no-op

        assert _colunas_de(db_path, "incidentes") == incidentes_1
        assert _colunas_de(db_path, "incidente_membros") == membros_1


class TestForeignKeyIncidentes:
    """FKs de incidente_membros/incidentes/eventos, POR CONEXÃO — mesma
    disciplina da #22 (TestForeignKeyEventos)."""

    def test_conectar_impoe_fk_de_incidente_membros_para_incidentes(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")

        with pytest.raises(sqlite3.IntegrityError):
            with conectar() as conexao:
                conexao.execute(
                    """
                    INSERT INTO incidente_membros (
                        incidente_id, alerta_id, score, motivo, criado_em
                    ) VALUES (99999, ?, 0.9, 'teste', '2026-08-12T00:00:00')
                    """,
                    (alerta_id,),
                )

    def test_conectar_impoe_fk_de_incidente_membros_para_alertas(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(alerta_id, 0.9, "teste", "2026-08-12T00:00:00")

        with pytest.raises(sqlite3.IntegrityError):
            with conectar() as conexao:
                conexao.execute(
                    """
                    INSERT INTO incidente_membros (
                        incidente_id, alerta_id, score, motivo, criado_em
                    ) VALUES (?, 99999, 0.9, 'teste', '2026-08-12T00:00:01')
                    """,
                    (incidente_id,),
                )

    def test_conectar_impoe_fk_de_fundido_em(self, db_temporario):
        with pytest.raises(sqlite3.IntegrityError):
            with conectar() as conexao:
                conexao.execute(
                    "INSERT INTO incidentes (status, criado_em, atualizado_em, fundido_em) "
                    "VALUES ('RESOLVIDO', '2026-08-12T00:00:00', '2026-08-12T00:00:00', 99999)"
                )

    def test_conectar_impoe_fk_de_agregado_incidente_id(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")

        with pytest.raises(sqlite3.IntegrityError):
            with conectar() as conexao:
                conexao.execute(
                    """
                    INSERT INTO eventos (
                        tipo, agregado_id, agregado_incidente_id, payload, criado_em
                    ) VALUES ('IncidenteCriado', ?, 99999, '{}', '2026-08-12T00:00:00')
                    """,
                    (alerta_id,),
                )

    def test_unique_alerta_id_impede_membro_duplicado(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        db_module.criar_incidente(alerta_id, 0.9, "fundador", "2026-08-12T00:00:00")
        outro_incidente_id = db_module.criar_incidente(
            _inserir_alerta(db_temporario, "A2"), 0.9, "fundador", "2026-08-12T00:00:01"
        )

        with pytest.raises(sqlite3.IntegrityError):
            db_module.adicionar_membro_incidente(
                outro_incidente_id, alerta_id, 0.5, "duplicado", "2026-08-12T00:00:02"
            )


class TestInvarianteAgregadoIncidenteId:
    """agregado_incidente_id IS NOT NULL SSE o evento é de ciclo de vida de
    Incidente — validado em runtime por `_inserir_evento_outbox`, não como
    CHECK constraint (SQLite não permite adicioná-la via ALTER TABLE)."""

    def test_evento_de_incidente_sem_agregado_incidente_id_levanta(self, db_temporario):
        from alertavida.database import _inserir_evento_outbox

        with pytest.raises(ValueError, match="Invariante violada"):
            with conectar() as conexao:
                _inserir_evento_outbox(
                    conexao,
                    tipo="IncidenteCriado",
                    agregado_id=1,
                    agregado_incidente_id=None,
                    payload={},
                    criado_em="2026-08-12T00:00:00",
                )

    def test_evento_de_alerta_com_agregado_incidente_id_levanta(self, db_temporario):
        from alertavida.database import _inserir_evento_outbox

        with pytest.raises(ValueError, match="Invariante violada"):
            with conectar() as conexao:
                _inserir_evento_outbox(
                    conexao,
                    tipo="AlertaCriado",
                    agregado_id=1,
                    agregado_incidente_id=1,
                    payload={},
                    criado_em="2026-08-12T00:00:00",
                )


class TestRollbackAtomicidadeIncidente:
    """Cada função de transição de Incidente escreve estado + evento na
    MESMA transação (invariante 4) — mesmo estilo de
    TestRollbackAtomicidade."""

    def test_criar_incidente_com_alerta_inexistente_nao_deixa_residuo(self, db_temporario):
        with pytest.raises(sqlite3.IntegrityError):
            db_module.criar_incidente(99999, 0.9, "teste", "2026-08-12T00:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            n_incidentes = conexao.execute("SELECT COUNT(*) FROM incidentes").fetchone()[0]
            n_membros = conexao.execute("SELECT COUNT(*) FROM incidente_membros").fetchone()[0]
            n_eventos = conexao.execute(
                "SELECT COUNT(*) FROM eventos WHERE tipo = 'IncidenteCriado'"
            ).fetchone()[0]

        assert n_incidentes == 0, "INSERT em incidentes deveria ter sido revertido pelo rollback"
        assert n_membros == 0
        assert n_eventos == 0

    def test_adicionar_membro_duplicado_nao_deixa_residuo(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        db_module.criar_incidente(alerta_id, 0.9, "fundador", "2026-08-12T00:00:00")
        outro_incidente_id = db_module.criar_incidente(
            _inserir_alerta(db_temporario, "A2"), 0.9, "fundador", "2026-08-12T00:00:01"
        )

        with pytest.raises(sqlite3.IntegrityError):
            db_module.adicionar_membro_incidente(
                outro_incidente_id, alerta_id, 0.5, "duplicado", "2026-08-12T05:00:00"
            )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            atualizado_em = conexao.execute(
                "SELECT atualizado_em FROM incidentes WHERE id = ?", (outro_incidente_id,)
            ).fetchone()[0]
            n_eventos_atualizado = conexao.execute(
                "SELECT COUNT(*) FROM eventos WHERE tipo = 'IncidenteAtualizado'"
            ).fetchone()[0]

        assert atualizado_em == "2026-08-12T00:00:01", (
            "UPDATE atualizado_em deveria ter sido revertido"
        )
        assert n_eventos_atualizado == 0


class TestCriarIncidente:
    def test_persiste_incidente_e_membro_fundador(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")

        incidente_id = db_module.criar_incidente(
            alerta_id, 0.9, "mesmo_codigo_ibge", "2026-08-12T00:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            incidente = conexao.execute(
                "SELECT status, criado_em, atualizado_em, resolvido_em, fundido_em "
                "FROM incidentes WHERE id = ?",
                (incidente_id,),
            ).fetchone()
            membro = conexao.execute(
                "SELECT incidente_id, alerta_id, score, motivo "
                "FROM incidente_membros WHERE incidente_id = ?",
                (incidente_id,),
            ).fetchone()

        assert incidente == ("ATIVO", "2026-08-12T00:00:00", "2026-08-12T00:00:00", None, None)
        assert membro == (incidente_id, alerta_id, 0.9, "mesmo_codigo_ibge")

    def test_emite_incidente_criado(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")

        incidente_id = db_module.criar_incidente(
            alerta_id, 0.9, "mesmo_codigo_ibge", "2026-08-12T00:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            evento = conexao.execute(
                "SELECT tipo, agregado_id, agregado_incidente_id, payload "
                "FROM eventos WHERE tipo = 'IncidenteCriado'"
            ).fetchone()

        assert evento[0] == "IncidenteCriado"
        assert evento[1] == alerta_id
        assert evento[2] == incidente_id
        assert json.loads(evento[3]) == {
            "incidente_id": incidente_id,
            "alerta_id": alerta_id,
            "score": 0.9,
            "motivo": "mesmo_codigo_ibge",
        }


class TestAdicionarMembroIncidente:
    def test_persiste_novo_membro_e_atualiza_incidente(self, db_temporario):
        fundador_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            fundador_id, 0.9, "fundador", "2026-08-12T00:00:00"
        )
        novo_membro_id = _inserir_alerta(db_temporario, "A2")

        db_module.adicionar_membro_incidente(
            incidente_id, novo_membro_id, 0.7, "distancia_proxima", "2026-08-12T01:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            membros = conexao.execute(
                "SELECT alerta_id FROM incidente_membros WHERE incidente_id = ?",
                (incidente_id,),
            ).fetchall()
            atualizado_em = conexao.execute(
                "SELECT atualizado_em FROM incidentes WHERE id = ?", (incidente_id,)
            ).fetchone()[0]

        assert {m[0] for m in membros} == {fundador_id, novo_membro_id}
        assert atualizado_em == "2026-08-12T01:00:00"

    def test_emite_incidente_atualizado(self, db_temporario):
        fundador_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            fundador_id, 0.9, "fundador", "2026-08-12T00:00:00"
        )
        novo_membro_id = _inserir_alerta(db_temporario, "A2")

        db_module.adicionar_membro_incidente(
            incidente_id, novo_membro_id, 0.7, "distancia_proxima", "2026-08-12T01:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            evento = conexao.execute(
                "SELECT tipo, agregado_id, agregado_incidente_id "
                "FROM eventos WHERE tipo = 'IncidenteAtualizado'"
            ).fetchone()

        assert evento == ("IncidenteAtualizado", novo_membro_id, incidente_id)


class TestResolverIncidente:
    def test_resolve_e_marca_resolvido_em(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(alerta_id, 0.9, "fundador", "2026-08-12T00:00:00")

        db_module.resolver_incidente(incidente_id, alerta_id, "2026-08-12T02:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            status, resolvido_em = conexao.execute(
                "SELECT status, resolvido_em FROM incidentes WHERE id = ?", (incidente_id,)
            ).fetchone()

        assert status == "RESOLVIDO"
        assert resolvido_em == "2026-08-12T02:00:00"

    def test_emite_incidente_resolvido(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(alerta_id, 0.9, "fundador", "2026-08-12T00:00:00")

        db_module.resolver_incidente(incidente_id, alerta_id, "2026-08-12T02:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            evento = conexao.execute(
                "SELECT tipo, agregado_id, agregado_incidente_id "
                "FROM eventos WHERE tipo = 'IncidenteResolvido'"
            ).fetchone()

        assert evento == ("IncidenteResolvido", alerta_id, incidente_id)


class TestReativarIncidente:
    def test_reativa_e_limpa_resolvido_em(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(alerta_id, 0.9, "fundador", "2026-08-12T00:00:00")
        db_module.resolver_incidente(incidente_id, alerta_id, "2026-08-12T02:00:00")

        db_module.reativar_incidente(incidente_id, alerta_id, "2026-08-12T03:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            status, resolvido_em = conexao.execute(
                "SELECT status, resolvido_em FROM incidentes WHERE id = ?", (incidente_id,)
            ).fetchone()

        assert status == "ATIVO"
        assert resolvido_em is None

    def test_emite_incidente_reativado(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(alerta_id, 0.9, "fundador", "2026-08-12T00:00:00")
        db_module.resolver_incidente(incidente_id, alerta_id, "2026-08-12T02:00:00")

        db_module.reativar_incidente(incidente_id, alerta_id, "2026-08-12T03:00:00")

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            evento = conexao.execute(
                "SELECT tipo, agregado_id, agregado_incidente_id "
                "FROM eventos WHERE tipo = 'IncidenteReativado'"
            ).fetchone()

        assert evento == ("IncidenteReativado", alerta_id, incidente_id)


class TestFundirIncidentes:
    """Redirect append-only (Round 1, Q6): o Incidente fundido nunca é
    apagado nem tem seus membros movidos; ambos os ids continuam
    resolvíveis."""

    def test_redirect_append_only_preserva_membros_do_fundido(self, db_temporario):
        sobrevivente_alerta = _inserir_alerta(db_temporario, "A1")
        sobrevivente_id = db_module.criar_incidente(
            sobrevivente_alerta, 0.9, "fundador", "2026-08-12T00:00:00"
        )
        fundido_alerta = _inserir_alerta(db_temporario, "A2")
        fundido_id = db_module.criar_incidente(
            fundido_alerta, 0.9, "fundador", "2026-08-12T00:00:01"
        )
        disparador_alerta = _inserir_alerta(db_temporario, "A3")

        db_module.fundir_incidentes(
            sobrevivente_id, fundido_id, disparador_alerta, "2026-08-12T04:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            fundido_em = conexao.execute(
                "SELECT fundido_em FROM incidentes WHERE id = ?", (fundido_id,)
            ).fetchone()[0]
            membros_fundido = conexao.execute(
                "SELECT alerta_id FROM incidente_membros WHERE incidente_id = ?",
                (fundido_id,),
            ).fetchall()

        assert fundido_em == sobrevivente_id
        assert membros_fundido == [(fundido_alerta,)]

    def test_ambos_ids_continuam_resolviveis(self, db_temporario):
        sobrevivente_alerta = _inserir_alerta(db_temporario, "A1")
        sobrevivente_id = db_module.criar_incidente(
            sobrevivente_alerta, 0.9, "fundador", "2026-08-12T00:00:00"
        )
        fundido_alerta = _inserir_alerta(db_temporario, "A2")
        fundido_id = db_module.criar_incidente(
            fundido_alerta, 0.9, "fundador", "2026-08-12T00:00:01"
        )
        disparador_alerta = _inserir_alerta(db_temporario, "A3")

        db_module.fundir_incidentes(
            sobrevivente_id, fundido_id, disparador_alerta, "2026-08-12T04:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            ids_existentes = {
                row[0] for row in conexao.execute("SELECT id FROM incidentes").fetchall()
            }

        assert {sobrevivente_id, fundido_id}.issubset(ids_existentes)

    def test_emite_incidente_fundido(self, db_temporario):
        sobrevivente_alerta = _inserir_alerta(db_temporario, "A1")
        sobrevivente_id = db_module.criar_incidente(
            sobrevivente_alerta, 0.9, "fundador", "2026-08-12T00:00:00"
        )
        fundido_alerta = _inserir_alerta(db_temporario, "A2")
        fundido_id = db_module.criar_incidente(
            fundido_alerta, 0.9, "fundador", "2026-08-12T00:00:01"
        )
        disparador_alerta = _inserir_alerta(db_temporario, "A3")

        db_module.fundir_incidentes(
            sobrevivente_id, fundido_id, disparador_alerta, "2026-08-12T04:00:00"
        )

        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            evento = conexao.execute(
                "SELECT tipo, agregado_id, agregado_incidente_id, payload "
                "FROM eventos WHERE tipo = 'IncidenteFundido'"
            ).fetchone()

        assert evento[0] == "IncidenteFundido"
        assert evento[1] == disparador_alerta
        assert evento[2] == fundido_id
        assert json.loads(evento[3]) == {
            "incidente_sobrevivente_id": sobrevivente_id,
            "incidente_fundido_id": fundido_id,
            "alerta_id_disparador": disparador_alerta,
        }


# ----------------------------------------------------------------------
# Disponibilidade do R-Tree do SQLite (issue #60) — prova empírica, não
# inferência (wiki/_schema.md regra 1). A matriz de CI cobre ubuntu-latest
# e windows-latest com o mesmo `uv python install`; a saída deste teste nas
# duas pernas É a evidência colada no corpo do PR. Se qualquer perna falhar
# aqui, o candidato de blocking usa o fallback de colunas indexadas
# (ver decisions/ se o fallback for necessário) em vez do R-Tree.
# ----------------------------------------------------------------------

class TestCapacidadeEspacialSQLite:
    def test_rtree_habilitado_via_compile_options(self):
        with contextlib.closing(sqlite3.connect(":memory:")) as conexao:
            opcoes = [row[0] for row in conexao.execute("PRAGMA compile_options")]

        assert any("RTREE" in opcao.upper() for opcao in opcoes), (
            f"SQLITE_ENABLE_RTREE ausente em compile_options: {sorted(opcoes)}"
        )

    def test_rtree_cria_tabela_virtual_e_consulta(self):
        with contextlib.closing(sqlite3.connect(":memory:")) as conexao:
            conexao.execute(
                "CREATE VIRTUAL TABLE probe_rtree USING rtree("
                "id, min_lat, max_lat, min_lon, max_lon)"
            )
            conexao.execute("INSERT INTO probe_rtree VALUES (1, -30.0, -29.0, -57.0, -56.0)")

            linhas = conexao.execute(
                "SELECT id FROM probe_rtree "
                "WHERE min_lat <= -29.5 AND max_lat >= -29.5 "
                "AND min_lon <= -56.5 AND max_lon >= -56.5"
            ).fetchall()

        assert linhas == [(1,)]


# ----------------------------------------------------------------------
# Blocking de correlação (issue #60) — geração de candidatos + instrumentação
# ----------------------------------------------------------------------

def _inserir_alerta_correlacao(
    db_path: Path,
    *,
    cod_alerta: str,
    fonte: str = "CEMADEN",
    evento: str = "HIDROLOGICO",
    cobrade_codigo: str | None = "1.2.1.0.0",
    codibge: int | None = 4322400,
    latitude: float,
    longitude: float,
    datahoracriacao: str,
) -> int:
    """Insere um alerta com os campos que o blocking usa (evento, cobrade,
    codibge, posição, onset) e o registra em `idx_alertas_espacial` — o
    mesmo par de INSERTs que `aplicar_resultado_deteccao` faz no ramo
    CRIADO. `_inserir_alerta` (issue #59) não serve aqui: cobre só os
    campos mínimos para as FKs de incidente, sem posição/onset reais.
    """
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        cursor = conexao.execute(
            """
            INSERT INTO alertas (
                fonte, cod_alerta, evento, cobrade_codigo, codibge,
                latitude, longitude, datahoracriacao, detectado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fonte,
                cod_alerta,
                evento,
                cobrade_codigo,
                codibge,
                latitude,
                longitude,
                datahoracriacao,
                datahoracriacao,
            ),
        )
        alerta_id = cursor.lastrowid
        assert alerta_id is not None
        conexao.execute(
            """
            INSERT INTO idx_alertas_espacial (id, min_lat, max_lat, min_lon, max_lon)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alerta_id, latitude, latitude, longitude, longitude),
        )
        conexao.commit()
    return alerta_id


class TestAvaliarCandidatosCorrelacao:
    def test_sem_nenhum_incidente_aberto_grava_observacao_sem_candidato(self, db_temporario):
        alerta_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            alerta_id, "2026-08-12T10:00:00+00:00"
        )

        assert len(resultados) == 1
        assert resultados[0].incidente_id is None
        assert resultados[0].decisao.resultado.value == "NAO_VINCULA"
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            observacao = conexao.execute(
                "SELECT alerta_id, incidente_id, distancia_km, decisao, motivo "
                "FROM correlacao_observacoes"
            ).fetchone()
        assert observacao == (alerta_id, None, None, "NAO_VINCULA", "sem_candidatos")

    def test_incidente_dentro_do_bbox_e_da_janela_e_candidato(self, db_temporario):
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        incidente_id = db_module.criar_incidente(
            fundador_id, 1.0, "fundador", "2026-08-12T10:00:00+00:00"
        )
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T11:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T11:00:00+00:00"
        )

        assert len(resultados) == 1
        assert resultados[0].incidente_id == incidente_id
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            observacao = conexao.execute(
                "SELECT alerta_id, incidente_id, mesmo_codibge, decisao "
                "FROM correlacao_observacoes"
            ).fetchone()
        assert observacao == (novo_id, incidente_id, 1, resultados[0].decisao.resultado.value)

    def test_fora_do_bbox_nao_e_candidato(self, db_temporario):
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        db_module.criar_incidente(fundador_id, 1.0, "fundador", "2026-08-12T10:00:00+00:00")
        # Belém (~PA), a milhares de km de distância — muito além do buffer
        # de blocking (~0.54° derivado de DISTANCIA_MAXIMA_KM).
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-1.45,
            longitude=-48.48,
            datahoracriacao="2026-08-12T11:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T11:00:00+00:00"
        )

        assert len(resultados) == 1
        assert resultados[0].incidente_id is None
        assert resultados[0].decisao.motivo == "sem_candidatos"

    def test_fora_da_janela_de_tempo_nao_e_candidato(self, db_temporario):
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T00:00:00+00:00",
        )
        db_module.criar_incidente(fundador_id, 1.0, "fundador", "2026-08-12T00:00:00+00:00")
        # Mesmo bbox, mas 7h de diferença de onset — além da janela de 6h
        # (JANELA_TEMPO_SEGUNDOS, importada de domain/correlacao.py).
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T07:00:01+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T07:00:01+00:00"
        )

        assert len(resultados) == 1
        assert resultados[0].incidente_id is None
        assert resultados[0].decisao.motivo == "sem_candidatos"

    def test_incidente_resolvido_nao_e_candidato(self, db_temporario):
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        incidente_id = db_module.criar_incidente(
            fundador_id, 1.0, "fundador", "2026-08-12T10:00:00+00:00"
        )
        db_module.resolver_incidente(incidente_id, fundador_id, "2026-08-12T10:30:00+00:00")
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T11:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T11:00:00+00:00"
        )

        assert resultados[0].incidente_id is None
        assert resultados[0].decisao.motivo == "sem_candidatos"

    def test_incidente_fundido_nao_e_candidato(self, db_temporario):
        sobrevivente_alerta = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-20.0,
            longitude=-45.0,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        sobrevivente_id = db_module.criar_incidente(
            sobrevivente_alerta, 1.0, "fundador", "2026-08-12T10:00:00+00:00"
        )
        fundido_alerta = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A2",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        fundido_id = db_module.criar_incidente(
            fundido_alerta, 1.0, "fundador", "2026-08-12T10:00:01+00:00"
        )
        disparador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A3",
            latitude=0.0,
            longitude=0.0,
            datahoracriacao="2026-08-12T10:00:02+00:00",
        )
        db_module.fundir_incidentes(
            sobrevivente_id, fundido_id, disparador_id, "2026-08-12T10:30:00+00:00"
        )
        # Mesmo bbox/janela do incidente FUNDIDO (não do sobrevivente).
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T11:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T11:00:00+00:00"
        )

        assert resultados[0].incidente_id is None
        assert resultados[0].decisao.motivo == "sem_candidatos"

    def test_grava_observacao_para_par_avaliado_nao_vincula(self, db_temporario):
        """Par avaliado (dentro do bbox/janela), mas tipo incompatível —
        NAO_VINCULA ainda assim vira uma linha em correlacao_observacoes
        (Round 1, Q1: "TODO par avaliado, inclusive NAO_VINCULA")."""
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            evento="HIDROLOGICO",
            cobrade_codigo="1.2.1.0.0",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        db_module.criar_incidente(fundador_id, 1.0, "fundador", "2026-08-12T10:00:00+00:00")
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            evento="GEOLOGICO",
            cobrade_codigo="1.1.1.0.0",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T11:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T11:00:00+00:00"
        )

        assert len(resultados) == 1
        assert resultados[0].decisao.resultado.value == "NAO_VINCULA"
        assert resultados[0].decisao.motivo == "tipos_incompativeis"
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            observacao = conexao.execute(
                "SELECT incidente_id, decisao, motivo FROM correlacao_observacoes"
            ).fetchone()
        assert observacao[0] is not None
        assert observacao[1] == "NAO_VINCULA"
        assert observacao[2] == "tipos_incompativeis"

    def test_janela_assimetrica_respeita_sinal(self, db_temporario, monkeypatch):
        """delta_t > 0 (alerta avaliado com onset DEPOIS do representante) é
        checado contra janela_depois, não contra janela_antes — um par que
        passaria numa janela simétrica de 6h (o único valor usado antes desta
        mudança) é excluído quando janela_depois é estreitada para 4h,
        provando que a comparação usa o sinal de delta_t, não abs(delta_t)."""
        monkeypatch.setitem(
            db_module.JANELA_ABERTA_SEGUNDOS_POR_TIPO,
            TipoEvento.HIDROLOGICO,
            (6 * 3600.0, 4 * 3600.0),  # (janela_antes, janela_depois)
        )
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )
        db_module.criar_incidente(fundador_id, 1.0, "fundador", "2026-08-12T10:00:00+00:00")
        # +5h: dentro de uma janela simétrica de 6h, fora da janela_depois de 4h.
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T15:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T15:00:00+00:00"
        )

        assert resultados[0].incidente_id is None
        assert resultados[0].decisao.motivo == "sem_candidatos"

    def test_janela_assimetrica_aceita_dentro_do_lado_antes(self, db_temporario, monkeypatch):
        """Mesma janela assimétrica do teste acima, mas delta_t < 0 (alerta
        avaliado com onset ANTES do representante) — dentro de janela_antes
        (6h), então é candidato mesmo excedendo janela_depois (4h), provando
        que os dois lados são checados independentemente."""
        monkeypatch.setitem(
            db_module.JANELA_ABERTA_SEGUNDOS_POR_TIPO,
            TipoEvento.HIDROLOGICO,
            (6 * 3600.0, 4 * 3600.0),  # (janela_antes, janela_depois)
        )
        fundador_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A1",
            latitude=-29.84,
            longitude=-56.73,
            datahoracriacao="2026-08-12T15:00:00+00:00",
        )
        incidente_id = db_module.criar_incidente(
            fundador_id, 1.0, "fundador", "2026-08-12T15:00:00+00:00"
        )
        # -5h: fora da janela_depois (4h) se o sinal fosse ignorado, mas
        # dentro de janela_antes (6h).
        novo_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B1",
            fonte="EONET",
            latitude=-29.85,
            longitude=-56.74,
            datahoracriacao="2026-08-12T10:00:00+00:00",
        )

        resultados = db_module.avaliar_candidatos_correlacao(
            novo_id, "2026-08-12T10:00:00+00:00"
        )

        assert resultados[0].incidente_id == incidente_id


# ----------------------------------------------------------------------
# Ciclo de vida de Incidente (issue #61) — helpers de leitura que a
# integração usa para decidir reativação/resolução: buscar_incidente_atual
# (segue o redirect de fusão), status_incidente, todos_membros_resolvidos
# (árvore de fusão, não só o incidente_id passado).
# ----------------------------------------------------------------------

def _marcar_resolvido(db_path: Path, alerta_id: int) -> None:
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.execute(
            "UPDATE alertas SET status_interno = 'RESOLVIDO' WHERE id = ?",
            (alerta_id,),
        )
        conexao.commit()


class TestBuscarAlertasOrfaos:
    """Issue #87 — varredura de reconciliação: alertas `ATIVO` da fonte sem
    linha em `incidente_membros` (mecanismo compensatório do invariante 4,
    ver wiki/decisions/incident-boundary-reconciliation-sweep.md)."""

    def test_alerta_sem_membership_eh_orfao(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        assert db_module.buscar_alertas_orfaos(FonteDado.CEMADEN) == [alerta_id]

    def test_alerta_com_membership_nao_eh_orfao(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        db_module.criar_incidente(alerta_id, 1.0, "fundador", "2026-08-12T00:00:00")
        assert db_module.buscar_alertas_orfaos(FonteDado.CEMADEN) == []

    def test_alerta_resolvido_sem_membership_nao_conta(self, db_temporario):
        """Órfão que já transitou para RESOLVIDO fica fora do escopo —
        mesma severidade branda que um alerta pré-#61 nunca correlacionado
        (wiki/decisions/incident-lifecycle-wiring.md)."""
        alerta_id = _inserir_alerta(db_temporario, "A1")
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            conexao.execute(
                "UPDATE alertas SET status_interno = 'RESOLVIDO' WHERE id = ?",
                (alerta_id,),
            )
            conexao.commit()
        assert db_module.buscar_alertas_orfaos(FonteDado.CEMADEN) == []

    def test_filtra_por_fonte(self, db_temporario):
        alerta_cemaden = _inserir_alerta(db_temporario, "A1")
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            conexao.execute(
                "INSERT INTO alertas (fonte, cod_alerta, latitude, longitude, detectado_em) "
                "VALUES ('EONET', 'B1', -10.0, -40.0, '2026-08-12T00:00:00')"
            )
            conexao.commit()
        assert db_module.buscar_alertas_orfaos(FonteDado.CEMADEN) == [alerta_cemaden]


class TestBuscarIncidenteAtual:
    def test_alerta_nunca_correlacionado_retorna_none(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        assert db_module.buscar_incidente_atual(alerta_id) is None

    def test_alerta_membro_direto_retorna_seu_incidente(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            alerta_id, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        assert db_module.buscar_incidente_atual(alerta_id) == incidente_id

    def test_segue_redirect_de_fusao_ate_o_sobrevivente(self, db_temporario):
        alerta_sobrevivente = _inserir_alerta(db_temporario, "A1")
        sobrevivente_id = db_module.criar_incidente(
            alerta_sobrevivente, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        alerta_fundido = _inserir_alerta(db_temporario, "A2")
        fundido_id = db_module.criar_incidente(
            alerta_fundido, 1.0, "fundador", "2026-08-12T00:00:01"
        )
        disparador_id = _inserir_alerta(db_temporario, "A3")
        db_module.fundir_incidentes(
            sobrevivente_id, fundido_id, disparador_id, "2026-08-12T00:30:00"
        )

        # O membro do incidente FUNDIDO (não do sobrevivente) deve resolver
        # para o id do sobrevivente através do redirect.
        assert db_module.buscar_incidente_atual(alerta_fundido) == sobrevivente_id


class TestStatusIncidente:
    def test_retorna_status_atual(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            alerta_id, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        assert db_module.status_incidente(incidente_id) == "ATIVO"

        db_module.resolver_incidente(incidente_id, alerta_id, "2026-08-12T01:00:00")
        assert db_module.status_incidente(incidente_id) == "RESOLVIDO"

    def test_incidente_inexistente_levanta(self, db_temporario):
        with pytest.raises(ValueError):
            db_module.status_incidente(99999)


class TestTodosMembrosResolvidos:
    def test_incidente_de_membro_unico_nao_resolvido(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            alerta_id, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        assert db_module.todos_membros_resolvidos(incidente_id) is False

    def test_incidente_de_membro_unico_resolvido(self, db_temporario):
        alerta_id = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            alerta_id, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        _marcar_resolvido(db_temporario, alerta_id)
        assert db_module.todos_membros_resolvidos(incidente_id) is True

    def test_um_membro_nao_resolvido_impede_resolucao(self, db_temporario):
        alerta_a = _inserir_alerta(db_temporario, "A1")
        incidente_id = db_module.criar_incidente(
            alerta_a, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        alerta_b = _inserir_alerta(db_temporario, "A2")
        db_module.adicionar_membro_incidente(
            incidente_id, alerta_b, 0.9, "vincula", "2026-08-12T00:10:00"
        )
        _marcar_resolvido(db_temporario, alerta_a)
        # alerta_b ainda ATIVO
        assert db_module.todos_membros_resolvidos(incidente_id) is False

        _marcar_resolvido(db_temporario, alerta_b)
        assert db_module.todos_membros_resolvidos(incidente_id) is True

    def test_conta_membros_herdados_por_fusao(self, db_temporario):
        """Membros do Incidente FUNDIDO continuam com incidente_id apontando
        para ele (redirect append-only, nunca realocação) — checar apenas o
        sobrevivente ignoraria esses membros herdados."""
        alerta_sobrevivente = _inserir_alerta(db_temporario, "A1")
        sobrevivente_id = db_module.criar_incidente(
            alerta_sobrevivente, 1.0, "fundador", "2026-08-12T00:00:00"
        )
        alerta_fundido = _inserir_alerta(db_temporario, "A2")
        fundido_id = db_module.criar_incidente(
            alerta_fundido, 1.0, "fundador", "2026-08-12T00:00:01"
        )
        disparador_id = _inserir_alerta(db_temporario, "A3")
        db_module.fundir_incidentes(
            sobrevivente_id, fundido_id, disparador_id, "2026-08-12T00:30:00"
        )
        db_module.adicionar_membro_incidente(
            sobrevivente_id, disparador_id, 0.9, "vincula", "2026-08-12T00:30:00"
        )

        _marcar_resolvido(db_temporario, alerta_sobrevivente)
        _marcar_resolvido(db_temporario, disparador_id)
        # alerta_fundido (herdado via fusão) ainda ATIVO — não deve resolver.
        assert db_module.todos_membros_resolvidos(sobrevivente_id) is False

        _marcar_resolvido(db_temporario, alerta_fundido)
        assert db_module.todos_membros_resolvidos(sobrevivente_id) is True


class TestAplicarResultadoDeteccaoRetornaIds:
    def test_retorna_alerta_id_para_criado_e_reativado(self, db_temporario):
        from alertavida.domain.alerta import Alerta
        from alertavida.domain.coordenadas import Coordenadas
        from alertavida.domain.detector import (
            EventoDetectado,
            ResultadoDeteccao,
            TipoEventoDetectado,
        )
        from alertavida.domain.enums import FonteDado, NivelRisco

        alerta = Alerta(
            cod_alerta="A1",
            fonte=FonteDado.CEMADEN,
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
            data_criacao=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        resultado = ResultadoDeteccao(
            eventos=[
                EventoDetectado(
                    tipo=TipoEventoDetectado.CRIADO,
                    cod_alerta="A1",
                    fonte=FonteDado.CEMADEN,
                    payload={},
                )
            ],
            codigos_vistos={"A1"},
            codigos_ausentes=set(),
            fonte_por_codigo={"A1": FonteDado.CEMADEN},
        )

        ids = db_module.aplicar_resultado_deteccao(
            resultado, {"A1": alerta}, "2026-08-12T00:00:00"
        )

        assert set(ids.keys()) == {"A1"}
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            alerta_id_real = conexao.execute(
                "SELECT id FROM alertas WHERE cod_alerta = 'A1'"
            ).fetchone()[0]
        assert ids["A1"] == alerta_id_real


# ----------------------------------------------------------------------
# Issue #127 — migration única do fuso do CEMADEN, protegida por user_version
# ----------------------------------------------------------------------


def _user_version(db_path: Path) -> int:
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        return conexao.execute("PRAGMA user_version").fetchone()[0]


def _tempos_de(db_path: Path, cod_alerta: str) -> tuple[str | None, str | None]:
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        return conexao.execute(
            "SELECT datahoracriacao, ult_atualizacao FROM alertas WHERE cod_alerta = ?",
            (cod_alerta,),
        ).fetchone()


def _banco_pre_127(
    db_path: Path, linhas: list[tuple[str, str, str | None, str | None]]
) -> None:
    """Deixa um banco no estado anterior à #127: schema atual, linhas com os
    timestamps como o código antigo gravava, `user_version = 0`.

    Cada linha: (fonte, cod_alerta, datahoracriacao, ult_atualizacao).
    """
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.executemany(
            """
            INSERT INTO alertas (
                fonte, cod_alerta, latitude, longitude, detectado_em,
                datahoracriacao, ult_atualizacao
            ) VALUES (?, ?, -10.0, -40.0, '2026-11-13T21:00:00+00:00', ?, ?)
            """,
            linhas,
        )
        conexao.execute("PRAGMA user_version = 0")
        conexao.commit()


def _como_o_codigo_antigo_gravava(bruto: str) -> str:
    """Pré-#127: string sem offset do painel lida como UTC."""
    return datetime.fromisoformat(bruto).replace(tzinfo=timezone.utc).isoformat()


class TestMigracaoFusoCemaden:
    def test_banco_novo_ja_nasce_na_versao_1(self, db_temporario):
        assert _user_version(db_temporario) == 1

    def test_desloca_3h_so_as_linhas_do_cemaden(self, db_temporario):
        _banco_pre_127(
            db_temporario,
            [
                (
                    "CEMADEN",
                    "3423",
                    "2026-11-13T17:31:22.137000+00:00",
                    "2026-11-13T22:05:00+00:00",
                ),
                (
                    "EONET",
                    "EONET_1",
                    "2026-11-13T17:31:22+00:00",
                    "2026-11-13T22:05:00+00:00",
                ),
            ],
        )

        db_module.criar_banco()

        assert _tempos_de(db_temporario, "3423") == (
            "2026-11-13T20:31:22.137000+00:00",
            "2026-11-14T01:05:00+00:00",  # cruza a meia-noite
        )
        assert _tempos_de(db_temporario, "EONET_1") == (
            "2026-11-13T17:31:22+00:00",
            "2026-11-13T22:05:00+00:00",
        )
        assert _user_version(db_temporario) == 1

    def test_roda_uma_unica_vez(self, db_temporario):
        _banco_pre_127(
            db_temporario,
            [("CEMADEN", "1", "2026-11-13T17:00:00+00:00", "2026-11-13T17:00:00+00:00")],
        )

        db_module.criar_banco()
        db_module.criar_banco()
        db_module.criar_banco()

        assert _tempos_de(db_temporario, "1") == (
            "2026-11-13T20:00:00+00:00",
            "2026-11-13T20:00:00+00:00",
        )

    def test_preserva_timestamp_nulo(self, db_temporario):
        _banco_pre_127(
            db_temporario, [("CEMADEN", "1", "2026-11-13T17:00:00+00:00", None)]
        )

        db_module.criar_banco()

        assert _tempos_de(db_temporario, "1") == ("2026-11-13T20:00:00+00:00", None)

    @pytest.mark.parametrize(
        "bruto",
        [
            "2026-11-13 17:31:22.137",  # formato real do painel
            "2026-11-13 22:05:00.000",  # fração zerada + cruza a meia-noite
            "2026-04-09T07:08:15",
        ],
    )
    def test_valor_migrado_e_identico_ao_do_parser_corrigido(self, db_temporario, bruto):
        """O detector compara `ult_atualizacao` como STRING contra o snapshot.
        Se a migration e o parser divergissem em um caractere, a primeira
        rodada pós-deploy emitiria AlertaAtualizado espúrio para todo alerta
        ATIVO do CEMADEN."""
        antigo = _como_o_codigo_antigo_gravava(bruto)
        _banco_pre_127(db_temporario, [("CEMADEN", "1", antigo, antigo)])

        db_module.criar_banco()

        alerta = CemadenSource()._montar_alerta(
            {
                "cod_alerta": "1",
                "evento": "Risco Hidrológico - Moderado",
                "nivel": "Moderado",
                "datahoracriacao": bruto,
                "ult_atualizacao": bruto,
                "latitude": -10.0,
                "longitude": -40.0,
            }
        )
        assert alerta.ult_atualizacao is not None
        assert _tempos_de(db_temporario, "1") == (
            alerta.data_criacao.isoformat(),
            alerta.ult_atualizacao.isoformat(),
        )

    def test_falha_no_meio_nao_deixa_migration_pela_metade(self, db_temporario, monkeypatch):
        """Linhas deslocadas com `user_version` ainda em 0 fariam a próxima
        inicialização somar outras 3h. UPDATEs e bump de versão têm de cair
        no mesmo commit — ou em nenhum."""
        _banco_pre_127(
            db_temporario,
            [
                ("CEMADEN", "1", "2026-11-13T17:00:00+00:00", "2026-11-13T17:00:00+00:00"),
                ("CEMADEN", "2", "2026-11-13T18:00:00+00:00", "2026-11-13T18:00:00+00:00"),
            ],
        )
        original = db_module._deslocar_iso
        chamadas = 0

        def _falha_na_segunda_linha(valor, delta):
            nonlocal chamadas
            chamadas += 1
            if chamadas > 2:  # 2 colunas por linha: estoura na 2ª linha
                raise RuntimeError("falha simulada no meio da migration")
            return original(valor, delta)

        monkeypatch.setattr(db_module, "_deslocar_iso", _falha_na_segunda_linha)
        with pytest.raises(RuntimeError, match="falha simulada"):
            db_module.criar_banco()

        assert _user_version(db_temporario) == 0
        assert _tempos_de(db_temporario, "1") == (
            "2026-11-13T17:00:00+00:00",
            "2026-11-13T17:00:00+00:00",
        )

        monkeypatch.setattr(db_module, "_deslocar_iso", original)
        db_module.criar_banco()

        assert _user_version(db_temporario) == 1
        assert _tempos_de(db_temporario, "1")[0] == "2026-11-13T20:00:00+00:00"
        assert _tempos_de(db_temporario, "2")[0] == "2026-11-13T21:00:00+00:00"


# ----------------------------------------------------------------------
# Issue #129 — portão de município, ponta a ponta pelo banco
# ----------------------------------------------------------------------


class TestPortaoDeMunicipio:
    def test_mesma_chuva_em_municipios_vizinhos_vira_dois_incidentes(self, db_temporario):
        """Dois alertas CEMADEN a ~1 km, mesmo instante, mesmo subgrupo —
        antes da #129 vinculariam. Com códigos IBGE diferentes, o segundo
        abre o próprio Incidente e a observação registra o motivo."""
        agora = "2026-11-16T10:00:00+00:00"
        a_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="A",
            codibge=3550308,
            latitude=-23.55,
            longitude=-46.63,
            datahoracriacao=agora,
        )
        incidente_a = db_module.criar_incidente(a_id, 1.0, "fundador", agora)
        b_id = _inserir_alerta_correlacao(
            db_temporario,
            cod_alerta="B",
            codibge=3548708,
            latitude=-23.56,
            longitude=-46.63,
            datahoracriacao=agora,
        )

        resultados = db_module.avaliar_candidatos_correlacao(b_id, agora)

        assert [r.incidente_id for r in resultados] == [incidente_a]
        assert resultados[0].decisao.resultado.value == "NAO_VINCULA"
        assert resultados[0].decisao.motivo == "municipios_diferentes"
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            observacao = conexao.execute(
                "SELECT mesmo_codibge, decisao, motivo FROM correlacao_observacoes"
            ).fetchone()
        assert observacao == (0, "NAO_VINCULA", "municipios_diferentes")


# ----------------------------------------------------------------------
# Guarda de compatibilidade (#130): só bancos a partir de 2026-08-13
# ----------------------------------------------------------------------

_DDL_ALERTAS_PRE_A1 = """
    CREATE TABLE alertas (
        cod_alerta TEXT PRIMARY KEY, latitude REAL, longitude REAL, detectado_em TEXT
    )
"""
_DDL_ALERTAS_PRE_A2 = """
    CREATE TABLE alertas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fonte TEXT NOT NULL, cod_alerta TEXT NOT NULL,
        latitude REAL NOT NULL, longitude REAL NOT NULL, detectado_em TEXT NOT NULL,
        UNIQUE (fonte, cod_alerta)
    )
"""
_DDL_EVENTOS_SEM_FK = """
    CREATE TABLE eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, agregado_id INTEGER NOT NULL,
        agregado_incidente_id INTEGER NULL, payload TEXT NOT NULL, criado_em TEXT NOT NULL
    )
"""


def _banco_com(db_path: Path, *ddls: str, user_version: int = 0) -> None:
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        for ddl in ddls:
            conexao.execute(ddl)
        conexao.execute(f"PRAGMA user_version = {user_version}")
        conexao.commit()


def _banco_atual_sem(db_path: Path, monkeypatch, *, coluna_eventos: str) -> None:
    """Banco com o schema atual, depois rebaixado: `eventos` recriada sem a
    coluna dada e `user_version` de volta a 0 — a forma de um banco pré-#59."""
    _patch_db_path(monkeypatch, db_path)
    db_module.criar_banco()
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        conexao.execute("DROP TABLE eventos")
        conexao.execute(
            "CREATE TABLE eventos (id INTEGER PRIMARY KEY, tipo TEXT, agregado_id INTEGER, "
            "payload TEXT, criado_em TEXT, FOREIGN KEY (agregado_id) REFERENCES alertas(id))"
        )
        conexao.execute("PRAGMA user_version = 0")
        conexao.commit()
    assert coluna_eventos not in _colunas_de(db_path, "eventos")


class TestGuardaDeCompatibilidade:
    def test_banco_novo_passa(self, tmp_path, monkeypatch):
        db_path = tmp_path / "novo.db"
        _patch_db_path(monkeypatch, db_path)
        db_module.criar_banco()
        assert db_path.exists()

    def test_banco_pre_a1_e_recusado_listando_as_colunas(self, tmp_path, monkeypatch):
        db_path = tmp_path / "pre_a1.db"
        _banco_com(db_path, _DDL_ALERTAS_PRE_A1)
        _patch_db_path(monkeypatch, db_path)
        with pytest.raises(SchemaIncompativelError) as exc_info:
            db_module.criar_banco()
        msg = str(exc_info.value)
        for coluna in ("id", "fonte", "cobrade_codigo", "fonte_classificacao", "descricao"):
            assert coluna in msg

    def test_banco_pre_a2_e_recusado_sem_ser_alterado(self, tmp_path, monkeypatch):
        """Antes da #130 este banco recebia as colunas A.2 por ALTER TABLE.
        Agora é recusado — e a recusa acontece antes de qualquer ALTER."""
        db_path = tmp_path / "pre_a2.db"
        _banco_com(db_path, _DDL_ALERTAS_PRE_A2)
        _patch_db_path(monkeypatch, db_path)
        with pytest.raises(SchemaIncompativelError, match="cobrade_codigo"):
            db_module.criar_banco()
        assert "cobrade_codigo" not in _colunas_de(db_path, "alertas")

    def test_eventos_sem_fk_e_recusado(self, tmp_path, monkeypatch):
        db_path = tmp_path / "eventos_sem_fk.db"
        _patch_db_path(monkeypatch, db_path)
        db_module.criar_banco()
        with contextlib.closing(sqlite3.connect(db_path)) as conexao:
            conexao.execute("DROP TABLE eventos")
            conexao.execute(_DDL_EVENTOS_SEM_FK)
            conexao.execute("PRAGMA user_version = 0")
            conexao.commit()
        with pytest.raises(SchemaIncompativelError, match="FOREIGN KEY"):
            db_module.criar_banco()

    def test_eventos_pre_59_e_recusado(self, tmp_path, monkeypatch):
        db_path = tmp_path / "pre_59.db"
        _banco_atual_sem(db_path, monkeypatch, coluna_eventos="agregado_incidente_id")
        with pytest.raises(SchemaIncompativelError, match="agregado_incidente_id"):
            db_module.criar_banco()

    def test_user_version_1_dispensa_a_inspecao(self, tmp_path, monkeypatch):
        """Com `user_version >= 1` o banco é pós-#127 por construção."""
        db_path = tmp_path / "v1.db"
        _patch_db_path(monkeypatch, db_path)
        db_module.criar_banco()
        assert _user_version(db_path) == 1
        db_module.criar_banco()  # não levanta


class TestMigracao89:
    """O único passo de schema que sobrou: o snapshot de 2026-09-05 ainda
    tem os dois índices que a #89 removeu."""

    def test_remove_idx_fonte_e_idx_escopo_geografico(self, db_temporario):
        with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
            conexao.execute("CREATE INDEX idx_fonte ON alertas (fonte)")
            conexao.execute("CREATE INDEX idx_escopo_geografico ON alertas (escopo_geografico)")
            conexao.commit()
        assert {"idx_fonte", "idx_escopo_geografico"} <= _indices_de(db_temporario, "alertas")

        db_module.criar_banco()

        assert not {"idx_fonte", "idx_escopo_geografico"} & _indices_de(db_temporario, "alertas")
