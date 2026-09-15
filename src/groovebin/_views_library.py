"""Terminal output for the pattern library commands."""

from __future__ import annotations


def _cell(value: object, width: int) -> str:
    text = "" if value is None else f"{value:g}" if isinstance(value, float) else str(value)
    return text[:width].ljust(width)


def indexed(counts: dict) -> str:
    return (f"  {counts['parsed']} pattern(s) indexed, {counts['failed']} not parsed, "
            f"{counts['duplicates']} duplicate(s) skipped")


def found(rows: list[dict], limit: int | None) -> list[str]:
    lines = [f"{len(rows)} pattern(s){' (limit reached)' if limit and len(rows) == limit else ''}"]
    for r in rows:
        kind = "fill" if r["is_fill"] else "beat" if r["is_beat"] else ""
        tempo = f"{r['tempo']:6.1f}" if r["tempo"] is not None else "     -"
        lines.append(f"  {r['id']}  {_cell(r['meter'], 5)} {tempo}  {kind:4s}  {_cell(r['bars'], 3)} "
                     f"{_cell(r['role'], 10)} {_cell(r['category'], 16)} {_cell(r['group_name'], 24)} "
                     f"{_cell(r['variant'] or r['file'], 28)}")
    return lines


def picked(pool, ph) -> list[str]:
    fills = f", {len(pool.fills)} fill bar(s)" if pool.fills else ""
    left = f"; {pool.left_out} pattern(s) with a bar in another meter left out" if pool.left_out else ""
    lines = [f"pool: {len(pool.bars)} beat bar(s) from {len(pool.patterns)} pattern(s){fills}{left}",
             f"seed {ph.seed}: {len(ph.picks)} bar(s) of {ph.sig[0]}/{ph.sig[1]}, {len(ph.notes)} note(s) in {ph.map}"]
    for k, p in enumerate(ph.picks, 1):
        line = f"  bar {k:<3d} {'fill' if p.fill else 'beat'} {p.bar.id} bar {p.bar.index + 1} of {p.bar.count}"
        if p.fill:
            line += f", replaces {p.replaces.id} bar {p.replaces.index + 1}, {p.distance} onset step(s) from it"
        lines.append(line)
    if ph.unmapped:
        kept = ", ".join(f"{pitch} x{n}" for pitch, n in ph.unmapped.items())
        lines.append(f"  no {ph.map} counterpart, {'pitch kept' if ph.unmapped_rule == 'keep' else 'dropped'}: {kept}")
    return lines
