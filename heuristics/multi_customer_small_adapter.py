"""Compatibility wrapper for the renamed precomputed-matrix adapter.

New code should import :mod:`heuristics.precomputed_matrix_adapter`.
"""

from __future__ import annotations

if __package__:
    from .precomputed_matrix_adapter import *  # noqa: F401,F403
    from .precomputed_matrix_adapter import main
else:  # pragma: no cover - direct script execution
    from precomputed_matrix_adapter import *  # noqa: F401,F403
    from precomputed_matrix_adapter import main


if __name__ == "__main__":
    main()
