"""Evaluate XLSForm expressions (``${name}`` syntax) on one row, with XPath 1.0 values.

``compile_expression(expr)`` parses once and returns ``fn(row)``; ``row`` supplies
``ref(name)`` (a field's value: None when empty, select_multiple as space-separated
codes) and ``index()`` (the current repeat instance). Empty values compare as ``''``,
so ``${x} = 1`` is false and ``${x} != 1`` true when ``x`` is empty, as on the device.
Anything outside the supported subset raises ``UnsupportedExpression`` at compile time.
"""

import functools
import math
import re
from collections.abc import Callable

Value = str | float | bool | None


class UnsupportedExpression(ValueError):
    """The expression uses syntax or a function the evaluator does not implement."""


_TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<ref>\$\{[^}]+\})
      | (?P<num>\d+(?:\.\d*)?|\.\d+)
      | (?P<str>'[^']*'|"[^"]*")
      | (?P<op>!=|<=|>=|=|<|>|\+|-|\*|\(|\)|,)
      | (?P<name>[A-Za-z_][\w\-]*(?<!-))
      | (?P<dot>\.(?!\.))
    )""",
    re.VERBOSE,
)

_TRAILING_SPACE = re.compile(r"\s*\Z")

_BINARY = {
    "or": 1,
    "and": 2,
    "=": 3,
    "!=": 3,
    "<": 4,
    "<=": 4,
    ">": 4,
    ">=": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "div": 6,
    "mod": 6,
}


def _number(v: Value) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v.strip()) if v else math.nan
    except ValueError:
        return math.nan


def to_number(v: Value) -> float:
    """Return ``v`` as an XPath number (NaN when it is not one)."""
    return _number(v)


def _string(v: Value) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return str(v)


def _boolean(v: Value) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0 and not math.isnan(v)
    return bool(v)


def _equals(a: Value, b: Value) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return _boolean(a) == _boolean(b)
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        return _number(a) == _number(b)
    return _string(a) == _string(b)


def _compare(op: str, a: Value, b: Value) -> bool:
    if op == "=":
        return _equals(a, b)
    if op == "!=":
        return not _equals(a, b)
    x, y = _number(a), _number(b)
    return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


def _arith(op: str, a: Value, b: Value) -> float:
    x, y = _number(a), _number(b)
    if op == "+":
        return x + y
    if op == "-":
        return x - y
    if op == "*":
        return x * y
    if y == 0:
        return math.nan
    return x / y if op == "div" else math.fmod(x, y)


def _codes(v: Value) -> list[str]:
    return _string(v).split()


def _items(separator: Value, items: Value) -> list[str]:
    """Split a SurveyCTO list (``item-at``, ``count-items``, ...); empty: no items."""
    text = _string(items)
    return text.split(_string(separator)) if text else []


def _at(items: list[str], index: Value) -> str:
    """Return the item at a 0-based index, or empty text past the end."""
    i = int(_number(index))
    return items[i] if 0 <= i < len(items) else ""


_FUNCTIONS: dict[str, tuple[int, int, Callable[..., Value]]] = {
    # name: (min args, max args, implementation on evaluated args)
    "selected": (2, 2, lambda a, b: _string(b) in _codes(a)),
    "count-selected": (1, 1, lambda a: float(len(_codes(a)))),
    "not": (1, 1, lambda a: not _boolean(a)),
    "true": (0, 0, lambda: True),
    "false": (0, 0, lambda: False),
    "boolean": (1, 1, _boolean),
    "number": (1, 1, _number),
    "string": (1, 1, _string),
    "int": (
        1,
        1,
        lambda a: (
            float(math.trunc(_number(a))) if not math.isnan(_number(a)) else math.nan
        ),
    ),
    "round": (1, 2, lambda a, n=0: round(_number(a), int(_number(n)))),
    "string-length": (1, 1, lambda a: float(len(_string(a)))),
    "concat": (1, 99, lambda *xs: "".join(_string(x) for x in xs)),
    "contains": (2, 2, lambda a, b: _string(b) in _string(a)),
    "starts-with": (2, 2, lambda a, b: _string(a).startswith(_string(b))),
    "regex": (2, 2, lambda a, p: re.search(_string(p), _string(a)) is not None),
    "coalesce": (2, 2, lambda a, b: a if _string(a) != "" else b),
    # SurveyCTO's list and string functions; indexes start at 0.
    "selected-at": (2, 2, lambda a, i: _at(_codes(a), i)),
    "count-items": (2, 2, lambda sep, xs: float(len(_items(sep, xs)))),
    "item-at": (3, 3, lambda sep, xs, i: _at(_items(sep, xs), i)),
    "item-index": (
        3,
        3,
        lambda sep, xs, x: float(
            _items(sep, xs).index(_string(x)) if _string(x) in _items(sep, xs) else -1
        ),
    ),
    "item-present": (3, 3, lambda sep, xs, x: _string(x) in _items(sep, xs)),
    "de-duplicate": (
        2,
        2,
        lambda sep, xs: _string(sep).join(dict.fromkeys(_items(sep, xs))),
    ),
    "substr": (
        2,
        3,
        lambda a, start, end=None: _string(a)[
            int(_number(start)) : None if end is None else int(_number(end))
        ],
    ),
}


class _Parser:
    def __init__(self, expr: str):
        self.expr = expr
        self.tokens = self._tokenize(expr)
        self.pos = 0

    def _tokenize(self, expr: str) -> list[tuple[str, str]]:
        tokens, i = [], 0
        while i < len(expr):
            if _TRAILING_SPACE.match(expr, i):
                break
            m = _TOKEN_RE.match(expr, i)
            if m is None or m.end() == i:
                raise UnsupportedExpression(f"cannot read {expr[i:]!r} in {expr!r}")
            kind = m.lastgroup
            tokens.append((kind, m.group(kind)))
            i = m.end()
        return tokens

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise UnsupportedExpression(f"unexpected end of {self.expr!r}")
        self.pos += 1
        return token

    def expect(self, text: str) -> None:
        kind, value = self.take()
        if value != text:
            raise UnsupportedExpression(
                f"expected {text!r}, found {value!r} in {self.expr!r}"
            )

    def parse(self) -> Callable:
        node = self.expression(0)
        if self.peek() is not None:
            raise UnsupportedExpression(
                f"unexpected {self.peek()[1]!r} in {self.expr!r}"
            )
        return node

    def expression(self, min_prec: int) -> Callable:
        left = self.unary()
        while True:
            token = self.peek()
            op = token[1] if token and token[0] in ("op", "name") else None
            prec = _BINARY.get(op)
            if prec is None or prec <= min_prec:
                return left
            self.take()
            right = self.expression(prec)
            left = self._binary(op, left, right)

    @staticmethod
    def _binary(op: str, left: Callable, right: Callable) -> Callable:
        if op == "or":
            return lambda row: _boolean(left(row)) or _boolean(right(row))
        if op == "and":
            return lambda row: _boolean(left(row)) and _boolean(right(row))
        if op in ("=", "!=", "<", "<=", ">", ">="):
            return lambda row: _compare(op, left(row), right(row))
        return lambda row: _arith(op, left(row), right(row))

    def unary(self) -> Callable:
        token = self.peek()
        if token == ("op", "-"):
            self.take()
            operand = self.unary()
            return lambda row: -_number(operand(row))
        return self.primary()

    def primary(self) -> Callable:
        kind, value = self.take()
        if kind == "ref":
            name = value[2:-1]
            return lambda row: row.ref(name)
        if kind == "num":
            number = float(value)
            return lambda row: number
        if kind == "str":
            text = value[1:-1]
            return lambda row: text
        if kind == "dot":
            return lambda row: row.ref(".")
        if value == "(":
            node = self.expression(0)
            self.expect(")")
            return node
        if kind == "name" and self.peek() == ("op", "("):
            return self.call(value)
        if (kind, value) == ("name", "null"):
            # `${a} != null`: a path to no node, which the form reads as empty.
            return lambda row: ""
        raise UnsupportedExpression(f"unsupported {value!r} in {self.expr!r}")

    def call(self, name: str) -> Callable:
        self.expect("(")
        args: list[Callable] = []
        if self.peek() != ("op", ")"):
            args.append(self.expression(0))
            while self.peek() == ("op", ","):
                self.take()
                args.append(self.expression(0))
        self.expect(")")
        if name == "index" and not args:
            return lambda row: float(row.index())
        if name == "if" and len(args) == 3:
            cond, then, other = args
            return lambda row: then(row) if _boolean(cond(row)) else other(row)
        if name not in _FUNCTIONS:
            raise UnsupportedExpression(
                f"function {name}() is not supported in {self.expr!r}"
            )
        low, high, fn = _FUNCTIONS[name]
        if not low <= len(args) <= high:
            raise UnsupportedExpression(
                f"{name}() takes {low}-{high} arguments in {self.expr!r}"
            )
        return lambda row: fn(*(a(row) for a in args))


@functools.cache
def compile_expression(expr: str) -> Callable[[object], Value]:
    """Parse ``expr`` once; return a function of a row."""
    return _Parser(expr).parse()


@functools.cache
def reads_self(expr: str) -> bool:
    """Whether ``expr`` reads ``.``, the value of the question it gates."""
    return any(kind == "dot" for kind, _ in _Parser(expr).tokens)
