"""Resource limits for GraphQL operations, with optional environment overrides.

Every limit lives here so it is easy to find and change. The README explains
how each one is measured.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    # Nested selection levels below the root (introspection fields are ignored).
    max_depth: int = 6
    # Estimated upstream work per operation; see complexity.py for the weights.
    max_cost: int = 100
    # Aliased fields in the whole document, across all operations and fragments.
    max_aliases: int = 30
    # Lexical tokens in the document; the parser stops once this is exceeded.
    max_tokens: int = 1000

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Limits":
        """Read optional overrides, e.g. MLB_GRAPHQL_MAX_COST=150."""
        defaults = cls()
        values = {}
        for name in ("max_depth", "max_cost", "max_aliases", "max_tokens"):
            variable = f"MLB_GRAPHQL_{name.upper()}"
            raw = environ.get(variable)
            if raw is None:
                values[name] = getattr(defaults, name)
                continue
            try:
                value = int(raw)
            except ValueError:
                raise ValueError(f"{variable} must be an integer, got {raw!r}") from None
            if value < 1:
                raise ValueError(f"{variable} must be at least 1, got {value}")
            values[name] = value
        return cls(**values)
