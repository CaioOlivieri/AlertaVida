"""Testes diretos de src/alertavida/database.py.

Cobre:
- Verificação de compatibilidade de schema (_verificar_compatibilidade_schema)
- Migration aditiva (_migrar_banco) sobre schemas legados que SÃO compatíveis
- Criação do schema atual via criar_banco() em banco vazio
- Idempotência: criar_banco() rodado N vezes não altera schema nem dados
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from alertavida import database as db_module
from alertavida.database import SchemaIncompativelError
from tests.fixtures.schemas_legados import (
    aplicar_schema_pos_a1_pre_a2,
    aplicar_schema_pos_camada_3,
    aplicar_schema_pre_camada_3,
)

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _colunas_de(db_path: Path, tabela: str) -> set[str]:
    """Retorna o conjunto de nomes de coluna de uma tabela."""
    with sqlite3.connect(db_path) as conexao:
        cursor = conexao.execute(f"PRAGMA table_info({tabela})")
        return {row[1] for row in cursor.fetchall()}


def _patch_db_path(monkeypatch, db_path: Path) -> None:
    """Aponta DB_PATH para o caminho temporário no módulo database."""
    monkeypatch.setattr(db_module, "DB_PATH", db_path)


# ----------------------------------------------------------------------
# Verificação de compatibilidade (Caminho 3, formalizado em 12/05/2026)
# ----------------------------------------------------------------------

class TestVerificacaoCompatibilidade:
    """criar_banco() detecta schemas pré-A.1 e levanta erro explícito."""

    def test_banco_inexistente_passa(self, tmp_path, monkeypatch):
        db_path = tmp_path / "novo.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()

        assert db_path.exists()

    def test_banco_pre_camada_3_levanta(self, tmp_path, monkeypatch):
        db_path = tmp_path / "legado_c2.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pre_camada_3(conexao)
        _patch_db_path(monkeypatch, db_path)

        with pytest.raises(SchemaIncompativelError, match="id"):
            db_module.criar_banco()

    def test_banco_pos_camada_3_levanta(self, tmp_path, monkeypatch):
        db_path = tmp_path / "legado_c3.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pos_camada_3(conexao)
        _patch_db_path(monkeypatch, db_path)

        with pytest.raises(SchemaIncompativelError, match="id"):
            db_module.criar_banco()

    def test_mensagem_erro_lista_colunas_faltantes(self, tmp_path, monkeypatch):
        """Mensagem de erro deve listar as colunas que faltam, não só a primeira."""
        db_path = tmp_path / "legado.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pre_camada_3(conexao)
        _patch_db_path(monkeypatch, db_path)

        with pytest.raises(SchemaIncompativelError) as exc_info:
            db_module.criar_banco()

        msg = str(exc_info.value)
        # Schema pré-C3 não tem nem id nem fonte
        assert "id" in msg
        assert "fonte" in msg

    def test_banco_pre_a1_nao_recebe_colunas_a2_silenciosamente(
        self, tmp_path, monkeypatch
    ):
        """Regressão: _migrar_banco() NÃO deve adicionar cobrade_codigo
        / fonte_classificacao em bancos pré-A.1. A verificação tem que
        abortar antes do migrar_banco rodar.

        Sem esta proteção, um banco C3 receberia colunas A.2 e viraria
        uma quimera C3+A.2 onde queries do código atual quebram em runtime.
        """
        db_path = tmp_path / "quimera_potencial.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pos_camada_3(conexao)
        _patch_db_path(monkeypatch, db_path)

        with pytest.raises(SchemaIncompativelError):
            db_module.criar_banco()

        # Verifica que o schema NÃO foi alterado
        colunas = _colunas_de(db_path, "alertas")
        assert "cobrade_codigo" not in colunas
        assert "fonte_classificacao" not in colunas


# ----------------------------------------------------------------------
# Migration aditiva (caminho feliz: A.1 -> A.2)
# ----------------------------------------------------------------------

class TestMigrationAditiva:
    """Schemas que JÁ têm id+fonte recebem aditivos A.2 corretamente."""

    def test_schema_a1_recebe_colunas_a2(self, tmp_path, monkeypatch):
        db_path = tmp_path / "a1.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pos_a1_pre_a2(conexao)
        _patch_db_path(monkeypatch, db_path)

        # Antes: sem colunas A.2
        colunas_antes = _colunas_de(db_path, "alertas")
        assert "cobrade_codigo" not in colunas_antes
        assert "fonte_classificacao" not in colunas_antes

        # Roda criar_banco — deve passar pela verificação e aditivar
        db_module.criar_banco()

        # Depois: colunas A.2 presentes
        colunas_depois = _colunas_de(db_path, "alertas")
        assert "cobrade_codigo" in colunas_depois
        assert "fonte_classificacao" in colunas_depois

    def test_schema_a1_perde_coluna_assinatura(self, tmp_path, monkeypatch):
        """Manutenibilidade #8 B1: assinatura é removida por _migrar_banco()."""
        db_path = tmp_path / "a1_com_assinatura.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pos_a1_pre_a2(conexao)
        _patch_db_path(monkeypatch, db_path)

        colunas_antes = _colunas_de(db_path, "alertas")
        assert "assinatura" in colunas_antes

        db_module.criar_banco()

        colunas_depois = _colunas_de(db_path, "alertas")
        assert "assinatura" not in colunas_depois

    def test_migrar_banco_e_idempotente_sem_coluna_assinatura(self, tmp_path, monkeypatch):
        """Rodar criar_banco() de novo após o DROP não levanta erro (idempotência)."""
        db_path = tmp_path / "a1_ja_migrado.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pos_a1_pre_a2(conexao)
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()
        db_module.criar_banco()  # segunda rodada — não deve tentar DROP de novo

        colunas = _colunas_de(db_path, "alertas")
        assert "assinatura" not in colunas

    def test_fonte_classificacao_tem_default_correto(self, tmp_path, monkeypatch):
        """Linhas A.1 pré-existentes recebem 'INDETERMINADA' como default."""
        db_path = tmp_path / "a1_com_dados.db"
        with sqlite3.connect(db_path) as conexao:
            aplicar_schema_pos_a1_pre_a2(conexao)
            # Insere uma linha no schema A.1 (sem colunas A.2 ainda)
            conexao.execute(
                """
                INSERT INTO alertas (
                    fonte, cod_alerta, latitude, longitude, detectado_em
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("CEMADEN", "12345", -10.0, -40.0, "2026-05-09T10:00:00"),
            )
            conexao.commit()
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()  # aplica migration A.2

        with sqlite3.connect(db_path) as conexao:
            row = conexao.execute(
                "SELECT cobrade_codigo, fonte_classificacao FROM alertas WHERE cod_alerta = ?",
                ("12345",),
            ).fetchone()

        assert row[0] is None  # cobrade_codigo nullable
        assert row[1] == "INDETERMINADA"  # default A.2


# ----------------------------------------------------------------------
# Criação do schema atual + idempotência
# ----------------------------------------------------------------------

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
            "cobrade_codigo", "fonte_classificacao",
        }
        assert esperadas.issubset(colunas)

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

        with sqlite3.connect(db_temporario) as conexao:
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
            codigos_resolvidos=set(),
            fonte_por_codigo={"R1": FonteDado.CEMADEN},
        )

        aplicar_resultado_deteccao(resultado, {"R1": alerta}, "2026-06-11T11:00:00")

        with sqlite3.connect(db_temporario) as conexao:
            row = conexao.execute(
                "SELECT status_interno, rodadas_ausente, nivel, evento FROM alertas WHERE cod_alerta = 'R1'"
            ).fetchone()

        assert row[0] == "ATIVO", f"Esperado ATIVO, obtido {row[0]}"
        assert row[1] == 0, f"Esperado rodadas_ausente=0, obtido {row[1]}"
        assert row[2] == "ALTO"
        assert row[3] == "HIDROLOGICO"

        with sqlite3.connect(db_temporario) as conexao:
            count = conexao.execute(
                "SELECT COUNT(*) FROM eventos WHERE tipo = 'AlertaReativado'"
            ).fetchone()[0]
        assert count == 1


    def test_criar_banco_preserva_dados(self, tmp_path, monkeypatch):
        db_path = tmp_path / "com_dados.db"
        _patch_db_path(monkeypatch, db_path)

        db_module.criar_banco()
        with sqlite3.connect(db_path) as conexao:
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

        with sqlite3.connect(db_path) as conexao:
            n = conexao.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
        assert n == 1
