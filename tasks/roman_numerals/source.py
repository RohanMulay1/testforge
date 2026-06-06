"""Integer <-> Roman numeral conversion (1..3999)."""

_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

_SYMBOLS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def to_roman(n: int) -> str:
    if not isinstance(n, int):
        raise TypeError("n must be an int")
    if n < 1 or n > 3999:
        raise ValueError("n must be in range 1..3999")
    out = []
    for value, symbol in _VALUES:
        count, n = divmod(n, value)
        out.append(symbol * count)
    return "".join(out)


def from_roman(s: str) -> int:
    if not s:
        raise ValueError("empty string")
    s = s.upper()
    total = 0
    prev = 0
    for ch in reversed(s):
        if ch not in _SYMBOLS:
            raise ValueError(f"invalid symbol: {ch}")
        value = _SYMBOLS[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total
