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

- **Parte A.2 — Aditivo: taxonomia COBRADE com proveniência de classificação**:
  - Novo módulo `src/alertavida/domain/cobrade.py` com tabela de mapeamento `EVENTO_CEMADEN_PARA_COBRADE` (apenas 2 entradas, baseado em inspeção empírica de 240 alertas em 4 amostras de 01-02/05/2026): `Risco Hidrológico → 1.2.0.0.0`, `Movimentos de Massa → 1.1.3.0.0`
  - Novo enum `FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) registrando proveniência do `cobrade_codigo`
  - Novo campo `cobrade_codigo: str | None` no domínio `Alerta`
  - Novo campo `fonte_classificacao: FonteClassificacao` no domínio `Alerta` (default INDETERMINADA)
  - Nova coluna `cobrade_codigo TEXT NULL` na tabela `alertas`
  - Nova coluna `fonte_classificacao TEXT NOT NULL DEFAULT 'INDETERMINADA'` na tabela `alertas`
  - Migração via `_migrar_banco()` (aditiva, não destrutiva)
  - Testes do mapper e do parser CEMADEN populando os novos campos

- **Parte B — `CemadenSource` como `DataSource`** (após A.1 + A.2):
  - Refator de `monitor.py` em orquestrador real
  - Lógica CEMADEN específica migra para `sources/cemaden.py`
  - Pode rodar em paralelo com A.2 sem conflito

- **Parte C — `NasaEonetSource`** (após Parte B):
  - Nova fonte implementada como `DataSource`
  - Mapeamento de categorias EONET para subgrupos COBRADE em `cobrade.py`
  - Ingestão global, classificação geográfica via `EscopoGeografico`

**Ordem de execução**: A.1 → A.2 → B → C. A.1 é destrutivo (PK composta, enum mudando valores). A.2 é puramente aditivo (campo nullable, coluna nova nullable, módulo novo). Aditivos sobre destrutivos evitam conflito de migration.

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
| `monitor.py` vira orquestrador multi-fonte (Camada 4) | Continua sendo o entrypoint (`python -m alertavida.monitor`); lógica CEMADEN específica migra para `sources/cemaden.py`; loop sobre `[CemadenSource(), NasaEonetSource(), ...]`. Testes existentes continuam importando `executar_ingestao()`. |
| Indexação espacial obrigatória na Camada 5 | SQLite R-Tree na fase atual; PostGIS quando migrarmos para Postgres na Camada 6. Não relevante para Camadas 1-4. |
| Refator do enum `TipoEvento` para subgrupos COBRADE | Domínio dependia da terminologia de uma fonte específica (CEMADEN), violando Dependency Inversion. Refator alinha com padrão internacional COBRADE/EM-DAT — `HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`. Cada `DataSource` implementa mapeamento próprio para esses valores. Janela de baixo custo: feito agora, antes de Parte B/C triplicarem a superfície de mudança. |
| `cobrade_codigo` + enum `FonteClassificacao` no Alerta | Campo `cobrade_codigo: str \| None` preserva código no nível de subgrupo. Enum `FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) registra proveniência da classificação. Trilha de auditoria preservada quando Camada 5 reclassificar para subtipos. Open/Closed: novas estratégias de classificação só adicionam valores ao enum. |
| Granularidade COBRADE limitada ao subgrupo na Camada 4 | Inspeção empírica de 4 amostras CEMADEN (240 alertas, 01-02/05/2026) confirmou ausência de campo COBRADE explícito e taxonomia limitada a 2 tipos × 3 níveis. Distinção entre subtipos (inundação vs enxurrada vs alagamento; quedas vs deslizamentos vs corridas) exige topografia, densidade urbana, INMET. Inferir heuristicamente na Camada 4 violaria honestidade dos dados (§6.10). Subtipos são problema da Camada 5. |
| Subdivisão da Camada 4 Parte A em A.1 (destrutivo) + A.2 (aditivo COBRADE) | A.1 quebra surrogate key, enum, refator de domínio. A.2 é aditivo puro: coluna nullable, módulo novo, sem reescrita. Cada parte com narrativa coerente e independentemente reversível. Ordem A.1 → A.2 evita conflito de migration. A.2 pode rodar em paralelo com Parte B. |
| Fixtures CEMADEN versionadas em `tests/fixtures/cemaden/` | 4 amostras capturadas em 01-02/05/2026 (durante enchente real em PE) viram fixtures de teste de regressão. Uso por nível de teste: parsing usa 1 fixture, integração do `ChangeDetector` usa 2 fixtures consecutivas com diff controlado, contrato real continua via `@integration` no endpoint vivo. README documenta origem e contexto de cada fixture. |
| Pasta `data/` é runtime/state, ignorada via gitignore com exceção `.gitkeep` | Banco SQLite, payloads brutos, logs do inspector, backups — nada canônico. Estratégia uniforme: `data/*` ignorado, estrutura preservada via `.gitkeep`. Fixtures canônicas vivem em `tests/fixtures/`, não em `data/samples/`. Single Responsibility aplicado a estrutura de pastas. |

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
| 2026-05-07 | Camada 4 Parte A.1 — A.1.1, A.1.3 commitadas e CI verde. A.1.2 commitada LOCAL (não pushed). A.1.4 pendente. Push de A.1.2 + A.1.4 será feito junto após A.1.4 commitada.
