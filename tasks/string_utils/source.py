"""Small string utilities with edge-case behavior."""


def slugify(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    cleaned = []
    for ch in text.strip().lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in (" ", "-", "_"):
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def is_palindrome(text: str) -> bool:
    filtered = [c.lower() for c in text if c.isalnum()]
    return filtered == filtered[::-1]


def truncate(text: str, length: int, suffix: str = "...") -> str:
    if length < 0:
        raise ValueError("length must be non-negative")
    if len(text) <= length:
        return text
    if length <= len(suffix):
        return text[:length]
    return text[: length - len(suffix)] + suffix


def count_words(text: str) -> int:
    return len(text.split())
