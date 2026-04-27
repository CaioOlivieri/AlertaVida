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
- **Validação de dados:** Pydantic (v2) — *a ser introduzido na Camada 2*
- **API Framework:** FastAPI — *a ser introduzido na Camada 5*
- **Banco de dados (início):** SQLite ✅
- **Banco de dados (futuro):** PostgreSQL (via Supabase)
- **Testes:** pytest ✅

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

### Camada 1 — Ingestão Resiliente de Dados ⚙️ EM PROGRESSO

**O que já está pronto:**
- [x] Consumo da API CEMADEN (`monitor.py`)
- [x] Persistência em SQLite (`database.py`)
- [x] Sistema de deduplicação por `cod_alerta`
- [x] Função pura `montar_alerta()` para mapeamento de campos
- [x] Tratamento de erros por alerta (não derruba o loop)
- [x] Testes unitários (`tests/test_monitor.py` — 6 testes passando)

**O que falta:**
- [ ] Loop de execução agendado (a cada 5–10 minutos)
- [ ] Retry com backoff exponencial em falhas de API
- [ ] Logs estruturados (JSON, com timestamp, nível, contexto)
- [ ] Contador de erros no relatório final

**Endpoint principal validado:**
`https://painelalertas.cemaden.gov.br/wsAlertas2`

Campos relevantes do JSON: `codigoalerta`, `datahoracriacao`, `tipoevento`, `nivel`, `estado`, `municipio`, coordenadas geográficas.

### Camada 2 — Modelagem de Domínio 🔜 PRÓXIMA
**Objetivo:** parar de trabalhar com dicionários soltos.

**Entidades a criar (Pydantic):**
- `Alerta` — id, codigo, tipo_evento, nivel_risco, municipio, estado, data_criacao, coordenadas, status
- `Municipio` — código IBGE, nome, estado, coordenadas
- `NivelRisco` — enum (BAIXO, MODERADO, ALTO, MUITO_ALTO)
- `TipoEvento` — enum (HIDROLOGICO, GEOLOGICO, METEOROLOGICO, etc.)

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
├── alertavida.db          ← gerado em runtime (gitignored)
├── database.py
├── monitor.py
└── tests/
    └── test_monitor.py
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
│   ├── ingestion/              ← Camada 1
│   │   ├── __init__.py
│   │   ├── scheduler.py
│   │   ├── persistence.py
│   │   └── retry.py
│   ├── domain/                 ← Camada 2
│   │   ├── __init__.py
│   │   ├── alerta.py
│   │   ├── municipio.py
│   │   └── enums.py
│   ├── events/                 ← Camada 3
│   │   ├── __init__.py
│   │   └── change_detector.py
│   ├── sources/                ← Camada 4
│   │   ├── __init__.py
│   │   ├── base.py             ← interface DataSource
│   │   ├── cemaden.py
│   │   ├── nasa_eonet.py
│   │   └── inmet.py
│   ├── api/                    ← Camada 5
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── routes/
│   └── notifications/          ← Camada 7
│       └── __init__.py
├── tests/
│   ├── ingestion/
│   ├── domain/
│   ├── events/
│   └── sources/
└── data/                       ← SQLite local (gitignored)
```

A migração da estrutura atual para a alvo acontece quando entrarmos na Camada 2 — não antes.

---

## 5. Princípios Técnicos (não negociáveis)

1. **TDD sempre que possível.** Antes de escrever código de uma nova função, escrever o teste que ela precisa passar. Especialmente importante porque o código gerado por IA pode parecer correto mas ter erros lógicos.
2. **Testes unitários em cada camada.** Sem testes, não há escala.
3. **Logs estruturados desde o início.** Saber o que o sistema faz em produção.
4. **Configuração via variáveis de ambiente.** Nunca hardcoded. Usar `.env` + `pydantic-settings`.
5. **Type hints em todas as funções.** Python 3.13 — sem desculpa.
6. **Pydantic para qualquer entrada/saída de dados externos.** Validação no limite do sistema.
7. **Commits frequentes e descritivos.** Cada mudança significativa = um commit.
8. **README mínimo mas presente.** Como rodar, arquitetura básica, decisões importantes.

---

## 6. Convenções do Projeto

### Nomenclatura
- Variáveis e funções: `snake_case`
- Classes: `PascalCase`
- Constantes: `UPPER_SNAKE_CASE`
- Português ou inglês? **Domínio em português** (Alerta, Municipio, NivelRisco), **infraestrutura em inglês** (scheduler, persistence, base).

### Imports
- Ordem: stdlib → terceiros → locais
- Imports absolutos sempre que possível

### Tratamento de erros
- Nunca usar `except:` genérico
- Sempre logar o erro com contexto
- Decidir explicitamente: re-raise, retry, ou fallback?

### Commits
- Formato: `tipo(escopo): descrição`
- Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Escopo: nome da camada quando aplicável (`camada-1`, `camada-2`, etc.)
- Exemplo: `feat(camada-1): integra monitor com database, dedup e testes unitários`

---

## 7. Decisões Arquiteturais Já Tomadas

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

---

## 8. Como Trabalhar com o Agente do Cursor

### Modo pipeline (preferido)
Em vez de pedir função por função, especifique **comportamento esperado completo**:

> ❌ "Me escreve uma função pra buscar dados do CEMADEN"
>
> ✅ "Implemente o módulo `src/sources/cemaden.py` que segue a interface `DataSource` (em `src/sources/base.py`). A função `fetch()` deve buscar dados do endpoint CEMADEN, validar com os modelos Pydantic em `src/domain/`, retornar uma lista de `Alerta`, e fazer retry com backoff exponencial em caso de falha. Escreva os testes em `tests/sources/test_cemaden.py` antes da implementação."

### Sempre que iniciar uma sessão
1. Garantir que o agente leu este `CONTEXT.md`
2. Apontar a camada/módulo onde está trabalhando
3. Definir o resultado esperado (não os passos)
4. Deixar o agente executar e voltar com o resultado

### Estrutura de prompt recomendada
1. **Contexto:** "Leia o CONTEXT.md antes de qualquer coisa."
2. **Objetivo:** o que se quer alcançar (não como)
3. **Requisitos funcionais:** comportamento esperado, casos de borda
4. **Requisitos não funcionais:** robustez, testes, convenções
5. **Critério de sucesso:** como saber que está pronto (ex: "rodar `python monitor.py` duas vezes e ver `[NOVO]` na primeira e `[JÁ VISTO]` na segunda")

---

## 9. Histórico de Mudanças

| Data | Mudança |
|---|---|
| 2026-04-27 | Criação inicial do CONTEXT.md |
| 2026-04-27 | Camada 1 parcial: integração monitor + database, deduplicação por cod_alerta, função pura montar_alerta, testes unitários (6 passando), repositório no GitHub |

> Adicione novas linhas aqui sempre que houver mudança arquitetural ou conclusão de camada.
