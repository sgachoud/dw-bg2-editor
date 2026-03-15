# dw-bg2-editor

A Python/PySide6 desktop editor for **Building Gadgets 2** schematic files.
Load a schematic, inspect which blocks it uses, and replace or remove them — then save the result back as a valid BG2 JSON file.

---

## Features

- **Open / Save** any BG2 schematic (`.json` format).
- **Block list** — shows every block type present in the schematic with its exact count, sortable and filterable.
- **Replace** — swap every occurrence of a block with another one.
  Block properties (wall connections, axis, orientation…) are preserved on all variants.
- **Remove** — replace every occurrence of a block with air.
- **Schematic summary** — dimensions and total block count displayed at a glance.
- **Unsaved-changes guard** — warns before closing or overwriting with unsaved edits.
- **CLI shortcut** — pass a file path as the first argument to open it directly on launch.

---

## Requirements

- Python 3.11+
- PySide6

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
python main.py                          # open the GUI, then use File > Open
python main.py path/to/schematic.json  # open a specific file immediately
```

### Workflow

1. **File → Open** (or `Ctrl+O`) — pick a BG2 `.json` schematic.
2. The block list on the left shows every block type and its count.
   Use the filter box above the table to search by name.
3. Select a row to work with that block:
   - **Replace** — type the replacement block ID (e.g. `minecraft:stone`) in the right panel and click *Apply Replace*.
   - **Remove** — click *Remove Block (→ Air)* to erase every occurrence.
4. **File → Save** (`Ctrl+S`) or **File → Save As** (`Ctrl+Shift+S`) to write the modified schematic.

---

## File format

BG2 schematics are JSON files with three top-level fields:

| Field | Description |
|-------|-------------|
| `name` | Schematic display name (may be empty) |
| `statePosArrayList` | SNBT string containing the block-state palette (`blockstatemap`), the 3-D block grid (`statelist`), and the bounding box (`startpos` / `endpos`) |
| `requiredItems` | Map of item IDs → required counts (recalculated on save) |

The `statePosArrayList` value uses Minecraft's **SNBT** (Stringified NBT) format:

```
{
  blockstatemap: [ {Name:"minecraft:air"}, {Name:"minecraft:stone", Properties:{…}}, … ],
  startpos: {X:-26, Y:0, Z:-26},
  endpos:   {X:0,  Y:33, Z:0},
  statelist: [I; 0, 0, 1, 2, … ]   ← indices into blockstatemap
}
```

The editor parses and re-serialises this format transparently.

---

## Project structure

```
dw-bg2-editor/
├── main.py           # Entry point
├── schematic.py      # SNBT parser + Schematic data model
├── ui/
│   └── main_window.py  # PySide6 main window
├── data/
│   └── schematic_example.json  # Example schematic for testing
└── requirements.txt
```

---

## License

See [LICENSE](LICENSE).
