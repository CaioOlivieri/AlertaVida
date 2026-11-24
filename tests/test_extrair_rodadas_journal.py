"""Testes de scripts/extrair_rodadas_journal.py (issue #158)."""

import io
from datetime import UTC, datetime

from scripts.extrair_rodadas_journal import RodadaFonte, escrever_csv, extrair, main, resumir

_P = "2026-09-28T20:49:22-03:00 host python[159]: "

_JOURNAL = [
    f"{_P}2026-09-28 20:49:20,485 [INFO] apscheduler.scheduler: Adding job tentatively",
    f"{_P}2026-09-28T23:49:20.488506+00:00: rodada concluída",
    f"{_P}  CEMADEN: 23 coletados (0 novos, 0 atualizados, 0 reativados, 23 inalterados, "
    "0 descartados) [incidentes: 0 criados] em 0.46s",
    f"{_P}  EONET: FALHA de coleta (12.01s)",
    f"{_P}Total: 23 alertas",
    "2026-11-24T00:41:22-00:00 vm python[22207]:   INMET (avisos): 10 vigentes ou futuros "
    "(0 novos, 0 descartados) em 2.19s",
    "2026-11-24T01:11:22+00:00 vm python[22207]:   INMET (avisos): FALHA de coleta (3.00s)",
]


def _instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto).astimezone(UTC)


class TestExtrair:
    def test_rodada_usa_o_agora_do_cabecalho_em_utc(self):
        rodadas = list(extrair(_JOURNAL))
        cemaden = next(r for r in rodadas if r.fonte == "CEMADEN")
        assert cemaden == RodadaFonte(_instante("2026-09-28T23:49:20+00:00"), "CEMADEN", 23, False)

    def test_falha_de_fonte_fica_registrada_sem_contagem(self):
        eonet = next(r for r in extrair(_JOURNAL) if r.fonte == "EONET")
        assert eonet.falha and eonet.coletados is None
        assert eonet.instante_utc == _instante("2026-09-28T23:49:20+00:00")

    def test_inmet_usa_o_carimbo_do_journal(self):
        inmet = [r for r in extrair(_JOURNAL) if r.fonte == "INMET"]
        assert inmet == [
            RodadaFonte(_instante("2026-11-24T00:41:22+00:00"), "INMET", 10, False),
            RodadaFonte(_instante("2026-11-24T01:11:22+00:00"), "INMET", None, True),
        ]

    def test_linha_de_fonte_fora_de_um_bloco_e_ignorada(self):
        solta = [f"{_P}  CEMADEN: 5 coletados (5 novos) em 0.1s"]
        assert list(extrair(solta)) == []

    def test_total_encerra_o_bloco(self):
        depois = [*_JOURNAL[1:5], f"{_P}  CEMADEN: 9 coletados (9 novos) em 0.1s"]
        assert [r.coletados for r in extrair(depois) if r.fonte == "CEMADEN"] == [23]


class TestSaida:
    def test_csv_ordenado_sem_duplicatas(self):
        rodadas = list(extrair(_JOURNAL + _JOURNAL))
        saida = io.StringIO()
        escrever_csv(rodadas, saida)
        assert saida.getvalue().splitlines() == [
            "instante_utc,fonte,coletados,falha",
            "2026-09-28T23:49:20Z,CEMADEN,23,0",
            "2026-09-28T23:49:20Z,EONET,,1",
            "2026-11-24T00:41:22Z,INMET,10,0",
            "2026-11-24T01:11:22Z,INMET,,1",
        ]

    def test_resumo_conta_rodadas_de_alertas_nao_fontes(self):
        assert resumir(extrair(_JOURNAL)).splitlines() == [
            "rodadas de alertas: 1 (2026-09-28T23:49Z → 2026-09-28T23:49Z)",
            "  2026-09: 1",
        ]

    def test_main_le_arquivo_e_escreve_csv(self, tmp_path, capsys):
        entrada = tmp_path / "journal.txt"
        entrada.write_text("\n".join(_JOURNAL) + "\n", encoding="utf-8")
        saida = tmp_path / "rodadas.csv"
        assert main(["--entrada", str(entrada), "--saida", str(saida)]) == 0
        assert saida.read_text(encoding="utf-8").count("\n") == 5
        assert "rodadas de alertas: 1" in capsys.readouterr().out
