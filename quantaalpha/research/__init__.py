"""Incremental research-protocol extensions for upstream QuantaAlpha.

The original pipeline remains responsible for hypothesis generation, factor
implementation, Qlib execution and evolutionary exploration.
"""

from .memory import EconomicMemoryStore, MemoryProtocolError

__all__ = ["EconomicMemoryStore", "MemoryProtocolError"]

