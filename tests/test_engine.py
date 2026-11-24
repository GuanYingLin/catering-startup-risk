"""engine.py 的測試：作者門市驗收數字、結論規則、三句重點、極端輸入。

執行：python -m pytest
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import (CASES, EXAMPLE_STORE, NO_CAPITAL_TEXT, VERDICTS, Plan,  # noqa: E402
                    calculation_details, default_ramp, evaluate, fmt_money, fmt_months)


@pytest.fixture
def example() -> Plan:
    return Plan(**EXAMPLE_STORE)


# ---------------------------------------------------------------------------
# 作者門市驗收數字（改程式後這些數字不應改變）
# ---------------------------------------------------------------------------

def test_example_acceptance_numbers(example):
    r = evaluate(example)
    assert round(r.cm_rate, 4) == 0.6027
    assert fmt_money(r.cash_profit) == "69,132"
    assert round(r.cash_margin, 3) == 0.169
    assert fmt_money(r.breakeven_revenue) == "294,893"
    assert round(r.margin_of_safety, 3) == 0.280
    assert r.payback_months == 19.4
    assert r.stable_payback_months == 13.0
    assert fmt_money(r.splh) == "890"
    assert fmt_money(r.splh_breakeven) == "641"
    assert fmt_money(r.splh_healthy) == "787"
    assert fmt_money(r.splh_strained) == "1,236"
    assert r.splh_zone == "健康"
    assert r.verdict == "可行"
    assert r.verdict_sentence == "可行：三項檢查全部通過"
    assert r.missing_inputs == []
    assert all(c.passed for c in r.legal_checks)


def test_example_is_registered_as_case():
    assert EXAMPLE_STORE in CASES.values()


def test_example_highlights(example):
    s1, s2, s3 = evaluate(example).highlights
    assert s1.startswith("穩定期營業淨利（折舊前）每月 69,132 元")
    assert "19.4 個月回本" in s1 and "比 36 個月租約提早 16.6 個月" in s1
    assert "890 元" in s2 and "「健康」區間（787–1,236 元）" in s2
    assert "人事成本率高出產業平均最多" in s3 and "食材成本率（含包材）完全抵銷" in s3


# ---------------------------------------------------------------------------
# 結論規則：四種結論
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("changes, verdict", [
    ({}, "可行"),
    ({"rent": 200_000}, "不可行"),
    ({"contract_years": 1}, "不建議"),
    ({"food_rate": 0.43, "rent": 45_000, "contract_years": 5}, "可行，但獲利偏低"),
])
def test_verdicts(example, changes, verdict):
    r = evaluate(replace(example, **changes))
    assert r.verdict == verdict
    assert r.verdict_sentence.startswith(verdict)


def test_payback_equal_to_contract_passes(example):
    """第 2 項標準為「不超過租約」：回本月數等於租約月數仍算通過。"""
    r = evaluate(replace(example, contract_years=19.4 / 12))
    assert r.criteria[1].status == "通過"


def test_contract_missing_skips_second_check(example):
    r = evaluate(replace(example, contract_years=0))
    assert r.criteria[1].status == "略過"
    assert r.verdict == "可行"
    assert "租約未填" in r.highlights[0]


def test_verdict_names_come_from_constant():
    assert set(VERDICTS) == {"不可行", "不建議", "可行，但獲利偏低", "可行"}


# ---------------------------------------------------------------------------
# 三句重點的其他分支
# ---------------------------------------------------------------------------

def test_highlight_payback_exceeds_contract(example):
    s1 = evaluate(replace(example, contract_years=1)).highlights[0]
    assert "超過 12 個月租約 7.4 個月" in s1


def test_highlight_partial_offset_and_low_profit_zone(example):
    r = evaluate(replace(example, food_rate=0.43, rent=45_000))
    assert "「獲利偏低」區間" in r.highlights[1]
    assert "部分抵銷" in r.highlights[2]


def test_highlight_no_offset(example):
    r = evaluate(replace(example, food_rate=0.48, rent=60_000))
    assert "沒有其他項目低於平均可以抵銷" in r.highlights[2]


def test_highlight_all_costs_below_average(example):
    r = evaluate(replace(example, ft_salaries=[40_000], pt_hours=0, rent=15_000))
    assert r.highlights[2].startswith("三項成本率都不高於產業平均")


def test_highlight_strained_zone(example):
    r = evaluate(replace(example, ft_salaries=[40_000], pt_hours=40))
    assert r.splh_zone == "人力吃緊"
    assert "「人力吃緊」區間" in r.highlights[1]


# ---------------------------------------------------------------------------
# 養店期
# ---------------------------------------------------------------------------

def test_no_ramp_equals_stable_payback(example):
    r = evaluate(replace(example, ramp=[]))
    assert r.payback_months == r.stable_payback_months == 13.0


def test_default_ramp_extends_last_month():
    assert default_ramp(8) == [0.6, 0.6, 0.7, 0.7, 0.8, 0.8, 0.8, 0.8]
    assert default_ramp(0) == []


# ---------------------------------------------------------------------------
# 極端輸入
# ---------------------------------------------------------------------------

def test_all_zero_does_not_crash():
    r = evaluate(Plan())
    assert r.revenue == 0
    assert r.verdict == "不可行"


def test_missing_inputs_flagged():
    p = replace(Plan(), weekday_ticket=100, weekday_customers=100, weekday_days=20)
    assert evaluate(p).missing_inputs == ["食材成本率", "人事（員工薪資）", "月租金"]


def test_negative_contribution_margin(example):
    r = evaluate(replace(example, food_rate=1.0))
    assert r.verdict == "不可行"
    assert math.isinf(r.breakeven_revenue)
    assert "賣越多虧越多" in r.highlights[1]
    assert "—" not in r.highlights[1]


def test_no_capital(example):
    r = evaluate(replace(example, capital=0))
    assert r.payback_text == r.stable_payback_text == NO_CAPITAL_TEXT
    assert NO_CAPITAL_TEXT in r.highlights[0]
    assert r.criteria[1].actual == NO_CAPITAL_TEXT
    assert "0.0 個月" not in " ".join(r.highlights)


def test_zero_hours(example):
    r = evaluate(replace(example, ft_salaries=[], pt_hours=0, owner_hours=0))
    assert r.splh_zone == "—"
    assert r.highlights[1] == "總工時為 0，無法計算 SPLH。"


@pytest.mark.parametrize("changes", [
    {"rent": -1}, {"weekday_ticket": -146}, {"ft_salaries": [-1]}, {"ramp": [-0.1]},
])
def test_negative_inputs_rejected(example, changes):
    with pytest.raises(ValueError, match="不可為負數"):
        evaluate(replace(example, **changes))


def test_very_large_numbers(example):
    r = evaluate(replace(example, weekday_ticket=1e12, capital=1e15))
    assert math.isfinite(r.cash_profit)


# ---------------------------------------------------------------------------
# 顯示格式
# ---------------------------------------------------------------------------

def test_formatting():
    assert fmt_money(-0.4) == "0"
    assert fmt_money(float("nan")) == "—"
    assert fmt_months(float("inf")) == "無法回本"
    assert fmt_months(18.94) == "18.9 個月"


# ---------------------------------------------------------------------------
# 計算明細
# ---------------------------------------------------------------------------

def test_calculation_details(example):
    r = evaluate(example)
    d = dict(calculation_details(example, r))
    assert list(d) == ["營業額", "變動成本", "人事", "固定成本", "機會成本", "SPLH 四個門檻"]
    assert "平日：146 元 × 104 人 × 14 天 = 212,576 元" in d["營業額"]
    assert "假日：190 元 × 122 人 × 8.5 天 = 197,030 元" in d["營業額"]
    assert "食材：409,606 元 × 35.75% = 146,434 元" in d["變動成本"]
    assert "正職 1：45,000 元 × 1.20 = 54,000 元" in d["人事"]
    assert "兼職：時薪 200 元 × 108.33 小時 × 1.20 = 26,000 元" in d["人事"]
    assert "合計：177,717 元" in d["固定成本"]
    assert any(line.endswith("= 69,132 元") for line in d["固定成本"])
    assert "資金利息：啟動資金 900,000 元 × 年利率 1.7% ÷ 12 = 1,275 元" in d["機會成本"]
    splh = " ".join(d["SPLH 四個門檻"])
    for value in ("= 890 元", "= 641 元", "= 787 元", "= 840 元", "= 1,236 元"):
        assert value in splh


def test_calculation_details_zero_hours(example):
    p = replace(example, ft_salaries=[], pt_hours=0, pt_wage=0)
    d = dict(calculation_details(p, evaluate(p)))
    assert "沒有員工" in d["人事"]
    assert "總工時為 0，無法計算 SPLH。" in d["SPLH 四個門檻"]
