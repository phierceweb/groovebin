"""Pure note transforms: whole-part edits (`edits`), selection and operations on the selected notes
(`select`), and Logic's Transform presets over them (`presets`). Every function returns a new Part."""

from .edits import (GRIDS, TRIPLETS, Mask, PartWording, delete, grid_ticks, merge, note_lengths, note_value, quantize,
                    retimed, rounded, scale_velocity, shift, stretch, swing, transpose, velocity_curve)
from .presets import BY_NAME, PRESETS, THEORY, WHOLE_PART, Preset, operations, parse_value, run
from .select import FIELDS, OPS, Operation, Range, apply, apply_all, humanize, position_ticks, select, velocity_band
from .select_parse import parse_operation, parse_select, ticks_of
from .theory import Hold, Keys, change_key, diatonic, key_at, moved_key, quantized, scale_quantize, stepped

__all__ = ["GRIDS", "TRIPLETS", "note_value", "Mask", "PartWording", "delete", "grid_ticks", "merge", "note_lengths", "quantize", "retimed", "rounded",
           "scale_velocity", "shift", "stretch", "swing", "transpose", "velocity_curve",
           "BY_NAME", "PRESETS", "THEORY", "WHOLE_PART", "Preset", "operations", "parse_value", "run",
           "FIELDS", "OPS", "Operation", "Range", "apply", "apply_all", "humanize", "position_ticks", "select",
           "velocity_band", "parse_operation", "parse_select", "ticks_of",
           "Hold", "Keys", "change_key", "diatonic", "key_at", "moved_key", "quantized", "scale_quantize", "stepped"]
