"""XLSForm expression evaluation for relevance (XPath 1.0 value semantics)."""

import math

import pytest

from datasure.surveycto.xpath import UnsupportedExpression, compile_expression


class Row:
    """A row of field values; select_multiple values are space-separated codes."""

    def __init__(self, values, iteration=1):
        self.values, self.iteration = values, iteration

    def ref(self, name):
        return self.values.get(name)

    def index(self):
        return self.iteration


def ev(expr, **values):
    return compile_expression(expr)(Row(values))


@pytest.mark.parametrize(
    ("expr", "values", "expected"),
    [
        ("${a}=1", {"a": "1"}, True),
        ("${a}=1", {"a": "2"}, False),
        ("${a}=1", {"a": None}, False),
        ("${a} != 1", {"a": None}, True),  # empty -> NaN; NaN != 1 is true in XPath
        ("${a} = ''", {"a": None}, True),
        ("${a} > 0", {"a": -99}, False),
        ("${a} >= 0 and ${a} <= 120", {"a": 30}, True),
        ("${a}=1 and ${b}=1", {"a": "1", "b": "0"}, False),
        ("${a}=1 or ${b}=1", {"a": "1", "b": None}, True),
        ("not(${a}=1)", {"a": "0"}, True),
        ("selected(${m}, '2')", {"m": "1 2 77"}, True),
        ("selected(${m}, '3')", {"m": "1 2 77"}, False),
        ("selected(${m}, '2')", {"m": None}, False),
        ("count-selected(${m}) > 1", {"m": "1 2"}, True),
        ("string-length(${t}) > 0", {"t": "abc"}, True),
        ("string-length(${t}) > 0", {"t": None}, False),
        ("${a} div 2 = 1.5", {"a": 3}, True),
        ("${a} mod 2 = 1", {"a": 3}, True),
        ("-${a} = -3", {"a": 3}, True),
        ("${a} * 2 + 1 = 7", {"a": 3}, True),
        ("if(${a}=1, 'x', 'y') = 'y'", {"a": "0"}, True),
        ("regex(${t}, '^[0-9]{3}$')", {"t": "123"}, True),
        ("regex(${t}, '^[0-9]{3}$')", {"t": "12a"}, False),
        ("true() and not(false())", {}, True),
        ('${a} = "x"', {"a": "x"}, True),
        ("coalesce(${a}, ${b}) = 5", {"a": None, "b": 5}, True),
        ("int(${a}) = 3", {"a": 3.7}, True),
        ("number(${a}) > 2", {"a": "2.5"}, True),
        # SurveyCTO list and string functions, 0-based.
        ("selected-at(${m}, 1) = '2'", {"m": "1 2 77"}, True),
        ("selected-at(${m}, 5) = ''", {"m": "1 2"}, True),
        ("count-items(',', ${l}) = 3", {"l": "a,b,c"}, True),
        ("count-items(',', ${l}) = 0", {"l": None}, True),
        ("item-at(' - ', ${l}, 1) = 'b'", {"l": "a - b - c"}, True),
        ("item-at(',', ${l}, 9) = ''", {"l": "a,b"}, True),
        ("item-index(',', ${l}, 'c') = 2", {"l": "a,b,c"}, True),
        ("item-index(',', ${l}, 'z') = -1", {"l": "a,b,c"}, True),
        ("item-present(',', ${l}, 'b')", {"l": "a,b,c"}, True),
        ("item-present(',', ${l}, 'z')", {"l": "a,b,c"}, False),
        ("de-duplicate(',', ${l}) = 'a,b'", {"l": "a,b,a"}, True),
        ("substr(${t}, 1, 3) = 'bc'", {"t": "abcd"}, True),
        ("substr(${t}, 2) = 'cd'", {"t": "abcd"}, True),
        ("${a} != null", {"a": "x"}, True),
        ("${a} != null", {"a": None}, False),
    ],
)
def test_evaluates(expr, values, expected):
    assert ev(expr, **values) is expected


def test_index_is_the_repeat_instance():
    fn = compile_expression("index() > 1")
    assert fn(Row({}, iteration=1)) is False
    assert fn(Row({}, iteration=2)) is True


def test_number_coercion_of_text_is_nan():
    fn = compile_expression("number(${a})")
    assert math.isnan(fn(Row({"a": "abc"})))


@pytest.mark.parametrize(
    "expr",
    [
        "today() > ${d}",  # depends on when it runs
        "position(..) = 1",
        "/form/a = 1",
        "${a} = ",
        "unknown_fn(${a})",
    ],
)
def test_unsupported_raises(expr):
    with pytest.raises(UnsupportedExpression):
        compile_expression(expr)
