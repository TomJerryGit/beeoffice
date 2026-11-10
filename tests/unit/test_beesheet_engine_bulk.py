"""BeeSheet 公式引擎批量函数覆盖。"""
import pandas as pd
import pytest

from beeoffice.plugins.beesheet_engine import FormulaEngine


class FakeModel:
    def __init__(self):
        self.df = pd.DataFrame({
            "A": [1, 2, 3, 4, 5],
            "B": [10, 20, 30, 40, 50],
            "C": ["北京", "上海", "北京", "广州", "上海"],
            "D": ["a", "b", "c", "d", "e"],
        })

    def get_value(self, r, c):
        try:
            return self.df.iloc[r, c]
        except Exception:
            return None


@pytest.fixture
def model():
    return FakeModel()


FORMULAS = {
    "SUM": ("=SUM(A1:A5)", 15.0),
    "AVERAGE": ("=AVERAGE(A1:A5)", 3.0),
    "MAX": ("=MAX(A1:A5)", 5.0),
    "MIN": ("=MIN(A1:A5)", 1.0),
    "COUNT": ("=COUNT(A1:A5)", 5),
    "COUNTA": ("=COUNTA(D1:D5)", 5),
    "MEDIAN": ("=MEDIAN(A1:A5)", 3.0),
    "STDEV": ("=STDEV(A1:A5)", 1.4142135623730951),
    "VAR": ("=VAR(A1:A5)", 2.0),
    "LARGE": ("=LARGE(A1:A5,2)", 4.0),
    "SMALL": ("=SMALL(A1:A5,2)", 2.0),
    "IFERROR": ("=IFERROR(1/0,99)", 99),
    "CHOOSE": ('=CHOOSE(2,"x","y")', "y"),
    "IF": ("=IF(A1>0,SUM(A1:A3),0)", 6.0),
    "RANK": ("=RANK(3,A1:A5)", 3),
    "ABS": ("=ABS(-3)", 3.0),
    "SQRT": ("=SQRT(9)", 3.0),
    "TEXTJOIN": ('=TEXTJOIN("-",TRUE,"a","b")', "a-b"),
    "YEAR": ("=YEAR(DATE(2024,1,2))", 2024),
    "MONTH": ("=MONTH(DATE(2024,1,2))", 1),
    "DAY": ("=DAY(DATE(2024,1,2))", 2),
    "ROUND": ("=ROUND(1.234,2)", 1.23),
    "ROUNDUP": ("=ROUNDUP(1.2,0)", 2.0),
    "ROUNDDOWN": ("=ROUNDDOWN(1.8,0)", 1.0),
    "POWER": ("=POWER(2,3)", 8.0),
    "MOD": ("=MOD(10,3)", 1),
    "INT": ("=INT(1.9)", 1),
    "TRUNC": ("=TRUNC(1.9)", 1),
    "CEILING": ("=CEILING(1.2,1)", 2.0),
    "FLOOR": ("=FLOOR(1.8,1)", 1.0),
    "SUMPRODUCT": ("=SUMPRODUCT(A1:A3,B1:B3)", 140.0),
    "LEFT": ('=LEFT("hello",2)', "he"),
    "RIGHT": ('=RIGHT("hello",2)', "lo"),
    "MID": ('=MID("hello",2,3)', "ell"),
    "LEN": ('=LEN("hello")', 5),
    "TRIM": ('=TRIM(" hi ")', "hi"),
    "UPPER": ('=UPPER("hi")', "HI"),
    "LOWER": ('=LOWER("HI")', "hi"),
    "PROPER": ('=PROPER("hi there")', "Hi There"),
    "CONCAT": ('=CONCATENATE("a","b")', "ab"),
    "FIND": ('=FIND("l","hello")', 3),
    "SEARCH": ('=SEARCH("L","hello")', 3),
    "REPLACE": ('=REPLACE("hello",2,2,"XX")', "hXXlo"),
    "SUBSTITUTE": ('=SUBSTITUTE("hello","l","x")', "hexxo"),
    "TEXT": ('=TEXT(1.2,"0.0")', "1.2"),
    "VALUE": ('=VALUE("12")', 12.0),
    "REPT": ('=REPT("a",3)', "aaa"),
    "EXACT": ('=EXACT("a","a")', True),
    "DATEDIF": ('=DATEDIF(DATE(2024,1,1),DATE(2024,1,10),"d")', 9),
    "WEEKDAY": ("=WEEKDAY(DATE(2024,1,1))", 1),
    "PMT": ("=PMT(0.1,10,100)", -16.274539488251154),
    "FV": ("=FV(0.1,10,-10)", 159.37424601000023),
    "PV": ("=PV(0.1,10,-10)", 61.44567105704686),
    "NPV": ("=NPV(0.1,10,20)", 9.09090909090909),
    "SLN": ("=SLN(100,10,5)", 18.0),
    "DB": ("=DB(100,10,5,1)", 36.90426555198067),
    "COUNTIF": ('=COUNTIF(C1:C5,"北京")', 2),
    "SUMIF": ('=SUMIF(C1:C5,"北京",B1:B5)', 40.0),
    "AVERAGEIF": ('=AVERAGEIF(C1:C5,"北京",B1:B5)', 20.0),
    "COUNTIFS": ('=COUNTIFS(C1:C5,"北京",A1:A5,">1")', 1),
    "SUMIFS": ('=SUMIFS(B1:B5,C1:C5,"北京")', 40.0),
    "AVERAGEIFS": ('=AVERAGEIFS(B1:B5,C1:C5,"北京")', 20.0),
    "VLOOKUP": ("=VLOOKUP(1,A1:B5,2,FALSE)", 10),
    "HLOOKUP": ("=HLOOKUP(1,A1:B5,2,FALSE)", 2),
    "INDEX": ("=INDEX(A1:B5,2,2)", 20),
    "MATCH": ("=MATCH(3,A1:A5,0)", 3),
    "XLOOKUP": ("=XLOOKUP(3,A1:A5,B1:B5)", 30),
    "XMATCH": ("=XMATCH(3,A1:A5)", 3),
    "LET": ("=LET(x,1,x+1)", 2),
    "SWITCH": ('=SWITCH(2,1,"a",2,"b","c")', "b"),
    "MAXIFS": ('=MAXIFS(B1:B5,C1:C5,"北京")', 30.0),
    "MINIFS": ('=MINIFS(B1:B5,C1:C5,"北京")', 10.0),
    "TEXTBEFORE": ('=TEXTBEFORE("a-b","-")', "a"),
    "TEXTAFTER": ('=TEXTAFTER("a-b","-")', "b"),
    "VALUETOTEXT": ("=VALUETOTEXT(1)", "1"),
    "ISBLANK": ("=ISBLANK(A1)", False),
    "ISNUMBER": ("=ISNUMBER(A1)", False),
    "ISTEXT": ("=ISTEXT(D1)", True),
    "ISERROR": ("=ISERROR(1/0)", True),
}


@pytest.mark.parametrize("name", sorted(FORMULAS))
def test_formula_functions(model, name):
    formula, expected = FORMULAS[name]
    got = FormulaEngine.evaluate(formula, model)
    if isinstance(expected, float):
        assert got == pytest.approx(expected)
    else:
        assert got == expected


def test_formula_errors_and_non_formula(model):
    assert FormulaEngine.evaluate("plain", model) == "plain"
    assert str(FormulaEngine.evaluate("=1/0", model)).startswith("#ERROR")
    assert str(FormulaEngine.evaluate("=NOPE(1)", model)).startswith("#ERROR")
