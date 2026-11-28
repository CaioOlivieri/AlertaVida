# Verificação visual e de acessibilidade do site do acervo (#158)

Abre o site gerado num Chromium **sem rede**, nas larguras de celular (360 px)
e computador (1280 px), e procura rolagem lateral e violações do
[axe-core](https://github.com/dequelabs/axe-core) (WCAG 2.0/2.1 A e AA).
Ferramenta de desenvolvimento: não roda na VM, não entra nas dependências do
projeto e não é chamada pelo CI.

## O que é baixado, e por quê é confiável

| Peça | Versão fixa | Como é verificada |
|---|---|---|
| Imagem oficial do Playwright (Microsoft) | `playwright/python:v1.65.0-noble`, digest amd64 `sha256:3eb610b2…b493` | `FROM … @sha256:` no `Dockerfile` |
| `playwright` (pacote Python, mesmo projeto) | 1.65.0 | `pip --require-hashes` (`requirements.txt`) |
| `greenlet` (única dependência dele) | 3.5.6 | `pip --require-hashes` |
| `axe-core` (Deque) | 4.14.0, publicado em 2026-10-05 pelo CI do projeto | integridade SHA-512 do registro npm (passo 1) |

Critério: versões com pelo menos duas semanas, publicadas pelo próprio
mantenedor; nada vindo de wrapper de terceiros.

## Uso

```bash
cd scripts/verificacao_site

# 1. axe-core, conferindo a integridade publicada no npm
curl -s -o axe-core-4.14.0.tgz https://registry.npmjs.org/axe-core/-/axe-core-4.14.0.tgz
esperado=$(curl -s https://registry.npmjs.org/axe-core/4.14.0 | python3 -c "import json,sys;print(json.load(sys.stdin)['dist']['integrity'])")
obtido="sha512-$(openssl dgst -sha512 -binary axe-core-4.14.0.tgz | base64 -w0)"
[ "$esperado" = "$obtido" ] && tar -xzf axe-core-4.14.0.tgz --strip-components=1 package/axe.min.js && rm axe-core-4.14.0.tgz

# 2. a imagem (rede só aqui)
docker build -t alertavida-verif:pw1.65.0 .

# 3. auditoria — sem rede, só leitura, sem capacidades, usuário comum
SITE=/caminho/do/site; OUT=$(mktemp -d); chmod 777 "$OUT"; chmod -R a+rX "$SITE"
docker run --rm --network none --read-only --tmpfs /tmp:size=512m --shm-size=1g \
  --cap-drop ALL --security-opt no-new-privileges --user pwuser -e HOME=/tmp \
  -v "$SITE":/site:ro -v "$PWD":/verif:ro -v "$OUT":/out \
  alertavida-verif:pw1.65.0 python3 /verif/verificar_site.py \
  index.html municipio/3303906.html dados.html
```

Acrescente `-e ESQUEMA=dark` para o tema escuro. Saída: uma linha por página e
largura, um `relatorio-<esquema>.json` e prints da página inteira em `$OUT`;
código 1 se houver rolagem lateral ou violação. `axe.min.js` não é versionado
(baixe pelo passo 1).

## Resultado registrado (2026-11-28, exportação de 28/11)

Site antes do redesenho: 1 violação séria no celular
(`scrollable-region-focusable` — a tabela que rolava de lado não era alcançável
pelo teclado). Redesenho: 0 violações e nenhuma rolagem lateral nas três
páginas, nas duas larguras, nos temas claro e escuro.
