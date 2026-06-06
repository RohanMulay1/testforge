"""Temperature conversions with absolute-zero validation."""

ABSOLUTE_ZERO_C = -273.15


def celsius_to_fahrenheit(c: float) -> float:
    _check_above_absolute_zero(c)
    return c * 9 / 5 + 32


def fahrenheit_to_celsius(f: float) -> float:
    c = (f - 32) * 5 / 9
    _check_above_absolute_zero(c)
    return c


def celsius_to_kelvin(c: float) -> float:
    _check_above_absolute_zero(c)
    return c - ABSOLUTE_ZERO_C


def kelvin_to_celsius(k: float) -> float:
    if k < 0:
        raise ValueError("kelvin cannot be negative")
    return k + ABSOLUTE_ZERO_C


def _check_above_absolute_zero(c: float) -> None:
    if c < ABSOLUTE_ZERO_C:
        raise ValueError("temperature below absolute zero")
