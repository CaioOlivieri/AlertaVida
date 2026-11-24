# Análise: avisos do INMET que somem antes do fim — 2026-11-24

Relatório bruto da questão aberta da #153: um aviso sai da lista de ativos
(`avisos/ativos`, JSON) antes do `fim`, sem vir marcado como encerrado. Medido
numa cópia `mode=ro` do banco de produção (2026-11-24T17:46Z, 16 mensagens de
aviso, 35 coletas INMET sem falha desde 2026-11-24T01:18Z) e nas mensagens CAP
públicas do INMET (`avisos/rss` e `avisos/rss/<n>`), baixadas na mesma hora.

## O que o banco mostra

- 6 avisos (28748–28753, `fim` 2026-11-24T02:59Z) vistos pela última vez às
  02:35Z — a coleta seguinte já era depois do `fim`: **expiração normal**.
- 2 avisos sumiram com a validade em curso, ambos na coleta de
  **2026-11-24T12:35Z**:
  - 28754 (Tempestade, Perigo Potencial, até 2026-11-25T02:59Z, 3.476
    municípios);
  - 28758 (Tempestade, Perigo Potencial, 2026-11-25T03:00Z → 2026-11-26T02:59Z,
    2.978 municípios).
- Na mesma coleta apareceram **28759** (Tempestade, Perigo Potencial,
  2026-11-24T12:06Z → 2026-11-25T02:59Z, 3.501 municípios) e **28760**
  (mesmo evento e janela de 28758, 3.111 municípios): substitutos com **outro
  `id_aviso`**, não uma nova sequência do mesmo aviso.

## O que o CAP do INMET diz

Os 25 itens mais recentes do RSS (links `rss/56473` a `rss/56504`), um CAP
cada:

```
id_aviso seq  msgType  references                         event
28738    2    Cancel   …2026.28738.1                      Tempestade
28741    2    Update   …2026.28741.1                      Tempestade
28743    2    Cancel   …2026.28743.1                      Tempestade
28746    2    Update   …2026.28746.1                      Baixa Umidade
28747    2    Cancel   …2026.28747.1                      Tempestade
28751    2    Cancel   …2026.28751.1                      Chuvas Intensas
28754    2    Cancel   …2026.28754.1                      Tempestade
28755    2    Cancel   …2026.28755.1                      Tempestade
28758    2    Cancel   …2026.28758.1                      Tempestade
(demais: seq 1, msgType Alert)
```

- **Todo aviso que sumiu antes do `fim` tem uma mensagem oficial `Cancel`**
  (28754, 28758 e o 28743, caso original da #153). O cancelamento **nunca
  aparece no JSON de ativos** — o aviso só some.
- `Update` aparece no JSON como nova sequência (28746.2 está no banco).
- O `sent` das mensagens `Cancel` traz só a data (`2026-11-23T00:00:00-03:00`),
  não a hora: o instante do cancelamento não vem do CAP; a melhor medida é a
  primeira coleta que já não viu o aviso.
- No RSS, o item do cancelamento aparece como "Status Alert"; só o CAP de cada
  item diz `Cancel`.

## Efeito no acervo

Regra atual (`consultar_avisos_vigentes`): vale até o `fim` se não
`encerrado`. Resultado na cópia:

- 59 anotações (alerta, aviso); **9 usam um aviso já cancelado** no início do
  alerta — **todos os 9 alertas CEMADEN criados desde 12:35Z** (3619–3627),
  sempre com 28754 (cancelado) **e** 28759 (o substituto) na mesma anotação.
- 15 % das anotações erradas em ~5 h; cresce a cada cancelamento.
