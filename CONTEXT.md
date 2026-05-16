# AlertaVida — Contexto do Projeto

> **Como usar este arquivo:** este é o "cérebro" do projeto. Toda decisão arquitetural, mudança de stack ou nova camada implementada deve ser refletida aqui. **Documento vivo.**

---

## 1. Visão Geral

**AlertaVida** é um sistema de prevenção e alerta de desastres em tempo real, voltado para o público brasileiro. O objetivo é consumir dados de múltiplas fontes oficiais (CEMADEN, NASA EONET, INMET, INPE, Defesa Civil) e entregar alertas relevantes para usuários baseados em sua localização, com potencial uso por prefeituras e órgãos públicos.

**Missão técnica:** construir um sistema confiável, resiliente e testável — código que pode salvar vidas não pode falhar silenciosamente.

**Produto final esperado:**
- PWA (Progressive Web App) — funciona em iOS, Android e desktop com uma única codebase
- Mapa interativo com alertas em tempo real
- Notificações push baseadas em geolocalização
- Modo offline (último estado conhecido)
- Filtros por região e tipo de evento

---

## 2. Stack Técnica

### Backend
- **Linguagem:** Python 3.13.13
- **IDE:** Cursor
- **Validação de dados:** Pydantic (v2) ✅ *(Camada 2 — Parte 2 implementada)*
- **API Framework:** FastAPI — *a ser introduzido na Camada 5*
- **Agendador:** APScheduler (BackgroundScheduler) ✅
- **Banco de dados (início):** SQLite ✅
- **Banco de dados (futuro):** PostgreSQL (via Supabase)
- **Testes:** pytest 9.0.3 + pytest-cov + pytest-randomly + ruff ✅
- **Empacotamento:** uv + uv.lock + pyproject.toml + setuptools (src layout) ✅
- **CI/CD:** GitHub Actions (Ubuntu + Windows, push + schedule diário) ✅

### Frontend (futuro)
- **Framework:** Next.js (com suporte nativo a PWA)
- **Mapa:** Leaflet
- **Auth + DB cloud:** Supabase

### Versionamento
- **Git** desde a primeira linha ✅
- **Repositório:** https://github.com/CaioOlivieri/AlertaVida (privado)
- Convenção de commits: `tipo(escopo): descrição` em português (ex: `feat(camada-1): integra monitor com database`)

---

## 3. Arquitetura em 8 Camadas

Abordagem **camada por camada**, sem pular etapas. Cada camada deve estar funcional e testada antes de avançar.

### Camada 1 — Ingestão Resiliente de Dados ✅ CONCLUÍDA

**Implementado:**
- [x] Consumo da API CEMADEN (`monitor.py`)
- [x] Persistência em SQLite (`database.py`)
- [x] Sistema de deduplicação por `cod_alerta`
- [x] Função pura `montar_alerta()` para mapeamento de campos
- [x] Tratamento de erros por alerta (não derruba o loop)
- [x] Contador de erros + asserção sanitária no relatório final
- [x] Encoding UTF-8 forçado no terminal (acentos exibidos corretamente)
- [x] Retry com backoff exponencial em falhas de API (4 tentativas: imediata, 2s, 4s, 8s)
- [x] Distinção entre erros 4xx (sem retry) e 5xx/timeout (com retry)
- [x] Loop de execução agendado a cada 5 minutos (`scheduler.py`)
- [x] Shutdown gracioso via `Ctrl+C` (BackgroundScheduler + `time.sleep(1)`)
- [x] Proteção contra acúmulo: `max_instances=1`, `coalesce=True`, `misfire_grace_time=60`
- [x] Listener `EVENT_JOB_ERROR` mantém serviço vivo se uma rodada falhar
- [x] Suíte de testes (`tests/test_monitor.py` + `tests/test_scheduler.py` — 15 testes passando)
- Verificação de compatibilidade de schema (`_verificar_compatibilidade_schema`) que detecta bancos pré-A.1 e levanta `SchemaIncompativelError` antes do `_migrar_banco()` agir
- Testes diretos de `database.py` em `tests/test_database.py` (11 testes em 4 classes: verificação de compatibilidade, migration aditiva, criação de schema atual, idempotência)

**Adiado para camadas futuras:**
- [ ] Logs estruturados em JSON com timestamp/nível/contexto — virá junto com Pydantic na Camada 2

**Endpoint principal validado:**
`https://painelalertas.cemaden.gov.br/wsAlertas2`

Campos relevantes do JSON: `codigoalerta`, `datahoracriacao`, `tipoevento`, `nivel`, `estado`, `municipio`, coordenadas geográficas.

### Camada 2 — Modelagem de Domínio ✅ CONCLUÍDA
**Objetivo:** parar de trabalhar com dicionários soltos.

**Entidades a criar (Pydantic):**
- `Alerta` — id, codigo, tipo_evento, nivel_risco, municipio, estado, data_criacao, coordenadas, status
- `Municipio` — código IBGE, nome, estado, coordenadas
- `NivelRisco` — enum (BAIXO, MODERADO, ALTO, MUITO_ALTO)
- `TipoEvento` — enum (HIDROLOGICO, GEOLOGICO, METEOROLOGICO, etc.)

Esta também é a camada onde a refatoração da estrutura de pastas acontece (migrar para `src/`).

**Plano de execução em 3 partes:**
- [x] **Parte 1** — Refatoração para `src layout`, `pyproject.toml`, pacote `alertavida` 0.2.0 ✅
- [x] **Parte 2** — Modelos Pydantic implementados, 68 testes passando (revisões pendentes em issue #1)
- [x] **Parte 3** — Integração concluída: `montar_alerta()` retorna `Alerta`, `database.py` recebe `Alerta` ✅

### Camada 3 — Detecção de Mudanças e Eventos ✅ CONCLUÍDA

**Implementado:**
- [x] Inspeção empírica do contrato do wsAlertas2 (scripts/inspect_cemaden_payload.py)
- [x] Campos cod_alerta, codibge, ult_atualizacao, status mapeados e documentados
- [x] Migration do banco: colunas status_interno, visto_ultima_vez, rodadas_ausente,
      assinatura, codibge, latitude, longitude, ult_atualizacao + _migrar_banco() para
      bancos existentes
- [x] Tabela eventos (outbox) com índice idx_eventos_pendentes
- [x] ChangeDetector puro (detector.py): AlertaSnapshot, EventoDetectado,
      ResultadoDeteccao, detectar_mudancas()
- [x] Integração do ChangeDetector em executar_ingestao() — 3 fases:
      parse → detecção → persistência transacional
- [x] Outbox Pattern: INSERT em alertas e INSERT em eventos na mesma transação SQLite
- [x] buscar_snapshots_ativos() e aplicar_resultado_deteccao() em database.py
- [x] EventBus in-memory (subscribe/publish/handler_count)
- [x] OutboxDispatcher (processar_pendentes, batch_size=100)
- [x] log_handler padrão registrado para os 3 tipos de evento
- [x] Job do dispatcher integrado no scheduler (intervalo 30s)
- [x] Suíte de testes: 88 testes passando em < 1s

**Eventos emitidos:**
- AlertaCriado — alerta novo no feed, não existia no banco
- AlertaAtualizado — ult_atualizacao mudou para alerta já existente
- AlertaResolvido — alerta ausente por RODADAS_PARA_RESOLVER rodadas bem-sucedidas consecutivas

**Decisão: AlertaResolvido por inferência de ausência**
O campo status do CEMADEN sempre vale 1 — alertas são removidos do feed
sem sinalização prévia. AlertaResolvido é inferido após 3 rodadas ausentes
consecutivas (RODADAS_PARA_RESOLVER=3, configurável). Apenas rodadas
bem-sucedidas contam — falhas de rede não incrementam o contador.

### Camada 4 — Ingestão Multi-Fonte 🔒 BLOQUEADA
**Padrão arquitetural:** Adapter.

Interface comum `DataSource` com implementações:
- `CemadenSource` (refator do que está em `monitor.py`)
- `NasaEonetSource` (eventos globais — incluindo Brasil)
- `InmetSource` (planejado, requer mapeamento empírico)
- `InpeSource` (planejado, requer mapeamento empírico)

**Escopo da Camada 4:** ingestão paralela de fontes independentes. Cada fonte produz `Alerta`s próprios que coexistem na tabela com a coluna `fonte` como discriminador. Sem cruzamento ou correlação entre fontes — isso é responsabilidade da Camada 5.

**Estratégia de ingestão geográfica:**
- CEMADEN, INMET, INPE: 100% Brasil por construção.
- NASA EONET: ingestão global. O filtro Brasil/Próximo/Internacional acontece no domínio, não na ingestão. Isso permite ao usuário ativar visualização de eventos fora do Brasil quando desejar (Camadas 6-7).

Benefício: se uma fonte cair, sistema continua. Adicionar nova fonte = implementar interface.

**Subdivisão do trabalho (definida em 05/05/2026, antes da implementação):**

- **Parte A.1 — Refator destrutivo de domínio e banco**:
  - Surrogate key (`id INTEGER PRIMARY KEY AUTOINCREMENT`) + `UNIQUE (fonte, cod_alerta)` em vez de PK composta
  - `cod_alerta` muda de INTEGER para TEXT
  - `municipio` torna-se opcional, `coordenadas` torna-se obrigatório
  - Novo enum `NivelRisco.INDETERMINADO`
  - Novo enum `EscopoGeografico` (BRASIL, PROXIMO, INTERNACIONAL) substituindo bool
  - **Refator do enum `TipoEvento`**: valores antigos (`HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `OUTROS`) consolidados nos 5 subgrupos COBRADE (`HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`) + `INDETERMINADO`. Domínio passa a depender de padrão internacional (COBRADE/EM-DAT) em vez da terminologia de uma fonte específica.
  - `geographic.py` com `FaixaGeografica` + `classificar_escopo()` configurável via env var
  - Buffer "PROXIMO" padrão: 5° (~500km) — configurável via `ALERTAVIDA_BUFFER_PROXIMO_GRAUS`
  - `scripts/reclassificar_escopos.py` para re-classificar alertas existentes
  - `monitor.py` ajustado para gravar com `fonte='CEMADEN'` e `escopo_geografico` calculado
  - Atualização de TODOS os testes da Camada 3 que referenciam valores antigos do enum

- **Parte A.2 — Aditivo: taxonomia COBRADE com proveniência de classificação ✅ CONCLUÍDA**:
  - Novo módulo `src/alertavida/domain/cobrade.py` com tabela de mapeamento `EVENTO_CEMADEN_PARA_COBRADE` (apenas 2 entradas, baseado em inspeção empírica de 240 alertas em 4 amostras de 01-02/05/2026): `Risco Hidrológico → 1.2.0.0.0`, `Movimentos de Massa → 1.1.3.0.0`
  - Novo enum `FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) registrando proveniência do `cobrade_codigo`
  - Novo campo `cobrade_codigo: str | None` no domínio `Alerta`
  - Novo campo `fonte_classificacao: FonteClassificacao` no domínio `Alerta` (default INDETERMINADA)
  - Nova coluna `cobrade_codigo TEXT NULL` na tabela `alertas`
  - Nova coluna `fonte_classificacao TEXT NOT NULL DEFAULT 'INDETERMINADA'` na tabela `alertas`
  - Migração via `_migrar_banco()` (aditiva, não destrutiva)
  - Testes do mapper e do parser CEMADEN populando os novos campos

- **Parte B — CemadenSource como DataSource + Orquestrador isolado (após A.1 + A.2):** subdividida em três sub-partes encadeadas, cada uma com commit, CI verde e recap próprios:

  - **B.0 — fonte como atributo do modelo `Alerta` ✅ CONCLUÍDA 13/05/2026:** entregue em dois commits encadeados (B.0.a domínio + B.0.b infra) com CI temporariamente vermelho entre eles, registrando explicitamente que B.0.a sozinho não é deployável:

    - **B.0.a (commit d28cf56) — camada de domínio:** novo enum `FonteDado(StrEnum)` em `domain/enums.py` (valores fechados CEMADEN/EONET/INMET/INPE, sem INDETERMINADA porque fonte sempre é conhecida no momento de coleta) com `FonteDado.from_string` strict (alinhado com `NivelRisco.from_string`, não com `TipoEvento.from_string`). Campo `fonte: Annotated[FonteDado, Strict()]` em `Alerta` — strict cirúrgico no campo via `Annotated`, NÃO `strict=True` global no `model_config` (manter coerção em outros campos como `tipo_evento`, `nivel_risco`, datetimes). `Alerta.from_dict(data, *, fonte: FonteDado)` keyword-only obrigatório. Campo `fonte: FonteDado` adicionado também em `AlertaSnapshot` e `EventoDetectado`. `detectar_mudancas` perdeu parâmetro `fonte` (propaga via `Alerta.fonte` para criados/atualizados, via `snapshot.fonte` para resolvidos). `_payload_de(alerta)` consome `alerta.fonte.value`. CI ficou intencionalmente vermelho neste commit (10 testes de `test_monitor.py` falhando por TypeError nos kwargs obrigatórios) — comportamento esperado e documentado, B.0.b fecha.

    - **B.0.b (commit a5f5062) — camada de infraestrutura + ajuste retroativo do domínio:** novo campo `fonte_por_codigo: dict[str, FonteDado]` em `ResultadoDeteccao` populado pelo detector — modificação retroativa do domínio decidida em análise crítica de 13/05/2026 porque a alternativa (passar snapshots como parâmetro para `aplicar_resultado_deteccao`) violaria Dependency Inversion entre Infrastructure e Domain. `aplicar_resultado_deteccao(resultado, alertas_por_codigo, agora)` perdeu parâmetro `fonte`, lê via `resultado.fonte_por_codigo[cod]` quando precisa para `WHERE fonte = ? AND cod_alerta = ?`. `buscar_snapshots_ativos(fonte: FonteDado)` tipa parâmetro como enum; SELECT inclui coluna `fonte` para popular `AlertaSnapshot.fonte` via `FonteDado.from_string(row[1])` (rede de segurança contra valores corrompidos no banco). `monitor.py` ajusta call sites: `FONTE_CEMADEN: FonteDado = FonteDado.CEMADEN` (tipado), `Alerta.from_dict(item, fonte=FONTE_CEMADEN)` em `montar_alerta`, `detectar_mudancas(alertas, snapshots)` sem fonte, `aplicar_resultado_deteccao(resultado, alertas_validos, agora)` sem fonte. CI verde após B.0.b. Total: 183 testes passando, 0.58s.

    - **Schema SQL inalterado.** Coluna `fonte TEXT NOT NULL DEFAULT 'CEMADEN'` em `alertas` já existia desde A.1. B.0 mexeu apenas em código Python.

    - **`events.py` intocado.** Payloads já carregavam `"fonte"` desde A.1 via `_payload_de`; `OutboxDispatcher` é agnóstico de `Alerta`/`AlertaSnapshot`/`EventoDetectado`.

  - **B.1 — Interface `DataSource` + extração CEMADEN + infra de testes de contrato ✅ CONCLUÍDA 16/05/2026:** entregue em dois commits encadeados, ambos com CI verde:

    - **B.1.a (commit 90aa977) — infra da interface:** novo módulo `src/alertavida/sources/base.py` com `DataSource(ABC)` (property abstrata `fonte: FonteDado` + método abstrato `coletar() -> ResultadoColeta`), `ResultadoColeta` (frozen dataclass com `alertas: list[Alerta]`, `descartados: int`, `coletado_em: datetime` aware), `FalhaDeColeta(Exception)` (exceção tipada com `fonte: FonteDado`, `causa: str`, `original: Exception | None`, preserva chain via `raise ... from exc`). Novo `src/alertavida/sources/__init__.py` exportando os três tipos. Nova suíte `tests/sources/test_base.py` (13 testes — força ABC, valida frozen, valida chain). Novo `tests/sources/contrato.py` com `verificar_contrato_data_source(source_factory)` parametrizável — 7 invariantes (instância de ABC, fonte tipada como FonteDado, fonte em conjunto fechado, coletar retorna ResultadoColeta, alertas têm fonte consistente com a source, descartados int não-negativo, coletado_em aware com tzinfo). Novo `tests/fixtures/sources_fake.py` com `FakeDataSource` (implementação determinística sem I/O — princípio: testes verdadeiros usam dublês fiéis ao contrato real). Zero arquivos modificados, 196 testes passando, 1.01s.

    - **B.1.b (commit c9d9592) — extração CemadenSource + monitor simplificado:** novo módulo `src/alertavida/sources/cemaden.py` com `CemadenSource(DataSource)` migrando lógica HTTP+retry+backoff, `_montar_alerta`, `_normalize_payload`, cálculo de `escopo_geografico` e classificação COBRADE de `monitor.py`. Construtor keyword-only com três parâmetros injetáveis: `url=URL_CEMADEN`, `opener=urlopen` (tipado via `Callable[[Request], AbstractContextManager[_RespostaHTTP]]`, com `_RespostaHTTP` Protocol local PEP 544 — strict pelo contrato usado `read() -> bytes`, não pela classe `http.client.HTTPResponse` concreta), `timeout_segundos=30.0`. Importa de `sources.base` (não de `sources.__init__`) para evitar importação circular descoberta em runtime. `monitor.py` simplificado: remove `montar_alerta`, `normalize_alert_list`, `fetch_alertas_com_retry`, constantes `URL`/`FONTE_CEMADEN`, imports `urllib`/`socket`/`time`/`json`; `executar_ingestao` passa a fazer `CemadenSource().coletar()` e captura `FalhaDeColeta`. Variável `resultado` do detector renomeada para `resultado_det` para evitar shadowing com `resultado` da coleta — refator local aceitável, B.2 vai reorganizar o arquivo de qualquer jeito. `sources/__init__.py` passa a exportar `CemadenSource`. Nova suíte `tests/sources/test_cemaden.py` (20 testes: 14 migrados de `test_monitor.py` adaptados para construtor com opener injetável, 6 novos de invariantes B.1 — `coletado_em` aware, fonte CEMADEN em alertas retornados, propagação de TypeError/AttributeError como bug, FalhaDeColeta em rede esgotada/JSON inválido/Unicode inválido, contrato parametrizado). `tests/test_monitor.py` reduzido a 3 testes de orquestração mockando `CemadenSource.coletar` em vez de `fetch_alertas_com_retry` — incluindo teste novo `test_executar_ingestao_loga_e_sai_em_falha_de_coleta`. Esses 3 testes migrarão para `tests/ingestao/test_orquestrador.py` em B.2. `tests/test_contrato_cemaden.py` reescrito para usar `CemadenSource().coletar()` diretamente — aproxima o teste do contrato real usado em produção, exercitando fetch+parse+normalize+map em vez de só `Alerta.from_dict` isolado. 205 testes passando, 0.66s. CI verde em 37s (Ubuntu + Windows).

    - **Decisão arquitetural emergente em B.1.b: Protocol `_RespostaHTTP` local em vez de `HTTPResponse` concreta.** Tipar `opener: Callable[[Request], ContextManager[HTTPResponse]]` atrelaria a source à classe interna `http.client.HTTPResponse`. Como `coletar()` usa apenas `.read() -> bytes` do response, um Protocol local (PEP 544) que declara só esse contrato é mais correto: strict pelo contrato usado, não pela implementação. Fakes em teste só precisam de `read()`, sem `# type: ignore` por incompatibilidade de tipo concreto. Princípio de Dependency Inversion aplicado a tipos estáticos.

    - **Decisão arquitetural emergente em B.1.b: opener, url e timeout injetáveis no construtor.** Hoje testes mockavam transport via `patch("alertavida.monitor.urlopen", ...)` — referência por string ao módulo, frágil a renames. Construtor keyword-only (`CemadenSource(*, url=..., opener=..., timeout_segundos=...)`) declara dependências explicitamente. Testes passam fakes diretos sem string mágica. Futuro: staging/mock server para contrato sem mexer no código. Custo: três parâmetros opcionais. Benefício: declarativo, testes mais legíveis, sem string mágica.

  - **B.2 — Orquestrador isolado em `ingestao/orquestrador.py`:**
    - Novo módulo `src/alertavida/ingestao/orquestrador.py` com:
      - `executar_ingestao(sources: list[DataSource], agora: str | None = None) -> RelatorioIngestao` — função pública, recebe lista de fontes, captura `FalhaDeColeta` por fonte, isola falhas
      - `RelatorioFonte` — dataclass frozen por fonte: `fonte`, `coletados`, `novos`, `atualizados`, `inalterados`, `descartados`, `erros`, `falha_coleta: bool`, `duracao_segundos: float`
      - `RelatorioIngestao` — dataclass frozen agregando: `por_fonte: list[RelatorioFonte]`, `agora: str`, com `@property total`
    - `monitor.py` reduzido a ~30 linhas — entrypoint puro: parse args, configura logging, instancia `CemadenSource`, chama `executar_ingestao`, imprime relatório formatado, encerra
    - `scheduler.py` ajusta imports — passa a importar `executar_ingestao` de `alertavida.ingestao.orquestrador`
    - Testes existentes de `test_monitor.py` migram para `tests/ingestao/test_orquestrador.py` (testam o orquestrador com `FakeDataSource`, sem mocks de rede)
    - `tests/test_monitor.py` esvazia ou some — substituído pelos novos testes
    - `tests/sources/test_cemaden.py` recebe os testes CEMADEN-específicos que antes viviam em `test_monitor.py`

- **Parte C — `NasaEonetSource`** (após Parte B):
  - Nova fonte implementada como `DataSource`
  - Mapeamento de categorias EONET para subgrupos COBRADE em `cobrade.py`
  - Ingestão global, classificação geográfica via `EscopoGeografico`

Ordem de execução: A.1 → A.2 → B.0 → B.1 → B.2 → C. A.1 é destrutivo (PK composta, enum mudando valores). A.2 é puramente aditivo (campo nullable, coluna nova nullable, módulo novo). A.1, A.2, B.0 e B.1 concluídas em 2026-05-09, 2026-05-11, 2026-05-13 e 2026-05-16 respectivamente. A Parte B foi subdividida em 12/05/2026 em três sub-partes encadeadas (B.0 muda domínio, B.1 introduz interface e extrai CEMADEN, B.2 isola orquestrador) — cada uma com commit, CI verde e recap próprios antes da próxima. B.0 e B.1 foram cada uma entregues em dois commits encadeados (B.0.a/B.0.b, B.1.a/B.1.b). Big-bang foi rejeitado em favor de commits encadeados pelo mesmo motivo de A.1.1 → A.1.4: revisão localizada e reversibilidade independente. Próximo: B.2.

**Granularidade COBRADE — limite consciente da Camada 4:**

A taxonomia COBRADE permite 5 níveis (`GRUPO.SUBGRUPO.TIPO.SUBTIPO.0`). A Camada 4 do AlertaVida classifica APENAS até o nível de subgrupo:
- `Risco Hidrológico` → `1.2.0.0.0` (não distingue inundação 1.2.1, enxurrada 1.2.2, alagamento 1.2.3)
- `Movimentos de Massa` → `1.1.3.0.0` (não distingue quedas, deslizamentos, corridas, subsidências)

Distinção entre subtipos exige cruzamento com topografia, densidade urbana, série temporal de chuva (INMET) — fora do escopo da Camada 4. É problema da Camada 5 (Correlação de Eventos).

**Inferir subtipos heuristicamente na Camada 4 violaria §6.10 (honestidade dos dados).** O `Alerta` carrega `fonte_classificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) para que reclassificações futuras na Camada 5 preservem trilha de auditoria — sempre via UPDATE atômico (cobrade_codigo + fonte_classificacao mudam juntos).

### Camada 5 — Correlação de Eventos 🔒 BLOQUEADA
**Conceito:** `Incidente` = agregado de N `Alerta`s referentes ao mesmo evento físico observado por fontes diferentes.

Exemplo: uma enchente em Recife pode produzir um `Alerta` do CEMADEN (nível ALTO), um `Alerta` da NASA EONET (categoria severeStorms) e um `Alerta` do INMET (medição de chuva acumulada). Os três são relatos do mesmo evento.

**Algoritmo (versão inicial):**
- Mesma janela temporal (ex: ±6h)
- Distância geográfica abaixo de um limiar (ex: 50 km)
- Tipos de evento "compatíveis" (regra explícita por par de tipos)

**Pré-requisito técnico:** indexação espacial. SQLite R-Tree na fase atual; PostGIS quando migrarmos para Postgres na Camada 6. Correlação com loop puro não escala além de aproximadamente 100 alertas por rodada.

**Saída:** novos handlers podem assinar eventos `IncidenteCriado` e `IncidenteAtualizado` para reagir a eventos correlacionados.

### Camada 6 — API Própria (FastAPI) 🔒 BLOQUEADA
**Endpoints planejados:**
- `GET /alertas/ativos`
- `GET /alertas/por-municipio/{ibge}`
- `GET /alertas/historico`
- `GET /alertas/proximos?lat={lat}&lon={lon}&raio={km}`

Documentação automática via OpenAPI/Swagger (built-in do FastAPI).

Quando integrarmos com FastAPI, o `BackgroundScheduler` já existente continua funcionando — não é necessário trocar.

### Camada 7 — Interface Visual (Next.js + Leaflet) 🔒 BLOQUEADA
PWA com mapa interativo, lista de alertas, filtros, instalável como app no celular.

### Camada 8 — Motor de Notificação 🔒 BLOQUEADA
**Curto prazo:** Web Push (nativo do PWA).
**Médio prazo:** WhatsApp Business API, Email (SMTP), Telegram.
**Longo prazo:** Cell Broadcast (via parceria com operadoras/governo).

---

## 4. Estrutura de Pastas

### Estado atual
```
alertavida/
├── .gitignore
├── .github/
│   └── workflows/
│       └── test.yml              ← CI Ubuntu + Windows + schedule CEMADEN
├── uv.lock                       ← lockfile cross-platform (commitado)
├── CLAUDE.md
├── CONTEXT.md
├── README.md
├── pyproject.toml
├── scripts/
│   └── inspect_cemaden_payload.py
│   └── reclassificar_escopos.py   ← re-classifica escopo_geografico após mudança de buffers
├── data/
│   └── alertavida.db          ← gerado em runtime (gitignored)
│   └── samples/               ← JSONs do inspetor (gitignored)
├── src/
│   └── alertavida/
│       ├── __init__.py
│       ├── monitor.py
│       ├── database.py
│       ├── scheduler.py
│       ├── events.py
│       └── domain/
│           ├── __init__.py
│           ├── alerta.py
│           ├── municipio.py
│           ├── coordenadas.py
│           ├── enums.py
│           └── detector.py
└── tests/
    ├── __init__.py
    ├── conftest.py               ← fixture db_temporario
    ├── test_contrato_cemaden.py  ← teste de contrato @integration
    ├── test_monitor.py
    ├── test_scheduler.py
    ├── test_events.py
    └── domain/
        ├── test_alerta.py
        └── test_detector.py
```

### Estrutura alvo (após refatorações futuras)
```
alertavida/
├── CONTEXT.md
├── README.md
├── .gitignore
├── .env.example
├── pyproject.toml              ← dependências e config
├── src/
│   └── alertavida/
│       ├── __init__.py
│       ├── ingestion/              ← Camada 1
│       │   ├── __init__.py
│       │   ├── scheduler.py
│       │   ├── persistence.py
│       │   └── retry.py
│       ├── domain/                 ← Camada 2
│       │   ├── __init__.py
│       │   ├── alerta.py
│       │   ├── municipio.py
│       │   └── enums.py
│       ├── events/                 ← Camada 3
│       │   ├── __init__.py
│       │   └── change_detector.py
│       ├── sources/                ← Camada 4
│       │   ├── __init__.py
│       │   ├── base.py             ← interface DataSource
│       │   ├── cemaden.py
│       │   ├── nasa_eonet.py
│       │   └── inmet.py
│       ├── correlation/            ← Camada 5
│       │   ├── __init__.py
│       │   └── incidente.py
│       ├── api/                    ← Camada 6
│       │   ├── __init__.py
│       │   ├── main.py
│       │   └── routes/
│       └── notifications/          ← Camada 8
│           └── __init__.py
├── tests/
│   ├── ingestion/
│   ├── domain/
│   ├── events/
│   └── sources/
└── data/                       ← SQLite local (gitignored)
```

A migração para sub-módulos por camada (ingestion/, domain/, etc.) acontece **gradualmente** conforme cada camada é trabalhada.

---

## 5. Como Rodar (Estado Atual)

### Instalação (após clonar o repo)
```bash
pip install -e ".[dev]"
```
Modo editável: mudanças no código aparecem imediatamente, sem reinstalar.

### Execução única (debug, validação)
```bash
python -m alertavida.monitor
```
Faz uma rodada de ingestão, persiste alertas novos, imprime relatório, encerra.

### Execução contínua (modo serviço)
```bash
python -m alertavida.scheduler
```
Roda a primeira rodada imediatamente, depois repete a cada 5 minutos. Encerra com `Ctrl+C`.

### Testes
```bash
python -m pytest -v
```
Roda os 15 testes da suíte. Tempo total < 1 segundo (graças ao mock de `time.sleep`).

---

## 6. Princípios Técnicos (não negociáveis)

1. **TDD sempre que possível.** Antes de escrever código de uma nova função, escrever o teste que ela precisa passar. Especialmente importante porque o código gerado por IA pode parecer correto mas ter erros lógicos.
2. **Testes unitários em cada camada.** Sem testes, não há escala.
3. **Logs estruturados desde o início.** Saber o que o sistema faz em produção.
4. **Configuração via variáveis de ambiente.** Nunca hardcoded. Usar `.env` + `pydantic-settings`.
5. **Type hints em todas as funções.** Python 3.13 — sem desculpa.
6. **Pydantic para qualquer entrada/saída de dados externos.** Validação no limite do sistema.
7. **Commits frequentes e descritivos.** Cada mudança significativa = um commit.
8. **README mínimo mas presente.** Como rodar, arquitetura básica, decisões importantes.
9. **Mocks em testes que envolvem rede ou tempo.** Suíte deve rodar em < 1 segundo.
10. **Honestidade dos dados.** O modelo de domínio representa fielmente o que a fonte fornece, sem inventar precisão. Campos são opcionais quando a fonte os entrega esporadicamente, obrigatórios quando garantidos. Enriquecimento de dados ausentes (lookups, fallbacks, inferências) é responsabilidade da camada de fontes (Camada 4), não da camada de domínio (Camada 2).

---

## 7. Convenções do Projeto

### Nomenclatura
- Variáveis e funções: `snake_case`
- Classes: `PascalCase`
- Constantes: `UPPER_SNAKE_CASE`
- Português ou inglês? **Domínio em português** (Alerta, Municipio, NivelRisco), **infraestrutura em inglês** (scheduler, persistence, base).

### Imports
- Ordem: stdlib → terceiros → locais
- Imports absolutos sempre que possível
- Imports internos do projeto começam com `alertavida.` (ex: `from alertavida.database import ...`)

### Tratamento de erros
- Nunca usar `except:` genérico
- Sempre logar o erro com contexto
- Decidir explicitamente: re-raise, retry, ou fallback?
- Erros 4xx (cliente) NÃO devem ter retry; erros 5xx, timeouts e conexão SIM

### Commits
- Formato: `tipo(escopo): descrição`
- Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Escopo: nome da camada quando aplicável (`camada-1`, `camada-2`, etc.)
- Exemplo: `feat(camada-1): integra monitor com database, dedup e testes unitários`

---

## 8. Decisões Arquiteturais Já Tomadas

| Decisão | Motivo |
|---|---|
| PWA em vez de app nativo | Codebase única, sem App Store, atualização instantânea |
| SQLite no início | Simplicidade. PostgreSQL quando houver múltiplos usuários |
| Pydantic v2 | Padrão moderno, integração nativa com FastAPI |
| FastAPI | Documentação automática, performance, suporte async |
| Next.js + Leaflet | Familiaridade + Leaflet é gratuito e robusto |
| Event-Driven na Camada 3 | Desacopla ingestão de consumidores |
| Adapter pattern na Camada 4 | Permite adicionar fontes sem mexer no resto |
| Função pura `montar_alerta()` | Separa mapeamento (testável) de I/O (rede + banco) |
| Dedup por `cod_alerta` (PK) | Garantia de integridade no nível do banco |
| Retry só em 5xx/timeout/conexão | Erros 4xx não se resolvem com retry; 408/429 são exceções |
| Backoff exponencial (2s, 4s, 8s) | Padrão da indústria — respeita API caída sem hostilizar |
| BackgroundScheduler em vez de Blocking | Permite shutdown gracioso via Ctrl+C no Windows; prepara integração futura com FastAPI |
| `time.sleep(1)` no thread principal | Funciona em qualquer SO, respeita Ctrl+C nativamente |
| `max_instances=1` + `coalesce=True` | Evita acúmulo de execuções se uma rodada demorar mais que o intervalo |
| Mock de `time.sleep` nos testes | Suíte completa em < 1 segundo |
| src layout (`src/alertavida/`) | Padrão recomendado pela Python Packaging Authority — força import correto, evita armadilhas com imports relativos |
| `pyproject.toml` em vez de `requirements.txt` | Padrão moderno (PEP 517/518); centraliza deps, build, config de ferramentas |
| Banco em `data/` | Separa dados gerados em runtime do código fonte |
| `pip install -e` (modo editável) | Mudanças no código aparecem instantaneamente sem reinstalar |
| Coordenadas como Value Object opcional (`Coordenadas \| None`) | Honestidade dos dados — fonte nem sempre fornece com precisão |
| Município sempre obrigatório no Alerta | Fallback geográfico mínimo garantido |
| Enriquecimento (IBGE, lookups) só na Camada 4 | Camada 2 representa, Camada 4 enriquece |
| AlertaResolvido por inferência (N=3 rodadas ausentes) | status do CEMADEN sempre vale 1; alertas somem do feed sem aviso; N=3 é conservador (15 min) e configurável |
| Outbox Pattern em SQLite | INSERT de alerta e evento na mesma transação — elimina dual-write; caminho natural para Postgres LISTEN/NOTIFY e depois broker |
| ChangeDetector função pura | Zero I/O; testável sem mock de banco; separa decisão (detector) de execução (database) |
| EventBus in-memory sem biblioteca | ~50 linhas próprias; sem acoplamento externo; substituível por broker quando necessário |
| ult_atualizacao como gatilho de AlertaAtualizado | Campo explícito entregue pelo CEMADEN; mais confiável que hash de campos |
| codibge parseado em from_dict | Campo presente no payload; evita lookup externo planejado para Camada 4 |
| OutboxDispatcher a cada 30s no scheduler | Latência aceitável para Camada 3; Camada 7 pode reduzir se notificações exigirem |
| uv em vez de pip direto | Lockfile cross-platform, reprodutibilidade garantida entre máquinas e CI |
| CI matrix Ubuntu + Windows | Paths e encoding se comportam diferente entre OSes — bugs de plataforma aparecem antes do usuário descobrir |
| Teste de contrato CEMADEN separado (`@integration`) | API não documentada pode mudar schema sem aviso; teste diário detecta antes de quebrar produção |
| `conftest.py` com `db_temporario` | Centraliza setup de banco temporário — elimina monkeypatch duplicado em 3 testes |
| Schedule diário para contrato (não em push) | Evita consumir minutos de CI em cada commit para um teste que depende de rede externa |
| Renumeração do roadmap (4-7 → 4-8 com Camada 5 nova) | Correlação de eventos é responsabilidade própria, não sub-tarefa da Camada 4. Documentar erros de planejamento explicitamente em vez de esconder via "Camada 4.5". |
| Surrogate key + UNIQUE composto em vez de PK composta | `id INTEGER PRIMARY KEY AUTOINCREMENT` + `UNIQUE (fonte, cod_alerta)`. FKs em outras tabelas viram INTEGER simples; URLs futuras ficam opacas (`/alertas/12345`); renomear fontes não quebra referências. |
| `cod_alerta` como TEXT, não INTEGER | CEMADEN usa código numérico, EONET usa string (`EONET_5421`). String é o tipo mais inclusivo. |
| `municipio` opcional, `coordenadas` obrigatório no Alerta | Inversão da regra anterior. Múltiplas fontes mostraram que o mínimo garantido pelo conjunto é coordenadas, não município. Honestidade dos dados aplicada ao conjunto, não ao CEMADEN isolado. |
| `NivelRisco.INDETERMINADO` adicionado ao enum | EONET não classifica gravidade. Tipo permanece não-nulo; downstream trata `INDETERMINADO` como categoria explícita em vez de caso especial de None. |
| `EscopoGeografico` enum em vez de bool | Três estados (BRASIL, PROXIMO, INTERNACIONAL) capturam relevância geográfica sem inventar precisão. Eventos fronteiriços e marítimos próximos têm classificação própria. |
| Bbox + buffer em vez de polígono shapely | Quatro comparações numéricas, sem dependência nova. "Honestidade dos dados" — imprecisão é assumida e documentada, substituível por shapely sem quebrar contrato. |
| Faixas geográficas configuráveis em valor, imutáveis em estrutura | Buffers individuais via env var (`ALERTAVIDA_BUFFER_PROXIMO_GRAUS`). Adicionar/remover categorias requer mudança em `FAIXAS_DEFAULT` no código + migração via `scripts/reclassificar_escopos.py`. |
| `escopo_geografico` pré-computado na ingestão | Cálculo na ingestão evita recálculo em queries. Mudanças nos buffers só afetam alertas novos; re-classificação é operação manual via script dedicado. |
| Ingestão global de NASA EONET (sem filtro `bbox` na requisição) | Filtro Brasil/Próximo/Internacional acontece no domínio, não na fonte. Permite ao usuário visualizar eventos fora do Brasil quando desejar (Camadas 7-8). Custo de armazenamento aceitável até migração para Postgres. |
| `monitor.py` vira orquestrador multi-fonte (Camada 4) | Continua sendo o entrypoint (`python -m alertavida.monitor`); lógica CEMADEN específica migrada para `sources/cemaden.py` em B.1.b (2026-05-16); loop sobre `[CemadenSource(), NasaEonetSource(), ...]` será montado pelo orquestrador em B.2 (ingestao/orquestrador.py). Testes existentes continuam importando `executar_ingestao()` até B.2 migrá-los para `tests/ingestao/test_orquestrador.py`. |
| Indexação espacial obrigatória na Camada 5 | SQLite R-Tree na fase atual; PostGIS quando migrarmos para Postgres na Camada 6. Não relevante para Camadas 1-4. |
| Refator do enum `TipoEvento` para subgrupos COBRADE | Domínio dependia da terminologia de uma fonte específica (CEMADEN), violando Dependency Inversion. Refator alinha com padrão internacional COBRADE/EM-DAT — `HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`. Cada `DataSource` implementa mapeamento próprio para esses valores. Janela de baixo custo: feito agora, antes de Parte B/C triplicarem a superfície de mudança. |
| `cobrade_codigo` + enum `FonteClassificacao` no Alerta | Campo `cobrade_codigo: str \| None` preserva código no nível de subgrupo. Enum `FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) registra proveniência da classificação. Trilha de auditoria preservada quando Camada 5 reclassificar para subtipos. Open/Closed: novas estratégias de classificação só adicionam valores ao enum. |
| Granularidade COBRADE limitada ao subgrupo na Camada 4 | Inspeção empírica de 4 amostras CEMADEN (240 alertas, 01-02/05/2026) confirmou ausência de campo COBRADE explícito e taxonomia limitada a 2 tipos × 3 níveis. Distinção entre subtipos (inundação vs enxurrada vs alagamento; quedas vs deslizamentos vs corridas) exige topografia, densidade urbana, INMET. Inferir heuristicamente na Camada 4 violaria honestidade dos dados (§6.10). Subtipos são problema da Camada 5. |
| Subdivisão da Camada 4 Parte A em A.1 (destrutivo) + A.2 (aditivo COBRADE) | A.1 quebra surrogate key, enum, refator de domínio. A.2 é aditivo puro: coluna nullable, módulo novo, sem reescrita. Cada parte com narrativa coerente e independentemente reversível. Ordem A.1 → A.2 evita conflito de migration. A.2 pode rodar em paralelo com Parte B. |
| Fixtures CEMADEN versionadas em `tests/fixtures/cemaden/` | 4 amostras capturadas em 01-02/05/2026 (durante enchente real em PE) viram fixtures de teste de regressão. Uso por nível de teste: parsing usa 1 fixture, integração do `ChangeDetector` usa 2 fixtures consecutivas com diff controlado, contrato real continua via `@integration` no endpoint vivo. README documenta origem e contexto de cada fixture. |
| Pasta `data/` é runtime/state, ignorada via gitignore com exceção `.gitkeep` | Banco SQLite, payloads brutos, logs do inspector, backups — nada canônico. Estratégia uniforme: `data/*` ignorado, estrutura preservada via `.gitkeep`. Fixtures canônicas vivem em `tests/fixtures/`, não em `data/samples/`. Single Responsibility aplicado a estrutura de pastas. |
| Invariante de atomicidade COBRADE via `@model_validator` Pydantic, não CHECK constraint SQL | SQLite não permite adicionar CHECK constraint via `ALTER TABLE`, apenas via rebuild da tabela. Usar CHECK quebraria o caminho de `_migrar_banco()` em bancos preexistentes (A.2 deixaria de ser aditivo puro). Mover a invariante para o domínio (`@model_validator(mode="after")` em `Alerta`) cobre uniformemente banco novo e migrado, gera `ValidationError` explícito no boundary, e alinha com §6 ("Pydantic para qualquer entrada/saída de dados externos. Validação no limite do sistema"). |
| Verificação explícita de schema antes de `_migrar_banco()` | A migration C3 → A.1 nunca existiu (PK composta → surrogate key não é alterável via ALTER TABLE no SQLite). O `CREATE TABLE IF NOT EXISTS` mascarava a incompatibilidade silenciosamente, e `_migrar_banco()` pós-A.2 adicionaria colunas COBRADE a bancos C3, criando quimera C3+A.2 onde queries do código atual quebrariam em runtime longe da causa raiz. Verificação aborta com erro claro mandando recriar o banco. Caminho 3 da discussão arquitetural de 12/05/2026. |
| `SchemaIncompativelError` como exceção específica | Facilita `pytest.raises(SchemaIncompativelError)` e filtragem em logs futuros. Não é `RuntimeError` genérico — distingue erro de schema de qualquer outra falha de inicialização do banco. |
| `fonte` como atributo do modelo `Alerta` (B.0) | Proveniência da fonte é metadado de domínio, consistente com `fonte_classificacao` (A.2) que registra proveniência da classificação COBRADE. Inconsistência conceitual em manter um no domínio e outro como parâmetro de operação. Atributo no modelo elimina parâmetro propagado em `aplicar_resultado_deteccao`, garante imutabilidade da origem via Pydantic frozen, torna `Alerta` auto-suficiente para auditoria (REPL, logs, testes). Custo: `Alerta.from_dict()` ganha parâmetro `fonte`. |
| `DataSource` como ABC com `ResultadoColeta` tipado, não `list[Alerta]` | Orquestrador precisa de `descartados` por fonte para preservar a assertion sanitária (`novos + atualizados + inalterados + descartados + erros == total`) que hoje vive globalmente. `list[Alerta]` puro força o orquestrador a adivinhar quantos foram descartados. `ResultadoColeta` (frozen dataclass com `alertas`, `descartados`, `coletado_em`) carrega contabilidade explícita. |
| `FalhaDeColeta` como exceção tipada do domínio | Mesma filosofia de `SchemaIncompativelError`: exceção específica facilita `pytest.raises(FalhaDeColeta)` e filtragem em logs. Não é `RuntimeError` genérico — distingue falha de fonte de qualquer outra falha do orquestrador. Falhas individuais de alerta dentro de uma rodada NÃO sobem como `FalhaDeColeta` (são contadas em `descartados`); só falhas de rodada inteira (rede esgotada, schema rejeitado, retries esgotados). |
| Orquestrador separado em `ingestao/orquestrador.py`, não em `monitor.py` (B.2) | `monitor.py` atual viola SRP três vezes: entrypoint + orquestração + lógica CEMADEN. B.1 extrai a lógica CEMADEN para `sources/cemaden.py`; B.2 extrai a orquestração para `ingestao/orquestrador.py`; `monitor.py` fica como entrypoint puro (~30 linhas: argv, logging config, instancia sources, chama executar_ingestao, formata relatório). Alinha com estrutura-alvo documentada em §4 (subpacote `ingestion/` da Camada 1). |
| `RelatorioIngestao` tipado em vez de contadores soltos | Hoje a "assertion sanitária" vive em variáveis locais frágeis (`novos`, `atualizados`, `inalterados`, `descartados`, `erros`). `RelatorioFonte` (frozen dataclass por fonte) + `RelatorioIngestao` (frozen agregado com `@property total`) torna contabilidade imutável, tipada, e consumível por: logging, testes, e (futuro) endpoint `/health` da Camada 6. Invariantes verificáveis em vez de variáveis locais. |
| Testes de contrato parametrizados em `tests/sources/contrato.py` | Suíte `verificar_contrato_data_source(source_factory)` roda em qualquer `DataSource`. Quando `NasaEonetSource` entrar (Parte C), uma linha de teste garante conformidade total com o contrato. Mudanças no contrato (campo novo em `DataSource`, invariante nova em `ResultadoColeta`) quebram TODAS as sources em uma única definição. Manutenção centralizada, evolução segura. |
| `FakeDataSource` em vez de `unittest.mock.Mock` | `Mock` é genérico — qualquer atributo acessado retorna outro Mock, escondendo erros de assinatura. `FakeDataSource` implementa a interface real; se `DataSource` mudar (método novo, assinatura nova), o fake quebra imediatamente dando feedback. Princípio: testes verdadeiros usam dublês fiéis ao contrato real. |
| Migração da Parte B em três commits encadeados (B.0 → B.1 → B.2), não big-bang | Mesmo princípio de A.1.1 → A.1.4: revisão localizada, reversibilidade independente, CI verde por etapa. B.0 muda domínio sem mexer em sources; B.1 extrai sem reorganizar; B.2 reorganiza com a interface já estabelecida. Big-bang concentraria risco em um commit gigante onde falhas viram garimpo. |
| `FonteDado` como `StrEnum` (não `str, Enum`) | Consistência com `FonteClassificacao` (já é `StrEnum`). `StrEnum` (Python 3.11+) retorna o valor diretamente em `str(membro)`, comportamento desejável para serialização JSON em payloads de eventos. Decisão NÃO se estende retroativamente para `NivelRisco`, `TipoEvento`, `EscopoGeografico` — fora do escopo de B.0; deixa essa dívida documentada para refator futuro de consolidação. |
| `FonteDado.from_string` strict (levanta), não retorna sentinela | Alinhado com `NivelRisco.from_string`, não com `TipoEvento.from_string` que retorna `INDETERMINADO`. Justificativa: fonte desconhecida em runtime é bug grave — banco gravaria valor inválido violando `UNIQUE(fonte, cod_alerta)`. Levantar força tratar. Fonte sempre é conhecida no momento de coleta (`DataSource` declara sua origem), diferente de `TipoEvento` onde campos brutos do payload podem ser irreconhecíveis. |
| `Annotated[FonteDado, Strict()]` cirúrgico em vez de `strict=True` global no `model_config` | `strict=True` em `ConfigDict` afetaria TODOS os campos do `Alerta`, bloqueando coerção que hoje funciona (strings ISO para datetimes, strings para `TipoEvento`/`NivelRisco` em construção direta). Mudança não-cirúrgica quebraria uma quantidade imprevisível de testes existentes. `Annotated[FonteDado, Strict()]` aplica strict APENAS ao campo `fonte` — bloqueia coerção string → enum onde queremos, preserva resto do modelo. Pydantic v2 feature, documentado em https://docs.pydantic.dev/latest/concepts/strict_mode/. |
| `Alerta.from_dict(data, *, fonte: FonteDado)` keyword-only obrigatório | Elimina ambiguidade no call site: `Alerta.from_dict(payload, FonteDado.CEMADEN)` seria menos legível que `Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)`. Padrão recomendado em Effective Python item 25 (force keyword-only para parâmetros que afetam comportamento semântico). Custo: zero. Benefício: clareza. |
| `fonte_por_codigo` em `ResultadoDeteccao` em vez de parâmetro para `aplicar_resultado_deteccao` | Decisão revisada em 13/05/2026 durante análise crítica antes de B.0.b. Alternativa rejeitada (snapshots como parâmetro de `aplicar_resultado_deteccao`) violaria Dependency Inversion — Infrastructure (`database.py`) dependendo de detalhes de Domain (`AlertaSnapshot`) para descobrir fonte. Princípio Tell, Don't Ask: o detector "diz" tudo que aconteceu (eventos, códigos vistos, códigos ausentes, mapa de fonte por código); a infra "executa" sem precisar adivinhar. Detector já tem acesso a `Alerta.fonte` e `AlertaSnapshot.fonte` — popula o mapa sem trabalho extra. Em B.2 (orquestrador), cada `ResultadoDeteccao` por fonte é independente; o orquestrador não precisa montar dicionários auxiliares repetindo lógica. |
| Modificação retroativa de domínio aceitável em B.0.b | B.0.a fechou domain layer. B.0.b precisou adicionar `fonte_por_codigo` ao `ResultadoDeteccao` — modificação retroativa. Aceitável porque: (1) o código de B.0.a continua funcionando, só ganha um campo novo; (2) a alternativa (refazer B.0.a com a decisão correta desde o início) seria desperdício de trabalho já commitado; (3) o histórico mostra honestamente "B.0.a fechou domínio com decisão incompleta, análise crítica antes de B.0.b refinou". Princípio: refator é trabalho legítimo, esconder o refator via squash perderia informação. |
| `FonteDado.from_string` na leitura do banco como rede de segurança | `buscar_snapshots_ativos` chama `FonteDado.from_string(row[1])` ao construir `AlertaSnapshot`. Se um dia a coluna `fonte` no banco tiver valor inválido (corrupção, migration falha, intervenção manual errada), levanta `ValueError` na leitura em vez de propagar silenciosamente para o domínio. Custo: dois caracteres a mais. Benefício: detecção precoce de corrupção de dados. |

---

## 9. Como trabalhar com agentes de IA neste projeto

### 9.1 Divisão de papéis

- **Claude (chat web)** — arquiteto. Decisões de design, revisão crítica, formulação de prompts. Não toca arquivos do projeto.
- **Claude Code (terminal)** — executor. Lê o codebase via `CLAUDE.md`, edita arquivos, roda testes, dá recap.
- **Cursor (IDE)** — editor + revisão visual. Diff, navegação, commits.

### 9.2 Fluxo padrão

1. Discussão arquitetural no chat → prompt formulado
2. Prompt colado no Claude Code → execução com recap
3. Recap trazido de volta ao chat → validação contra desvios
4. Commit no Cursor após aprovação

### 9.3 Anti-padrões aprendidos

- **Strings literais soltas em prompts** ⇒ agente "embeleza" (`"Chuva"` virou `"Chuva intensa"` em 2026-04-30, ver issue #1). Sempre marcar com "use estas strings exatamente".
- **Escopo implícito** ⇒ agente toca arquivos não pedidos. Sempre listar `NÃO modificar:` no prompt.
- **Recap ausente** ⇒ desvios passam silenciosos. Sempre pedir `git diff --stat` no fim.

### 9.4 Estrutura de prompt recomendada

1. **Contexto:** "Leia o CLAUDE.md antes de qualquer coisa."
2. **Objetivo:** o que se quer alcançar (não como)
3. **Requisitos funcionais:** comportamento esperado, casos de borda
4. **Requisitos não funcionais:** robustez, testes, convenções
5. **Critério de sucesso:** como saber que está pronto
6. **Escopo de não-modificação:** lista explícita de arquivos intocáveis

---

## 10. Histórico de Mudanças

| Data | Mudança |
|---|---|
| 2026-04-27 | Criação inicial do CONTEXT.md |
| 2026-04-27 | Camada 1 parcial: integração monitor + database, deduplicação por cod_alerta, função pura montar_alerta, testes unitários (6 passando), repositório no GitHub |
| 2026-04-28 | Correções na Camada 1: contador de erros, encoding UTF-8, asserção sanitária dos contadores (7 testes passando) |
| 2026-04-28 | Retry com backoff exponencial na requisição CEMADEN, distinção entre erros 4xx e 5xx (11 testes passando) |
| 2026-04-28 | Agendamento automático com APScheduler (BackgroundScheduler), shutdown gracioso via Ctrl+C, requirements.txt criado (15 testes passando) |
| 2026-04-28 | **Camada 1 concluída** — sistema roda continuamente como serviço, resiste a falhas de rede, encerra limpo |
| 2026-04-29 | Camada 2 — Parte 1 concluída: refatoração para `src layout`, `pyproject.toml`, pacote `alertavida` 0.2.0 (15 testes passando) |
| 2026-05-01 | Camada 2 — Parte 2: 68 testes passando (revisões em issues #1 e #2). Claude Code instalado e CLAUDE.md criado. Princípio de honestidade dos dados formalizado. Fluxo de trabalho com agentes de IA documentado (§9). |
| 2026-05-01 | **Camada 2 concluída** — Parte 3 integrada, `pick_value()` removida, 68 testes passando |
| 2026-05-02 | Camada 3 — inspeção empírica do wsAlertas2: campos status, ult_atualizacao e codibge mapeados |
| 2026-05-02 | Camada 3 — migration do banco: colunas de ciclo de vida + tabela eventos (outbox) |
| 2026-05-02 | Camada 3 — ChangeDetector puro implementado, 79 testes passando |
| 2026-05-02 | Camada 3 — integração do detector em executar_ingestao com outbox transacional, 81 testes |
| 2026-05-02 | **Camada 3 concluída** — EventBus, OutboxDispatcher, job no scheduler, 88 testes passando |
| 2026-05-03 | Infraestrutura de testes automatizados: uv + uv.lock, pytest-cov/randomly/ruff, CI GitHub Actions (Ubuntu + Windows), conftest.py com fixture db_temporario, marker integration, teste de contrato CEMADEN agendado diariamente |
| 2026-05-04 | Pré-Camada 4 — design da ingestão multi-fonte: roadmap renumerado (4-8 com Camada 5 nova de Correlação), decisões arquiteturais sobre EscopoGeografico, surrogate key, ingestão global EONET, faixas configuráveis. CONTEXT.md atualizado antes do código. |
| 2026-05-05 | Pré-Camada 4 Parte A — análise empírica de 4 amostras CEMADEN (240 alertas, 01-02/05/2026) confirmou ausência de campo COBRADE no payload e taxonomia limitada a 2 tipos físicos × 3 níveis. Decisões: refator do enum `TipoEvento` para subgrupos COBRADE; novos campos `cobrade_codigo` + enum `FonteClassificacao` no `Alerta`; granularidade COBRADE limitada ao subgrupo na Camada 4 (subtipos pertencem à Camada 5); Parte A subdividida em A.1 (destrutivo) + A.2 (aditivo COBRADE); fixtures CEMADEN versionadas em `tests/fixtures/`; `data/*` no gitignore. CONTEXT.md atualizado antes do código. |
| 2026-05-07 | Camada 4 Parte A.1 — A.1.1, A.1.3 commitadas e CI verde. A.1.2 commitada LOCAL (não pushed). A.1.4 concluída e commitada. Push pendente.
| 2026-05-09 | Camada 4 Parte A.1.4 concluída — detector, database, monitor, testes e scripts/reclassificar_escopos.py. cod_alerta str, surrogate key + UNIQUE (fonte, cod_alerta), coordenadas obrigatório, escopo_geografico pré-computado na ingestão. 120 testes passando. |
| 2026-05-11 | Camada 4 Parte A.2 concluída — `domain/cobrade.py` com `EVENTO_CEMADEN_PARA_COBRADE` (2 entradas baseadas em inspeção empírica) e `validar_formato`. Enum `FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA). Campos `cobrade_codigo: str \| None` e `fonte_classificacao: FonteClassificacao` em `Alerta`, com `@field_validator` de formato e `@model_validator` da invariante atômica. Colunas correspondentes em `alertas` via `_migrar_banco()` idempotente. 139 testes passando, CI verde em Ubuntu + Windows. |
| 2026-05-12 | Item 8 do ciclo de testes concluído — testes diretos de `database.py` (11 testes em `tests/test_database.py` cobrindo verificação de compatibilidade, migration aditiva, criação de schema atual, idempotência). Descoberta retroativa: A.1 (09/05/2026) introduziu ruptura de schema sem migration automática — `_migrar_banco()` pós-A.1 era `pass`, e o pós-A.2 só adiciona aditivamente as colunas COBRADE. `SchemaIncompativelError` adicionada para detectar e abortar com erro claro em bancos pré-A.1. Fixtures de schemas legados versionadas em `tests/fixtures/schemas_legados.py` (pré-C3, pós-C3, pós-A.1). 150 testes passando, CI verde em Ubuntu + Windows. |
| 2026-05-12 | Pré-Parte B — desenho arquitetural da Camada 4 Parte B registrado antes da implementação. Decisões: `fonte` vira atributo do `Alerta` (consistência com proveniência da classificação A.2); `DataSource` ABC com `ResultadoColeta` tipado (preserva assertion sanitária por fonte); `FalhaDeColeta` exceção tipada; orquestrador isolado em `ingestao/orquestrador.py` (SRP — `monitor.py` viola três vezes); `RelatorioIngestao` tipado substitui contadores soltos; testes de contrato parametrizados em `tests/sources/contrato.py`; `FakeDataSource` em vez de `unittest.mock.Mock`; migração em três commits encadeados B.0 → B.1 → B.2 (big-bang rejeitado). CONTEXT.md atualizado antes do código. |
| 2026-05-13 | Camada 4 Parte B.0 concluída — `fonte` como atributo do modelo `Alerta`, propagado por toda a stack (domínio + infra). Entregue em dois commits encadeados: B.0.a (d28cf56, domínio: `FonteDado` enum, campos `fonte` em `Alerta`/`AlertaSnapshot`/`EventoDetectado`, `Annotated[FonteDado, Strict()]` cirúrgico) deixou CI intencionalmente vermelho em 10 testes de `test_monitor.py`; B.0.b (a5f5062, infra: `aplicar_resultado_deteccao` sem param `fonte`, `buscar_snapshots_ativos(fonte: FonteDado)`, `monitor.py` ajustado) fechou o ciclo com CI verde. Decisão arquitetural retroativa em B.0.b: `fonte_por_codigo: dict[str, FonteDado]` em `ResultadoDeteccao` populado pelo detector — princípio Tell, Don't Ask, evita vazamento de responsabilidade entre Infrastructure e Domain. Schema SQL inalterado, `events.py` intocado. 183 testes passando em 0.58s, CI verde em Ubuntu + Windows. Próximo: B.1 (interface `DataSource` + extração `CemadenSource`). |
| 2026-05-16 | Camada 4 Parte B.1 concluída — interface `DataSource` + extração `CemadenSource` + infra de testes de contrato. Entregue em dois commits encadeados, ambos com CI verde: B.1.a (90aa977, infra: `sources/base.py` com `DataSource` ABC + `ResultadoColeta` frozen + `FalhaDeColeta` exception; `sources/contrato.py` com `verificar_contrato_data_source` parametrizada e 7 invariantes; `sources_fake.py` com `FakeDataSource` determinístico; 13 testes em `test_base.py`; 196 testes totais) e B.1.b (c9d9592, extração: `sources/cemaden.py` com `CemadenSource(DataSource)` migrando HTTP+retry+backoff+`_montar_alerta`+`_normalize_payload`+escopo+COBRADE de `monitor.py`; construtor keyword-only com `url`/`opener`/`timeout_segundos` injetáveis; Protocol local `_RespostaHTTP` PEP 544 para strict pelo contrato usado em vez de pela classe `HTTPResponse` concreta; `monitor.py` simplificado removendo `montar_alerta`/`normalize_alert_list`/`fetch_alertas_com_retry`/constantes/imports de transporte; `test_cemaden.py` com 20 testes (14 migrados + 6 novos de invariantes B.1: propagação de TypeError/AttributeError, FalhaDeColeta em rede/JSON/Unicode, fonte CEMADEN em alertas, coletado_em aware, contrato); `test_monitor.py` reduzido a 3 testes de orquestração com `CemadenSource.coletar` mockado; `test_contrato_cemaden.py` reescrito para usar `CemadenSource().coletar()` exercitando o fluxo completo; 205 testes totais, 0.66s local, 37s no CI). Importação circular evitada: `cemaden.py` importa de `sources.base` (não de `sources.__init__`). Decisões arquiteturais emergentes em B.1.b: Protocol local `_RespostaHTTP` e construtor keyword-only com transport injetável — registradas em §3 dentro do bloco B.1. Próximo: B.2 (orquestrador em `ingestao/orquestrador.py` com `RelatorioFonte`/`RelatorioIngestao`; `monitor.py` reduzido a entrypoint puro; testes migram para `tests/ingestao/`). |
