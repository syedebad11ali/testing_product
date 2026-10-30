"""Per-conversation memory: remembers budget, area, type and purpose the user mentioned.

Values are extracted by the offline engine's resolvers, so only known area names, type names
and numbers are ever stored (nothing free-text), which also makes them safe to hand to the model.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from backend.records.text import norm


@dataclass
class Memory:
    area: str = ""
    property_type: str = ""
    budget_max: float = 0.0
    purpose: str = ""
    block: int = 0

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}

    def summary(self) -> str:
        bits = []
        if self.area: bits.append(f"area={self.area}")
        if self.property_type: bits.append(f"type={self.property_type}")
        if self.budget_max: bits.append(f"budget_max_pkr={int(self.budget_max)}")
        if self.purpose: bits.append(f"purpose={self.purpose}")
        if self.block: bits.append(f"block={self.block}")
        return ", ".join(bits)


def update(memory: Memory, engine, text: str) -> Memory:
    """Fold what the message says into ``memory`` (new facts replace old ones)."""
    t = norm(text)
    area, ptype = engine._area(t), engine._type(t)
    if area:
        name = engine.s.area_names[area]
        if memory.area and memory.area != name:
            memory.block = 0      # a block number only makes sense inside the area it was given for
        memory.area = name
    blk = re.search(r"\bblock\s*(\d{1,3})\b", t)
    if blk: memory.block = int(blk.group(1))
    if ptype: memory.property_type = engine.s.type_names[ptype]
    budget = engine._money(t, "under|below|less than|max|upto|up to|budget|within|around")
    if budget: memory.budget_max = budget
    if re.search(r"\binvest(ment|ing)?\b", t): memory.purpose = "invest"
    elif re.search(r"\b(rent|rental)\b", t): memory.purpose = "rent"
    elif re.search(r"\b(buy|purchase|live|own use)\b", t): memory.purpose = "buy"
    return memory
