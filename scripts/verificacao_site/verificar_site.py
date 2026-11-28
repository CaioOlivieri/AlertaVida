"""Audita páginas do site do acervo num Chromium sem rede (issue #158).

Roda DENTRO do container descrito em `README.md` — nunca no host nem na VM.
Para cada página, nas larguras de celular (360 px) e computador (1280 px):

- rolagem lateral da página inteira (`scrollWidth > clientWidth`);
- violações do axe-core (WCAG 2.0/2.1 A e AA + boas práticas);
- um print da página inteira.

Lê `/site` (montado só para leitura) e `/verif/axe.min.js`; escreve só em
`/out`. `ESQUEMA=dark` audita o tema escuro. Sai com 1 se houver rolagem
lateral ou violação.
"""

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path("/site")
OUT = Path("/out")
AXE = Path("/verif/axe.min.js")
LARGURAS = {"celular": (360, 780), "desktop": (1280, 900)}
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]


def main(paginas: list[str]) -> int:
    esquema = os.environ.get("ESQUEMA", "light")
    resultado: dict = {}
    problemas = 0
    with sync_playwright() as p:
        # O container já é o isolamento (sem rede, só leitura, sem capacidades).
        navegador = p.chromium.launch(args=["--no-sandbox"])
        for nome, (largura, altura) in LARGURAS.items():
            contexto = navegador.new_context(
                viewport={"width": largura, "height": altura},
                device_scale_factor=2 if nome == "celular" else 1,
                is_mobile=nome == "celular",
                has_touch=nome == "celular",
                color_scheme=esquema,
            )
            for relativo in paginas:
                pagina = contexto.new_page()
                pagina.goto((SITE / relativo).as_uri())
                larguras = pagina.evaluate(
                    "() => [document.documentElement.scrollWidth,"
                    " document.documentElement.clientWidth]"
                )
                arquivo = relativo.replace("/", "_").removesuffix(".html")
                pagina.screenshot(path=str(OUT / f"{arquivo}-{nome}-{esquema}.png"), full_page=True)
                pagina.add_script_tag(path=str(AXE))  # o site em si não tem JavaScript
                axe = pagina.evaluate(
                    "async (tags) => await axe.run(document,"
                    " {runOnly: {type: 'tag', values: tags}})",
                    TAGS,
                )
                violacoes = [
                    {
                        "id": v["id"],
                        "impacto": v["impact"],
                        "ocorrencias": len(v["nodes"]),
                        "exemplo": v["nodes"][0]["target"] if v["nodes"] else None,
                        "ajuda": v["help"],
                    }
                    for v in axe["violations"]
                ]
                rolagem = larguras[0] > larguras[1]
                problemas += int(rolagem) + len(violacoes)
                resultado.setdefault(relativo, {})[nome] = {
                    "rolagem_horizontal": rolagem,
                    "scrollWidth_clientWidth": larguras,
                    "violacoes": violacoes,
                }
                ids = [f"{v['id']}({v['impacto']},{v['ocorrencias']})" for v in violacoes]
                print(
                    f"{relativo:28} {nome:8} {esquema:5} rolagem={rolagem!s:5} "
                    f"{larguras} axe={ids or 'ok'}"
                )
                pagina.close()
            contexto.close()
        navegador.close()
    (OUT / f"relatorio-{esquema}.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
