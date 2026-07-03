"""Corrige a classificação (tipo_evento/cobrade_codigo/fonte_classificacao)
de alertas CEMADEN já gravados antes do fix da issue #30.

Uso:
    uv run python -m scripts.reclassificar_cobrade_cemaden

Quando rodar:
- Uma vez, logo após o deploy do fix da issue #30.
- De novo só se um bug equivalente for reintroduzido.

Por que precisa buscar a API ao vivo (não é um recompute offline):
A string bruta do CEMADEN (`evento`, ex.: "Risco Hidrológico - Moderado")
nunca foi persistida — `alertas.evento` guarda o valor do enum de domínio
já resolvido (e, antes do fix, sempre errado: "INDETERMINADO"). Sem o dado
bruto não há como recalcular a classificação a partir do banco sozinho.
Este script busca o feed atual do CEMADEN, casa por `cod_alerta` com as
linhas já gravadas, e recalcula a classificação a partir do item ao vivo.

Alcance: só corrige alertas CEMADEN que AINDA estão no feed no momento em
que o script roda. Alertas já resolvidos/fora do feed não são alcançáveis
— o dado bruto deles se perdeu e não há caminho de recuperação.

O que faz:
- Busca o feed CEMADEN ao vivo via CemadenSource().coletar() (já usa o
  fix da issue #30 internamente).
- Para cada alerta retornado, procura a linha correspondente em `alertas`
  (fonte='CEMADEN', cod_alerta=...).
- Se encontrada e a classificação mudou, faz UPDATE de `evento`,
  `cobrade_codigo`, `fonte_classificacao` — ignorando de propósito o gate
  normal de `ult_atualizacao` (não é uma detecção de mudança de negócio,
  é uma correção de dado histórico).
- NÃO cria linhas novas, NÃO emite eventos na outbox, NÃO altera nenhuma
  outra coluna (municipio, uf, coordenadas, nivel, status_interno, etc.).
- Imprime resumo (total no feed, casados no banco, alterados, inalterados,
  não encontrados no banco).
"""

from __future__ import annotations

import sys

from alertavida.database import DB_PATH, conectar
from alertavida.domain.enums import FonteDado
from alertavida.sources import FalhaDeColeta
from alertavida.sources.cemaden import CemadenSource


def reclassificar() -> int:
    if not DB_PATH.exists():
        print(f"Banco não existe em {DB_PATH}. Nada a fazer.")
        return 0

    print(f"Buscando feed ao vivo do CEMADEN ({DB_PATH})...")
    try:
        resultado = CemadenSource().coletar()
    except FalhaDeColeta as exc:
        print(f"Falha ao buscar feed do CEMADEN: {exc.causa}")
        return 1

    total_feed = len(resultado.alertas)
    casados = 0
    alterados = 0
    inalterados = 0
    nao_encontrados = 0

    with conectar() as conexao:
        for alerta in resultado.alertas:
            row = conexao.execute(
                """
                SELECT evento, cobrade_codigo, fonte_classificacao
                FROM alertas
                WHERE fonte = ? AND cod_alerta = ?
                """,
                (FonteDado.CEMADEN.value, alerta.cod_alerta),
            ).fetchone()

            if row is None:
                nao_encontrados += 1
                continue

            casados += 1
            evento_atual, cobrade_atual, fonte_classificacao_atual = row
            mudou = (
                evento_atual != alerta.tipo_evento.value
                or cobrade_atual != alerta.cobrade_codigo
                or fonte_classificacao_atual != alerta.fonte_classificacao.value
            )

            if mudou:
                conexao.execute(
                    """
                    UPDATE alertas
                    SET evento = ?, cobrade_codigo = ?, fonte_classificacao = ?
                    WHERE fonte = ? AND cod_alerta = ?
                    """,
                    (
                        alerta.tipo_evento.value,
                        alerta.cobrade_codigo,
                        alerta.fonte_classificacao.value,
                        FonteDado.CEMADEN.value,
                        alerta.cod_alerta,
                    ),
                )
                alterados += 1
            else:
                inalterados += 1

        conexao.commit()

    print()
    print("=== Reclassificação COBRADE/tipo_evento (CEMADEN, issue #30) ===")
    print(f"Total no feed ao vivo   : {total_feed}")
    print(f"Casados no banco        : {casados}")
    print(f"Alterados               : {alterados}")
    print(f"Inalterados             : {inalterados}")
    print(f"Não encontrados no banco: {nao_encontrados}")
    if nao_encontrados:
        print(
            "(esperado: alertas novos que ainda não passaram por uma "
            "rodada de ingestão normal)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(reclassificar())
