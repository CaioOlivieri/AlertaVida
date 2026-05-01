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
- **Testes:** pytest ✅
- **Empacotamento:** pyproject.toml + setuptools (src layout) ✅

### Frontend (futuro)
- **Framework:** Next.js (com suporte nativo a PWA)
- **Mapa:** Leaflet
- **Auth + DB cloud:** Supabase

### Versionamento
- **Git** desde a primeira linha ✅
- **Repositório:** https://github.com/CaioOlivieri/AlertaVida (privado)
- Convenção de commits: `tipo(escopo): descrição` em português (ex: `feat(camada-1): integra monitor com database`)

---

## 3. Arquitetura em 7 Camadas

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

### Camada 2 — Modelagem de Domínio ⚙️ EM PROGRESSO
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
- [ ] **Parte 3** — Integração: `montar_alerta()` retorna `Alerta`, `database.py` recebe `Alerta`

### Camada 3 — Detecção de Mudanças e Eventos 🔒 BLOQUEADA (depende de 1 e 2)
**Padrão arquitetural:** Event-Driven Architecture.

**Eventos internos a emitir:**
- `AlertaCriado`
- `AlertaAtualizado`
- `AlertaResolvido`

Comparar snapshot atual com anterior, emitir evento correspondente, desacoplar ingestão de consumidores.

### Camada 4 — Fontes Múltiplas 🔒 BLOQUEADA
**Padrão arquitetural:** Adapter.

Interface comum `DataSource` com implementações:
- `CemadenSource` (já temos protótipo em `monitor.py`)
- `NasaEonetSource`
- `InmetSource`
- `InpeSource`

Benefício: se uma fonte cair, sistema continua. Adicionar nova fonte = implementar interface.

### Camada 5 — API Própria (FastAPI) 🔒 BLOQUEADA
**Endpoints planejados:**
- `GET /alertas/ativos`
- `GET /alertas/por-municipio/{ibge}`
- `GET /alertas/historico`
- `GET /alertas/proximos?lat={lat}&lon={lon}&raio={km}`

Documentação automática via OpenAPI/Swagger (built-in do FastAPI).

Quando integrarmos com FastAPI, o `BackgroundScheduler` já existente continua funcionando — não é necessário trocar.

### Camada 6 — Interface Visual (Next.js + Leaflet) 🔒 BLOQUEADA
PWA com mapa interativo, lista de alertas, filtros, instalável como app no celular.

### Camada 7 — Motor de Notificação 🔒 BLOQUEADA
**Curto prazo:** Web Push (nativo do PWA).
**Médio prazo:** WhatsApp Business API, Email (SMTP), Telegram.
**Longo prazo:** Cell Broadcast (via parceria com operadoras/governo).

---

## 4. Estrutura de Pastas

### Estado atual
```
alertavida/
├── .gitignore
├── CONTEXT.md
├── README.md
├── pyproject.toml
├── data/
│   └── alertavida.db          ← gerado em runtime (gitignored)
├── src/
│   └── alertavida/
│       ├── __init__.py
│       ├── monitor.py
│       ├── database.py
│       └── scheduler.py
└── tests/
    ├── __init__.py
    ├── test_monitor.py
    └── test_scheduler.py
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
│       ├── api/                    ← Camada 5
│       │   ├── __init__.py
│       │   ├── main.py
│       │   └── routes/
│       └── notifications/          ← Camada 7
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