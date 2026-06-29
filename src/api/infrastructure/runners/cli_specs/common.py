from __future__ import annotations


def number_arg(value: int | float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)
