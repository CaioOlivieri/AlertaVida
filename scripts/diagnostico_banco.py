"""Diagnóstico do banco local: qual versão do schema rodou aqui?"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "alertavida.db"

if not DB_PATH.exists():
    print(f"Banco não existe em {DB_PATH}")
    print("Veredito: banco LIMPO. Não há histórico para preservar.")
    raise SystemExit(0)

conn = sqlite3.connect(DB_PATH)

# 1. Tabelas presentes
tabelas = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]
print(f"Tabelas: {tabelas}\n")

# 2. Schema da tabela alertas
if "alertas" in tabelas:
    print("=== Schema atual de `alertas` ===")
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='alertas'"
    ).fetchone()[0]
    print(schema)
    print()

    # 3. Colunas presentes (via PRAGMA — mais robusto que parsear SQL)
    cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(alertas)").fetchall()}
    print(f"Colunas: {sorted(cols.keys())}\n")

    # 4. Contagem
    n = conn.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
    print(f"Linhas em `alertas`: {n}")

    # 5. Diagnóstico de versão
    print("\n=== Diagnóstico de versão ===")
    if "id" in cols and "fonte" in cols and "cobrade_codigo" in cols:
        print("✓ Schema PÓS-A.2 (estado atual do código)")
    elif "id" in cols and "fonte" in cols and "cobrade_codigo" not in cols:
        print("⚠ Schema PÓS-A.1, PRÉ-A.2 — banco rodou A.1 mas não foi migrado para A.2")
    elif "fonte" not in cols and "cod_alerta" in cols:
        print("⚠ Schema PRÉ-A.1 — banco está em versão antiga (Camada 2 ou 3)")
        if "status_interno" in cols:
            print("  → Tem colunas da Camada 3 (status_interno). Rodou Camada 3 mas não A.1.")
        else:
            print("  → Não tem colunas da Camada 3. Banco veio da Camada 2 ou anterior.")
    else:
        print("? Schema não reconhecido — investigar manualmente")

if "eventos" in tabelas:
    n_eventos = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    print(f"\nLinhas em `eventos`: {n_eventos}")

conn.close()