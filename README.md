# GRvx Cutter

Open-source [Glyphs](https://glyphsapp.com) script that cuts a geometric semicircle into a stem (straight or diagonal). Built for type designers; published as a reusable tool and portfolio piece by [Pasquale de Sario](https://pasqualedesario.eu).

**Version:** 0.1.0 · **License:** MIT · **UI:** Italiano / English

## Requirements

- [Glyphs](https://glyphsapp.com) 3 or 4
- [Vanilla](https://github.com/robotools/vanilla) (for the floating panel; without it the script still runs a default “inside” cut)

## Install

1. Download or clone this repository.
2. Copy the `GRvx` folder into your Glyphs Scripts directory:

   - **Glyphs 4:** `~/Library/Application Support/Glyphs 4/Scripts/`
   - **Glyphs 3:** `~/Library/Application Support/Glyphs/Scripts/`

3. In Glyphs: **Script → Reload Scripts** (or restart Glyphs).
4. Run **Script → GRvx → GRvx Cutter**.

## Usage

1. Open a glyph in Edit View.
2. Select **exactly two on-curve nodes** on opposite sides of the stem (the ends of the cut diameter).
3. The **goniometer** preview shows the circle (toggle in the panel).
4. Choose cut direction: **inside** or **outside** the stem.
5. Click **Apply**.

The diameter is aligned perpendicular to the stem axis when the stem can be recognized.

## Known limits

- The span between the two nodes must be short (at most 14 intermediate nodes); select the diameter ends, not a long outline arc.
- Stem detection needs roughly parallel edges at the two nodes; unusual junctions may fail with “stem not recognized”.
- Very small radii are rejected.
- Both nodes must belong to the **same** path.
- Goniometer canvas status strings are currently Italian-only; the panel UI is fully bilingual.

## Development

```text
GRvx-Cutter/
├── GRvx/
│   └── GRvx Cutter.py   # Glyphs script (MenuTitle: GRvx Cutter)
├── LICENSE
└── README.md
```

Author: Pasquale de Sario · https://pasqualedesario.eu
