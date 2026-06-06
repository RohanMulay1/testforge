"""A safe expression calculator (Shunting-yard, integers and floats)."""

import operator

_OPS = {
    "+": (1, operator.add),
    "-": (1, operator.sub),
    "*": (2, operator.mul),
    "/": (2, operator.truediv),
}


def tokenize(expr: str) -> list[str]:
    tokens: list[str] = []
    num: list[str] = []
    for ch in expr:
        if ch.isdigit() or ch == ".":
            num.append(ch)
        elif ch in _OPS or ch in "()":
            if num:
                tokens.append("".join(num))
                num = []
            tokens.append(ch)
        elif ch.isspace():
            if num:
                tokens.append("".join(num))
                num = []
        else:
            raise ValueError(f"invalid character: {ch}")
    if num:
        tokens.append("".join(num))
    return tokens


def evaluate(expr: str) -> float:
    output: list[float] = []
    ops: list[str] = []

    def apply():
        op = ops.pop()
        if len(output) < 2:
            raise ValueError("malformed expression")
        b = output.pop()
        a = output.pop()
        if op == "/" and b == 0:
            raise ZeroDivisionError("division by zero")
        output.append(_OPS[op][1](a, b))

    for tok in tokenize(expr):
        if tok in _OPS:
            while ops and ops[-1] != "(" and _OPS[ops[-1]][0] >= _OPS[tok][0]:
                apply()
            ops.append(tok)
        elif tok == "(":
            ops.append(tok)
        elif tok == ")":
            while ops and ops[-1] != "(":
                apply()
            if not ops:
                raise ValueError("mismatched parentheses")
            ops.pop()
        else:
            output.append(float(tok))

    while ops:
        if ops[-1] == "(":
            raise ValueError("mismatched parentheses")
        apply()
    if len(output) != 1:
        raise ValueError("malformed expression")
    return output[0]
