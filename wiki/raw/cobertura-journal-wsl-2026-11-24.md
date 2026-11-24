# Cobertura da coleta no WSL, extraída do journal — 2026-11-24

Relatório bruto do primeiro passo da issue #158. O banco não registra rodadas
(só `visto_ultima_vez` por alerta), então a única prova de quando o coletor
estava ligado no PC é o journal do WSL. Ele foi extraído antes da
desativação do PC (#141), porque rotação ou limpeza o apagariam.

## Como foi extraído

```
journalctl -u alertavida.service -o short-iso --no-pager \
    | uv run python -m scripts.extrair_rodadas_journal \
        --saida wiki/raw/rodadas-journal-wsl-2026-09-28-a-2026-11-22.csv
```

Uma rodada = um bloco `<agora>: rodada concluída` de `formatar_relatorio()`;
o instante é o `agora` do cabeçalho (UTC, escrito pelo orquestrador). Uma
linha do CSV por (rodada, fonte): `instante_utc`, `fonte`, `coletados` (vazio
quando a fonte falhou), `falha`. Só carimbos e contagens — nenhum nome de
máquina. Rodado em 2026-11-24 no PC; journal com 904 MB nessa data.

## Saída do script

```
rodadas de alertas: 2462 (2026-09-28T23:49Z → 2026-11-22T16:22Z)
  2026-09: 5
  2026-10: 1042
  2026-11: 1415
```

Conferência contra `grep` bruto no mesmo journal: 2.462 linhas
`rodada concluída`; CEMADEN 2.426 coletas + 36 falhas; EONET 2.397 + 65 —
idêntico ao CSV (4.924 linhas, 2.462 instantes distintos).

## Cobertura

- **2.462 de 15.752 rodadas possíveis = 15,6 %** entre a primeira e a última
  rodada (uma a cada 5 min).
- 56 dias no período; 51 com alguma coleta; **34 com menos de 5 h**; só 3
  com metade do dia ou mais.
- Maiores lacunas: 3 d 18 h 57 min, 2 d 10 h 12 min, 1 d 22 h 37 min.
- Até 2026-11-13: 1.542 rodadas — a #134 contou 1.535 no mesmo dia, com o
  journal lido mais cedo. Mesmo método.

## O que não existe mais

- **Nada antes de 2026-09-28T23:49Z.** O banco tem alertas desde 2026-08-13;
  a cobertura de 13/08 a 28/09 é desconhecida e não pode ser reconstruída.
- A partir de 2026-11-22 o coletor roda na VM; a cobertura de lá é extraída
  do journal da VM até a tabela `rodadas` entrar em produção (#158).
