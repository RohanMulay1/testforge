"""A minimal CSV parser supporting quoted fields and escaped quotes."""


def parse_line(line: str, delimiter: str = ",") -> list[str]:
    if len(delimiter) != 1:
        raise ValueError("delimiter must be a single character")
    fields: list[str] = []
    field: list[str] = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    field.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                field.append(ch)
        else:
            if ch == '"':
                in_quotes = True
            elif ch == delimiter:
                fields.append("".join(field))
                field = []
            else:
                field.append(ch)
        i += 1
    if in_quotes:
        raise ValueError("unterminated quote")
    fields.append("".join(field))
    return fields


def parse(text: str, delimiter: str = ",") -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line == "":
            continue
        rows.append(parse_line(line, delimiter))
    return rows
