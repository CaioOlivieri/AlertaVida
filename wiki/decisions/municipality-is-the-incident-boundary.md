status: proposal
sources: maintainer decision 2026-11-16, production database (2026-11-16), issue #129
updated: 2026-11-16

# An Incidente never spans two municipalities

**Maintainer decision (2026-11-16):** the same rain hitting two
neighbouring municipalities is **two** incidents, not one. In the
maintainer's words: even if it is the same rain, the areas are affected in
different ways. Civil-defence response is organised per municipality, so the
municipality is the operational unit an `Incidente` describes.

This settles a gap [[projects/layer-5-correlation]] left open: "same
physical event" was defined with the cross-source example (one storm seen by
CEMADEN and EONET) but never said whether one storm over two municipalities
is one event or two.

## What it means for the decision core

Today `domain/correlacao.py` only *weighs* the IBGE code
(`PESO_CODIGO_IBGE = 0.35`). Two alerts in different municipalities can
still score into `VINCULA` through distance, time and type. The decision
becomes a **structural gate**, alongside the two that already exist
(incompatible types; `TipoEvento.INDETERMINADO`): both codes known and
different → `NAO_VINCULA`, regardless of score, outside #63's calibration.

When either code is missing — every EONET alert today — nothing changes:
distance stays the fallback until #62 places EONET points inside a
municipality.

Implementation is #129; this page moves to `implemented` with it.

## Measured on the production database (2026-11-16)

- **No existing incident contradicts the rule.** No CEMADEN incident has
  members from more than one municipality; all 43 `VINCULA` rows are EONET
  pairs (no IBGE code on either side).
- **746 `REVISAO` rows are CEMADEN pairs in different municipalities**,
  4–40 km apart. Under this decision they are `NAO_VINCULA` by definition.
  They stay in `correlacao_observacoes` as written (append-only); anyone
  reading them must know they predate the gate.

## Consequences

- **#71 goes dormant.** Its human-review target was those 746 rows; they need
  no label. What remains for review are cross-source pairs where a code is
  missing — 0 today.
- **#100 narrows.** For CEMADEN × CEMADEN, `mesmo_codibge = 0` now means
  "different municipalities" without ambiguity; the ambiguity remains only
  for pairs with a missing code.
- **#63's corpus shrinks to what matters.** Calibration only has to cover
  pairs the gate does not decide.
- **#62 gains weight.** Once EONET points get a municipality, the gate
  applies to cross-source pairs too.
