"""
Building Gadgets 2 schematic data model.

Handles parsing, manipulation, and serialization of BG2 schematic JSON files.
The `statePosArrayList` field uses a Minecraft SNBT-like format.
"""

import json
import re
from typing import Optional


# ---------------------------------------------------------------------------
# SNBT parser
# ---------------------------------------------------------------------------

def parse_snbt(s: str):
    """Parse a Minecraft SNBT (Stringified NBT) string into Python objects."""
    pos = [0]  # use list so nested functions can mutate

    def skip_ws():
        while pos[0] < len(s) and s[pos[0]] in ' \t\n\r':
            pos[0] += 1

    def parse_value():
        skip_ws()
        c = s[pos[0]]
        if c == '{':
            return parse_object()
        elif c == '[':
            return parse_array()
        elif c == '"':
            return parse_string()
        else:
            return parse_primitive()

    def parse_object():
        pos[0] += 1  # consume '{'
        result = {}
        skip_ws()
        while pos[0] < len(s) and s[pos[0]] != '}':
            key = parse_key()
            skip_ws()
            pos[0] += 1  # consume ':'
            value = parse_value()
            result[key] = value
            skip_ws()
            if pos[0] < len(s) and s[pos[0]] == ',':
                pos[0] += 1
                skip_ws()
        pos[0] += 1  # consume '}'
        return result

    def parse_key():
        skip_ws()
        key = []
        while pos[0] < len(s) and s[pos[0]] not in ':,{}[]" \t\n\r':
            key.append(s[pos[0]])
            pos[0] += 1
        return ''.join(key)

    def parse_array():
        pos[0] += 1  # consume '['
        # Check for SNBT type prefix: I;, L;, B;
        if (pos[0] + 1 < len(s)
                and s[pos[0]] in 'ILB'
                and s[pos[0] + 1] == ';'):
            array_type = s[pos[0]]
            pos[0] += 2  # skip type prefix
        else:
            array_type = None

        result = []
        skip_ws()
        while pos[0] < len(s) and s[pos[0]] != ']':
            result.append(parse_value())
            skip_ws()
            if pos[0] < len(s) and s[pos[0]] == ',':
                pos[0] += 1
                skip_ws()
        pos[0] += 1  # consume ']'

        if array_type == 'I':
            return ('int_array', result)
        elif array_type == 'L':
            return ('long_array', result)
        elif array_type == 'B':
            return ('byte_array', result)
        return result

    def parse_string():
        pos[0] += 1  # consume opening '"'
        chars = []
        while pos[0] < len(s) and s[pos[0]] != '"':
            if s[pos[0]] == '\\':
                pos[0] += 1
                chars.append(s[pos[0]])
            else:
                chars.append(s[pos[0]])
            pos[0] += 1
        pos[0] += 1  # consume closing '"'
        return ''.join(chars)

    def parse_primitive():
        chars = []
        while pos[0] < len(s) and s[pos[0]] not in ':,{}[] \t\n\r':
            chars.append(s[pos[0]])
            pos[0] += 1
        token = ''.join(chars)
        # Strip trailing type suffixes (b, s, l, f, d)
        clean = token.rstrip('bslfdBSLFD')
        try:
            return int(clean)
        except ValueError:
            try:
                return float(clean)
            except ValueError:
                return token

    return parse_value()


def serialize_snbt(obj) -> str:
    """Serialize a Python object back to SNBT format."""
    if isinstance(obj, dict):
        parts = [f'{k}:{serialize_snbt(v)}' for k, v in obj.items()]
        return '{' + ','.join(parts) + '}'
    elif isinstance(obj, tuple) and len(obj) == 2 and obj[0] in ('int_array', 'long_array', 'byte_array'):
        prefix = {'int_array': 'I', 'long_array': 'L', 'byte_array': 'B'}[obj[0]]
        return f'[{prefix};' + ','.join(serialize_snbt(x) for x in obj[1]) + ']'
    elif isinstance(obj, list):
        return '[' + ','.join(serialize_snbt(x) for x in obj) + ']'
    elif isinstance(obj, str):
        escaped = obj.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(obj, bool):
        return 'true' if obj else 'false'
    elif isinstance(obj, int):
        return str(obj)
    elif isinstance(obj, float):
        return str(obj)
    else:
        return str(obj)


# ---------------------------------------------------------------------------
# Schematic model
# ---------------------------------------------------------------------------

def _make_item_key(block_name: str) -> str:
    """Build the requiredItems dict key for a block name."""
    mod = block_name.split(':')[0]
    return f'{mod}:Reference{{ResourceKey[minecraft:item / {block_name}]={block_name}}}'


class Schematic:
    def __init__(self):
        self.path: Optional[str] = None
        self.name: str = ''
        # List of blockstate dicts: {Name: str, Properties: {prop: val, ...}}
        self.blockstatemap: list[dict] = []
        # Flat list of ints – each is an index into blockstatemap
        self.statelist: list[int] = []
        self.startpos: dict = {'X': 0, 'Y': 0, 'Z': 0}
        self.endpos: dict = {'X': 0, 'Y': 0, 'Z': 0}
        self.required_items: dict = {}

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> 'Schematic':
        with open(path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)

        schem = cls()
        schem.path = path
        schem.name = raw.get('name', '')
        schem.required_items = raw.get('requiredItems', {})

        snbt_str = raw['statePosArrayList']
        parsed = parse_snbt(snbt_str)

        schem.blockstatemap = parsed.get('blockstatemap', [])
        schem.startpos = parsed.get('startpos', {'X': 0, 'Y': 0, 'Z': 0})
        schem.endpos = parsed.get('endpos', {'X': 0, 'Y': 0, 'Z': 0})

        raw_statelist = parsed.get('statelist', ('int_array', []))
        if isinstance(raw_statelist, tuple):
            schem.statelist = [int(x) for x in raw_statelist[1]]
        else:
            schem.statelist = [int(x) for x in raw_statelist]

        return schem

    def save(self, path: str):
        snbt_data = {
            'blockstatemap': self.blockstatemap,
            'endpos': self.endpos,
            'startpos': self.startpos,
            'statelist': ('int_array', self.statelist),
        }
        snbt_str = serialize_snbt(snbt_data)

        raw = {
            'name': self.name,
            'statePosArrayList': snbt_str,
            'requiredItems': self.required_items,
        }

        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)

        self.path = path

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def dimensions(self) -> tuple[int, int, int]:
        """Returns (size_x, size_y, size_z)."""
        sx = abs(self.endpos['X'] - self.startpos['X']) + 1
        sy = abs(self.endpos['Y'] - self.startpos['Y']) + 1
        sz = abs(self.endpos['Z'] - self.startpos['Z']) + 1
        return sx, sy, sz

    def get_block_counts(self) -> dict[str, int]:
        """
        Return {block_name: count} for all non-air blocks,
        sorted by count descending.
        """
        counts: dict[str, int] = {}
        for idx in self.statelist:
            if idx == 0:
                continue  # air
            if idx < len(self.blockstatemap):
                name = self.blockstatemap[idx].get('Name', 'unknown')
                counts[name] = counts.get(name, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

    def get_blockstate_indices(self, block_name: str) -> list[int]:
        """Return all blockstatemap indices whose Name matches block_name."""
        return [
            i for i, bs in enumerate(self.blockstatemap)
            if bs.get('Name') == block_name
        ]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def replace_block(self, old_name: str, new_name: str):
        """
        Replace all blockstatemap entries named old_name with new_name.
        Properties are kept intact (wall connections, axis, etc.).
        requiredItems is recalculated afterwards.
        """
        if old_name == new_name:
            return
        for bs in self.blockstatemap:
            if bs.get('Name') == old_name:
                bs['Name'] = new_name
        self._recalculate_required_items()

    def remove_block(self, block_name: str):
        """
        Set all statelist entries for block_name to 0 (air).
        requiredItems is recalculated afterwards.
        """
        target_indices = set(self.get_blockstate_indices(block_name))
        for i, idx in enumerate(self.statelist):
            if idx in target_indices:
                self.statelist[i] = 0
        self._recalculate_required_items()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalculate_required_items(self):
        """Rebuild requiredItems from current statelist / blockstatemap."""
        counts = self.get_block_counts()
        new_items: dict[str, int] = {}
        for name, count in counts.items():
            key = _make_item_key(name)
            new_items[key] = count
        self.required_items = new_items

    # ------------------------------------------------------------------
    # Undo / redo support
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a lightweight copy of all mutable state."""
        import copy
        return {
            'blockstatemap': copy.deepcopy(self.blockstatemap),
            'statelist': self.statelist.copy(),
            'required_items': self.required_items.copy(),
        }

    def restore(self, snap: dict):
        """Restore mutable state from a snapshot produced by :meth:`snapshot`."""
        import copy
        self.blockstatemap = copy.deepcopy(snap['blockstatemap'])
        self.statelist = snap['statelist'].copy()
        self.required_items = snap['required_items'].copy()
