# Cobertura da coleta na VM, extraída do journal — 2026-11-24

Relatório bruto da issue #158, complemento de
[[raw/cobertura-journal-wsl-2026-11-24]]. Cobre da primeira rodada na VM
(cutover, 2026-11-22) até a última rodada antes da tabela `rodadas` entrar em
produção (deploy de `389119b`, 2026-11-24T01:18:55Z). A partir daí a
cobertura está no banco.

## Como foi extraído

```
ssh <vm> 'sudo journalctl -u alertavida.service -o short-iso --no-pager \
    --until "2026-11-24 01:18:55 UTC"' > vm-journal.txt
uv run python -m scripts.extrair_rodadas_journal --entrada vm-journal.txt \
    --saida wiki/raw/rodadas-journal-vm-2026-11-22-a-2026-11-24.csv
```

O `--until` corta antes do carimbo da primeira rodada do código novo
(cabeçalho `2026-11-24T01:18:55.671343+00:00`, journal 01:18:56), que é a
primeira linha de `rodadas` — conferida numa cópia `mode=ro` do banco da VM.
Sem lacuna e sem sobreposição.

## Saída do script

```
rodadas de alertas: 397 (2026-11-22T16:23Z → 2026-11-24T01:16Z)
  2026-11: 397
```

Conferência contra `grep` no mesmo texto: 397 cabeçalhos; CEMADEN 397 + 0
falhas; EONET 395 + 2 falhas; INMET 24 coletas — idêntico ao CSV (818 linhas).
A primeira rodada (16:23:41Z) vem um minuto depois da última do WSL
(16:22Z): o cutover.

## Cobertura — e por que o método da #134 não serve mais

- `rodadas ÷ possíveis` (método da #134) dá **397 / 396 = 100,4 %**: todo
  restart dispara uma rodada imediata, fora da grade de 5 min, e cada deploy
  ou reboot soma uma. No WSL isso quase não aparecia (15,6 %).
- **Janelas de 5 min com ao menos uma rodada: 392 / 395 = 99,2 %.** É a
  medida certa para "o coletor estava ligado". As 3 janelas vazias são a
  parada proposital do teste do heartbeat (2026-11-22, 18:57:54 → 19:13:55,
  maior lacuna 18 min 10 s).
- O WSL pela mesma medida: 2.437 / 15.751 janelas = **15,5 %** (contra 15,6 %
  por contagem).

O fechamento da #141 (tempo ligado dos 7 primeiros dias) deve usar janelas,
não contagem.
