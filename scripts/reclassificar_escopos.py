"""Re-classifica `escopo_geografico` de alertas existentes.

Uso:
    uv run python -m scripts.reclassificar_escopos

Quando rodar:
- Após mudança nos buffers de `geographic.py` (ex: alterar
  ALERTAVIDA_BUFFER_PROXIMO_GRAUS).
- Quando bbox do BRASIL for ajustado (mudança de constante em geographic.py).

O que faz:
- Lê todos os alertas do banco.
- Recalcula escopo_geografico via classificar_escopo() usando coordenadas
  persistidas.
- Atualiza apenas registros onde o valor mudou.
- Imprime resumo (total, alterados, inalterados).

NÃO altera nada além da coluna `escopo_geografico`.
"""

from __future__ import annotations

import sqlite3
import sys

from alertavida.database import DB_PATH
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.geographic import classificar_escopo


def reclassificar() -> int:
    if not DB_PATH.exists():
        print(f"Banco não existe em {DB_PATH}. Nada a fazer.")
        return 0

    total = 0
    alterados = 0
    inalterados = 0

    with sqlite3.connect(DB_PATH) as conexao:
        cursor = conexao.execute(
            "SELECT id, latitude, longitude, escopo_geografico FROM alertas"
        )
        rows = cursor.fetchall()

        for row in rows:
            id_, latitude, longitude, escopo_atual = row
            total += 1

            try:
                coord = Coordenadas(latitude=latitude, longitude=longitude)
            except (TypeError, ValueError):
                inalterados += 1
                continue

            escopo_novo = classificar_escopo(coord).value

            if escopo_novo != escopo_atual:
                conexao.execute(
                    "UPDATE alertas SET escopo_geografico = ? WHERE id = ?",
                    (escopo_novo, id_),
                )
                alterados += 1
            else:
                inalterados += 1

        conexao.commit()

    print()
    print("=== Reclassificação de escopo geográfico ===")
    print(f"Total inspecionados : {total}")
    print(f"Alterados           : {alterados}")
    print(f"Inalterados         : {inalterados}")
    return 0


if __name__ == "__main__":
    sys.exit(reclassificar())
