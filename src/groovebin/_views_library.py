"""Terminal output for the pattern library commands."""

from __future__ import annotations

from .library.search import MAX_QUERY_BARS


def _cell(value: object, width: int) -> str:
    text = "" if value is None else f"{value:g}" if isinstance(value, float) else str(value)
    return text[:width].ljust(width)


def indexed(counts: dict) -> str:
    line = (f"  {counts['parsed']} pattern(s) indexed, {counts['failed']} not parsed, "
            f"{counts['duplicates']} duplicate(s) skipped")
    if counts["chords"] or counts["unread_chords"]:
        line += (f"\n  {counts['chords']} with chord labels beside {'it' if counts['chords'] == 1 else 'them'}, "
                 f"{counts['unread_chords']} chord file(s) not read")
    return line


def found(rows: list[dict], limit: int | None, *, distinct: int = 0) -> list[str]:
    """The listing; with ``distinct``, the query's distinct bars, rows lead with their distance from it."""
    head = f"{len(rows)} pattern(s){' (limit reached)' if limit and len(rows) == limit else ''}"
    if distinct > MAX_QUERY_BARS:
        head += f", compared on the first {MAX_QUERY_BARS} of the query's {distinct} distinct bars"
    lines = [head]
    for r in rows:
        kind = "fill" if r["is_fill"] else "beat" if r["is_beat"] else ""
        tempo = f"{r['tempo']:6.1f}" if r["tempo"] is not None else "     -"
        near = f"{r['distance']:5.1f}  " if "distance" in r else ""
        lines.append(f"  {near}{r['id']}  {_cell(r['meter'], 5)} {tempo}  {kind:4s}  {_cell(r['bars'], 3)} "
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
    if ph.level is not None:
        lines.append(f"  velocities levelled to a kick and snare median of {ph.level:g}")
    for k in ph.crashes:
        lines.append(f"  a crash on the downbeat of bar {k + 1}, after the fill")
    if ph.unmapped:
        kept = ", ".join(f"{pitch} x{n}" for pitch, n in ph.unmapped.items())
        lines.append(f"  no {ph.map} counterpart, {'pitch kept' if ph.unmapped_rule == 'keep' else 'dropped'}: {kept}")
    return lines
