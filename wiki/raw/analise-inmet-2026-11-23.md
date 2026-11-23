# Análise: avisos meteorológicos do INMET como fonte — 2026-11-23

Relatório bruto da pesquisa que antecede a issue da fonte INMET. Tudo abaixo
veio de requisições reais feitas em 2026-11-23 (read-only), salvo onde
indicado como busca na web.

## Endpoints testados

| URL | Resultado |
|---|---|
| `https://apiprevmet3.inmet.gov.br/avisos/ativos` | 200, JSON, 283.626 B |
| `https://apiprevmet3.inmet.gov.br/avisos/rss` | 200, RSS, 130.822 B, 59 itens |
| `https://apiprevmet3.inmet.gov.br/avisos/rss/<id>` | 200, **CAP 1.2** XML (~99 KB) |
| `https://alertas2.inmet.gov.br/` (portal) | sem resposta para o cliente usado |
| `http://alert-as.inmet.gov.br/cap_12/rss/alert-as.rss` (feed citado em documentos da OMM de 2015/2018) | 302 |
| `robots.txt` em apiprevmet3 | 404 (rota inexistente) |

## Autenticidade

O identificador CAP dos avisos é `urn:oid:2.49.0.0.76.0.2026.<id_aviso>.<seq>`.
`2.49.0.0.76.0` é o OID que o Registro de Autoridades de Alerta da OMM atribui
ao INMET (Brasil, categoria Met) — busca na web:
https://alertingauthority.wmo.int/authorities.php?recId=22

## JSON `avisos/ativos`

Envelope `{"hoje": [...], "futuro": [...]}`. Em 2026-11-23: 2 + 1 avisos.
Campos de cada aviso:

```
alterado, aviso_cor, codigo, created_at, data_fim, data_inicio, descricao,
encerrado, estados, fim, geocodes, hora_fim, hora_inicio, icone, id,
id_aviso, id_condicao_severa, id_icone, id_sequencia, id_severidade,
id_usuario, inicio, instrucoes, mesorregioes, microrregioes, municipios,
poligono, referencia, regioes, riscos, severidade, updated_at
```

Medido por aviso:

```
hoje   id_aviso=28743 seq=1 Tempestade    Perigo Potencial municipios= 3059 estados=19 vertices=106
hoje   id_aviso=28746 seq=1 Baixa Umidade Perigo Potencial municipios=  589 estados=9  vertices=20
futuro id_aviso=28747 seq=1 Tempestade    Perigo Potencial municipios= 3206 estados=15 vertices=71
```

- `geocodes`: lista de **códigos IBGE** de cada município coberto (string
  separada por vírgula). `poligono`: GeoJSON `Polygon` como string.
- `icone`: PNG em base64 dentro de cada aviso — a maior parte dos 280 KB.
- **Fuso:** `data_inicio` = `"2026-11-24T00:00:00.000Z"` com `hora_inicio` =
  `"00:00"`; `inicio` = `"2026-11-24 00:00"`. O CAP do mesmo aviso diz
  `onset 2026-11-24T00:00:00-03:00`. Ou seja, o `Z` do JSON **não é UTC**: é
  horário de Brasília rotulado errado — a mesma armadilha da #127.

## CAP 1.2 (`avisos/rss/56480`, aviso 28747)

```
identifier   urn:oid:2.49.0.0.76.0.2026.28747.1
sender       info.aviso@inmet.gov.br
sent         2026-11-22T11:35:31-03:00
status Actual | msgType Alert | scope Public | references None
info.category Met | event Tempestade | responseType Prepare
info.urgency Future | severity Moderate | certainty Likely
info.onset   2026-11-24T00:00:00-03:00
info.expires 2026-11-24T23:59:00-03:00
area.areaDesc "Aviso para as áreas: Centro Goiano, Triângulo Mineiro/..."
geocodes 0 | polygon presente
```

O CAP traz fuso explícito e a escala de severidade padrão (Perigo Potencial =
`Moderate`), mas **não** traz os códigos IBGE; o JSON traz os códigos, mas com
o fuso rotulado errado.

## Volume (histórico do RSS)

59 itens de 2026-11-13 a 2026-11-24, 1 a 7 por dia:

```
37 Tempestade | Perigo Potencial
13 Tempestade | Perigo
 4 Chuvas Intensas | Perigo Potencial
 3 Baixa Umidade | Perigo Potencial
 1 Vendaval | Perigo Potencial
 1 Ventos Costeiros | Perigo Potencial
```

## Termos de uso

Nenhuma licença ou documentação da API `apiprevmet3` encontrada (busca na
web). O guia de acesso a dados do INMET diz que o INMET fornece os dados e o
uso é responsabilidade do usuário. O endpoint é o backend do portal de avisos,
não uma API documentada — pode mudar sem aviso.
