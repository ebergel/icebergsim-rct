"""I/O edge of ICEBERGSIM: file loading and result export (ARCHITECTURE §3.11).

This is the only package allowed to touch the filesystem. The engine modules never do.
"""

from icebergsim.io.export import export_result, result_to_dict, summary_row, write_rows_csv
from icebergsim.io.files import load_definition

__all__ = [
    "export_result",
    "load_definition",
    "result_to_dict",
    "summary_row",
    "write_rows_csv",
]
