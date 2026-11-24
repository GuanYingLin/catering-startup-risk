"""餐飲單店創業前財務風險評估：計算引擎。

只放計算與判斷規則，不含畫面程式，方便單獨測試。
所有金額單位為新臺幣元，比率以小數表示（0.35 = 35%）。
判斷採現金基礎：不攤提啟動資金，以含養店期的回本月數衡量投資回收。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 公開資料與法規參數
# ---------------------------------------------------------------------------

# 經濟部「批發、零售及餐飲業經營實況調查」，2018–2024 六個調查年平均
# （2018 起改以營所稅資料推估，與之前口徑不同，故只取 2018 以後；2021 為普查年無資料）
# 每項為 (平均, 最低, 最高)
# pre_dep_margin：折舊前營業利益率 = 各年營業利益率 + 折舊率
BENCHMARKS = {
    "餐館業": {
        "food": (0.4586, 0.4411, 0.4762),
        "labor": (0.2548, 0.2250, 0.2740),
        "rent": (0.0572, 0.0537, 0.0598),
        "pre_dep_margin": (0.1431, 0.1118, 0.1811),
    },
    "飲料店業": {
        "food": (0.4631, 0.4545, 0.4740),
        "labor": (0.2585, 0.2215, 0.2799),
        "rent": (0.0521, 0.0420, 0.0619),
        "pre_dep_margin": (0.1465, 0.1362, 0.1663),
    },
}

MIN_MONTHLY_WAGE_2026 = 29_500  # 勞動部，2026-01-01 起
MIN_HOURLY_WAGE_2026 = 196

TAX_RATES = {
    "小規模營業人（1%）": 0.01,
    "使用統一發票（5%）": 0.05,
}

FT_MULTIPLIER = 1.20  # 正職雇主法定負擔：勞保、健保、勞退、職保，2026 年約 19.8%
PT_MULTIPLIER = 1.11  # 兼職雇主法定負擔：假設值，待依投保級距查證
FT_MONTHLY_HOURS = 176  # 正職每月工時（每週 40 小時 × 4.4 週）
CAPITAL_RATE = 0.017  # 資金機會成本年利率：假設值，待查證
MOS_THRESHOLD = 0.20  # 安全邊際提示門檻：設計預設值，只用於風險說明，不影響結論

SENSITIVITY_DROPS = (0.10, 0.20)  # 營業額下滑情境：設計預設值

# 養店期：各月營業額占穩定期的比例，養店期結束後為 100%
# 預設長度 6 個月、各月比例皆來自作者單一門市經驗；長度可調 0–12 個月（0 = 沒有養店期）
# 超過 6 個月時，第 7 個月之後預設沿用第 6 個月的比例
RAMP_DEFAULT = (0.60, 0.60, 0.70, 0.70, 0.80, 0.80)
RAMP_DEFAULT_MONTHS = len(RAMP_DEFAULT)
RAMP_MAX_MONTHS = 12


def default_ramp(months: int) -> list[float]:
    """長度為 months 的預設養店期比例；超過預設長度的月份沿用最後一個月。"""
    return [RAMP_DEFAULT[min(i, RAMP_DEFAULT_MONTHS - 1)] for i in range(months)]

VERDICTS = ("不可行", "不建議", "可行，但獲利偏低", "可行")
SPLH_ZONES = ("虧損", "獲利偏低", "健康", "人力吃緊")


# ---------------------------------------------------------------------------
# 假設與資料來源：所有固定參數的清單（畫面底部表格使用，由上方常數產生）
# 類別：公開資料／法規／設計假設／作者經驗
# ---------------------------------------------------------------------------

def _bench_text(t: tuple[float, float, float]) -> str:
    return f"平均 {t[0]:.2%}（歷年 {t[1]:.2%}–{t[2]:.2%}）"


_MOEA = "經濟部統計處「批發、零售及餐飲業經營實況調查」2018–2024 六個調查年（2021 普查年無資料）"
_BENCH_NAMES = {"food": "食材成本率", "labor": "人事成本率", "rent": "租金率",
                "pre_dep_margin": "折舊前營業利益率"}

ASSUMPTIONS: list[tuple[str, str, str, str]] = [
    *[("公開資料", f"{ind}{_BENCH_NAMES[k]}", _bench_text(v),
       _MOEA + ("；營業利益率 + 折舊率" if k == "pre_dep_margin" else ""))
      for ind, items in BENCHMARKS.items() for k, v in items.items()],
    ("法規", "基本工資（月薪）", f"{MIN_MONTHLY_WAGE_2026:,} 元", "勞動部公告，2026-01-01 起生效"),
    ("法規", "基本工資（時薪）", f"{MIN_HOURLY_WAGE_2026} 元", "勞動部公告，2026-01-01 起生效"),
    ("法規", "營業稅：小規模營業人", f"{TAX_RATES['小規模營業人（1%）']:.0%}",
     "加值型及非加值型營業稅法第 13 條（查定課徵）"),
    ("法規", "營業稅：使用統一發票", f"{TAX_RATES['使用統一發票（5%）']:.0%}",
     "加值型及非加值型營業稅法第 10 條"),
    ("法規", "正職法定負擔倍數", f"{FT_MULTIPLIER:.2f}",
     "依勞保、就保、健保、勞退（雇主提繳 6%）、職保的雇主負擔估算，2026 年約 19.8%；"
     "以投保薪資等於月薪計，實際依投保級距略有差異。可在進階設定調整"),
    ("設計假設", "兼職法定負擔倍數", f"{PT_MULTIPLIER:.2f}",
     "假設值，待依投保級距查證。可在進階設定調整"),
    ("設計假設", "正職每月工時", f"{FT_MONTHLY_HOURS} 小時",
     "每週 40 小時（勞動基準法第 30 條正常工時上限）× 每月 4.4 週"),
    ("設計假設", "資金機會成本年利率", f"{CAPITAL_RATE:.1%}",
     "假設值，約為銀行一年期定存利率，待查證。可在進階設定調整"),
    ("設計假設", "安全邊際提示門檻", f"{MOS_THRESHOLD:.0%}",
     "設計預設值，非官方標準；只用於風險說明，不影響結論"),
    ("設計假設", "營業額下滑情境", "、".join(f"−{d:.0%}" for d in SENSITIVITY_DROPS),
     "設計預設值；只用於風險說明，不影響結論"),
    ("設計假設", "「業界水準」與「健康下限」門檻", "折舊前營業利益率歷年最低值",
     "取產業數據的歷年最低值作為最低可接受水準，而非平均值"),
    ("設計假設", "「人力吃緊上限」門檻", "人事成本率歷年最低值",
     "人事成本率低於產業歷年最低，視為人手可能不足"),
    ("作者經驗", f"養店期第 1–{RAMP_DEFAULT_MONTHS} 個月預設營業額比例",
     "、".join(f"{s:.0%}" for s in RAMP_DEFAULT),
     f"作者單一門市經驗，請依自身情況調整；第 {RAMP_DEFAULT_MONTHS + 1} 個月之後"
     f"預設沿用第 {RAMP_DEFAULT_MONTHS} 個月的值"),
    ("作者經驗", "養店期預設長度", f"{RAMP_DEFAULT_MONTHS} 個月",
     f"作者單一門市經驗，可調整為 0–{RAMP_MAX_MONTHS} 個月（0 代表沒有養店期）"),
    ("作者經驗", "範例門市數字", "按「載入範例」帶入",
     "作者經營的早午餐加盟門市 2025/04–2026/03 實際數字；只作範例，不進入計算公式"),
]


# ---------------------------------------------------------------------------
# 輸入
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    industry: str = "餐館業"
    # A 營收
    weekday_ticket: float = 0.0
    weekday_customers: float = 0.0
    weekday_days: float = 0.0
    weekend_ticket: float = 0.0
    weekend_customers: float = 0.0
    weekend_days: float = 0.0
    # B 變動成本
    food_rate: float = 0.0
    packaging_rate: float = 0.0
    delivery_share: float = 0.0
    delivery_commission: float = 0.0
    tax_type: str = "小規模營業人（1%）"
    # C 人力
    ft_salaries: list[float] = field(default_factory=list)
    pt_wage: float = 0.0
    pt_hours: float = 0.0
    owner_hours: float = 0.0  # 算進總工時，不算進人事成本（老闆的成本放在機會成本）
    # D 固定費用
    rent: float = 0.0
    utilities: float = 0.0
    other_fixed: float = 0.0
    # E 投資
    capital: float = 0.0
    contract_years: float = 0.0
    owner_alt_wage: float = 0.0
    # F 養店期
    ramp: list[float] = field(default_factory=lambda: default_ramp(RAMP_DEFAULT_MONTHS))
    # 進階設定
    capital_rate: float = CAPITAL_RATE
    ft_multiplier: float = FT_MULTIPLIER
    pt_multiplier: float = PT_MULTIPLIER


# ---------------------------------------------------------------------------
# 輸出
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Criterion:
    """判斷表的一項通過標準。status：通過／未通過／略過。"""
    name: str
    actual: str
    standard: str
    status: str


@dataclass
class CostGap:
    key: str
    name: str
    cost: float  # 每月金額
    ratio: float  # 本計畫比率
    bench_avg: float
    gap: float  # 本計畫 − 產業平均（百分點，小數）
    cost_reduction: float  # 回到產業平均需減少的成本（高於平均時才有意義）
    revenue_increase: float | None  # 或需增加的營業額；變動成本無此解法時為 None


@dataclass
class Result:
    revenue: float
    variable_rate: float
    cm_rate: float
    contribution: float
    labor_cost: float
    fixed_cost: float
    cash_profit: float
    cash_margin: float
    opportunity_cost: float
    economic_profit: float
    breakeven_revenue: float
    margin_of_safety: float
    total_hours: float
    splh: float
    splh_breakeven: float
    splh_healthy: float
    splh_industry: float
    splh_strained: float
    splh_zone: str
    ramp_schedule: list[tuple[int, float, float, float]]  # (月, 營業額, 現金淨利, 累計)
    payback_months: float  # 含養店期
    stable_payback_months: float  # 不含養店期，僅供對照
    contract_months: float
    ratios: dict[str, float]
    cost_gaps: list[CostGap]
    sensitivity: list[tuple[str, float, float]]
    legal_checks: list[Check]
    criteria: list[Criterion]  # 判斷表三項通過標準
    verdict: str
    verdict_sentence: str  # 白話結論，例如「可行：三項檢查全部通過」
    risks: list[str]
    highlights: list[str]  # 重點摘要的三句白話重點，依計算結果產生


def _safe_div(a: float, b: float) -> float:
    return a / b if b else float("nan")


def fmt_money(x: float | None) -> str:
    """金額取整數、千分位；-0 顯示為 0，nan / inf 顯示為「—」。"""
    if x is None or not math.isfinite(x):
        return "—"
    return f"{round(x) or 0:,}"


def pct_text(x: float) -> str:
    return "—" if not math.isfinite(x) else f"{x:.1%}"


def payback_with_ramp(capital: float, revenue: float, cm_rate: float, fixed_cost: float,
                      ramp: list[float]) -> tuple[float, list[tuple[int, float, float, float]]]:
    """逐月累計現金淨利，回傳累計達到啟動資金的月數（內插，四捨五入到小數一位）。

    無法回本時回傳 inf。另回傳養店期加第一個穩定月的逐月明細。
    """
    schedule = []
    cum = 0.0
    payback = None
    for m, share in enumerate(list(ramp) + [1.0], start=1):
        rev = revenue * share
        profit = rev * cm_rate - fixed_cost
        prev = cum
        cum += profit
        schedule.append((m, rev, profit, cum))
        if payback is None and prev < capital <= cum:
            payback = (m - 1) + (capital - prev) / profit
    if capital <= 0:
        return 0.0, schedule
    if payback is None:
        stable_profit = revenue * cm_rate - fixed_cost
        if stable_profit <= 0:
            return float("inf"), schedule
        # 第 len(ramp)+1 個月之後每月固定賺 stable_profit
        months_done = len(ramp) + 1
        payback = months_done + (capital - cum) / stable_profit
    return round(payback, 1), schedule


def _months_text(x: float) -> str:
    return f"{x:,.1f} 個月"


def _highlights(cash_profit: float, payback_months: float, contract_months: float,
                splh: float, splh_zone: str, splh_breakeven: float, splh_healthy: float,
                splh_strained: float, cost_gaps: list[CostGap]) -> list[str]:
    """重點摘要的三句白話重點：獲利與回本、SPLH 區間、成本結構。"""
    # 第 1 句：每月現金淨利與含養店期回本月數，並與租約比較
    if cash_profit <= 0:
        s1 = (f"穩定期每月現金淨利 {fmt_money(cash_profit)} 元，營運不賺錢，"
              "累計現金淨利永遠追不上啟動資金，無法回本。")
    else:
        s1 = (f"穩定期每月現金淨利 {fmt_money(cash_profit)} 元，"
              f"含養店期約 {_months_text(payback_months)}回本")
        if not contract_months:
            s1 += "；租約未填，無法和租約比較。"
        else:
            diff = contract_months - payback_months
            contract = f"{contract_months:,.0f} 個月租約"
            if diff > 0:
                s1 += f"，比 {contract}提早 {_months_text(diff)}。"
            elif diff == 0:
                s1 += f"，剛好等於 {contract}，沒有緩衝。"
            else:
                s1 += f"，超過 {contract} {_months_text(-diff)}，租約到期前回不了本。"

    # 第 2 句：SPLH 落在哪個區間，附上區間範圍
    if math.isnan(splh):
        s2 = "總工時為 0，無法計算 SPLH。"
    else:
        ranges = {
            "虧損": f"低於損益平衡 {fmt_money(splh_breakeven)} 元",
            "獲利偏低": f"{fmt_money(splh_breakeven)}–{fmt_money(splh_healthy)} 元",
            "健康": f"{fmt_money(splh_healthy)}–{fmt_money(splh_strained)} 元",
            "人力吃緊": f"高於 {fmt_money(splh_strained)} 元",
        }
        meaning = {
            "虧損": "每工時營業額不足以支付成本",
            "獲利偏低": "會賺錢，但獲利率低於業界最低水準",
            "健康": "人力與營業額相稱",
            "人力吃緊": "人手可能撐不住預估營業額",
        }
        s2 = (f"每工時營業額（SPLH）{fmt_money(splh)} 元，落在「{splh_zone}」區間"
              f"（{ranges[splh_zone]}），{meaning[splh_zone]}。")

    # 第 3 句：高於產業平均最多的成本項目，以及是否被其他項目抵銷
    above = max(cost_gaps, key=lambda g: g.gap)
    below = min(cost_gaps, key=lambda g: g.gap)
    total = sum(g.gap for g in cost_gaps)
    total_text = (f"三項合計比產業平均{'高' if total > 0 else '低'} "
                  f"{abs(total) * 100:.1f} 個百分點")
    if above.gap <= 0:
        s3 = (f"三項成本率都不高於產業平均，其中{below.name}最低，"
              f"比平均低 {-below.gap * 100:.1f} 個百分點；{total_text}。")
    else:
        s3 = (f"成本結構中，{above.name}高出產業平均最多"
              f"（本計畫 {above.ratio:.1%}，平均 {above.bench_avg:.1%}，"
              f"高 {above.gap * 100:.1f} 個百分點）")
        if below.gap < 0:
            verb = "完全抵銷" if total <= 0 else "部分抵銷"
            s3 += (f"，但被{below.name}{verb}（低於平均 {-below.gap * 100:.1f} 個百分點），"
                   f"{total_text}。")
        else:
            s3 += f"，沒有其他項目低於平均可以抵銷，{total_text}。"
    return [s1, s2, s3]


def evaluate(p: Plan) -> Result:
    bench = BENCHMARKS[p.industry]

    # 1. 月營業額（穩定期）
    revenue = (p.weekday_ticket * p.weekday_customers * p.weekday_days
               + p.weekend_ticket * p.weekend_customers * p.weekend_days)

    # 2. 邊際貢獻率
    tax_rate = TAX_RATES[p.tax_type]
    variable_rate = (p.food_rate + p.packaging_rate
                     + p.delivery_share * p.delivery_commission + tax_rate)
    cm_rate = 1 - variable_rate
    contribution = revenue * cm_rate

    # 3. 人事成本與固定成本
    labor_cost = (sum(p.ft_salaries) * p.ft_multiplier
                  + p.pt_wage * p.pt_hours * p.pt_multiplier)
    fixed_cost = labor_cost + p.rent + p.utilities + p.other_fixed

    # 4. 穩定期現金淨利、現金利益率、經濟淨利
    cash_profit = contribution - fixed_cost
    cash_margin = _safe_div(cash_profit, revenue)
    opportunity_cost = p.owner_alt_wage + p.capital * p.capital_rate / 12
    economic_profit = cash_profit - opportunity_cost

    # 5. 損益兩平與安全邊際
    breakeven_revenue = fixed_cost / cm_rate if cm_rate > 0 else float("inf")
    margin_of_safety = (_safe_div(revenue - breakeven_revenue, revenue)
                        if math.isfinite(breakeven_revenue) else float("nan"))

    # 6. SPLH 區間（以總工時計算）
    total_hours = len(p.ft_salaries) * FT_MONTHLY_HOURS + p.pt_hours + p.owner_hours
    splh = _safe_div(revenue, total_hours)

    def revenue_for_margin(margin: float) -> float:
        """現金利益率剛好等於 margin 時所需的營業額。"""
        return fixed_cost / (cm_rate - margin) if cm_rate > margin else float("inf")

    splh_breakeven = _safe_div(breakeven_revenue, total_hours)
    splh_healthy = _safe_div(revenue_for_margin(bench["pre_dep_margin"][1]), total_hours)
    splh_industry = _safe_div(revenue_for_margin(bench["pre_dep_margin"][0]), total_hours)
    splh_strained = _safe_div(_safe_div(labor_cost, total_hours), bench["labor"][1])

    if math.isnan(splh):
        splh_zone = "—"
    elif not splh >= splh_breakeven:
        splh_zone = "虧損"
    elif not splh >= splh_healthy:
        splh_zone = "獲利偏低"
    elif splh > splh_strained:
        splh_zone = "人力吃緊"
    else:
        splh_zone = "健康"

    # 7. 回本（含養店期）
    contract_months = p.contract_years * 12
    payback_months, ramp_schedule = payback_with_ramp(p.capital, revenue, cm_rate,
                                                      fixed_cost, p.ramp)
    stable_payback_months = (round(p.capital / cash_profit, 1) if cash_profit > 0
                             else float("inf"))

    # 8. 成本結構
    food_total_rate = p.food_rate + p.packaging_rate
    ratios = {
        "food": food_total_rate,
        "labor": _safe_div(labor_cost, revenue),
        "rent": _safe_div(p.rent, revenue),
        "cash_margin": cash_margin,
    }
    cost_items = (
        # key, 名稱, 每月金額, 是否為固定成本（增加營業額可稀釋）
        ("food", "食材成本率（含包材）", revenue * food_total_rate, False),
        ("labor", "人事成本率", labor_cost, True),
        ("rent", "租金率", p.rent, True),
    )
    cost_gaps = []
    for key, name, cost, is_fixed in cost_items:
        avg = bench[key][0]
        cost_gaps.append(CostGap(
            key=key, name=name, cost=cost, ratio=ratios[key], bench_avg=avg,
            gap=ratios[key] - avg,
            cost_reduction=cost - revenue * avg,
            # 食材隨營業額等比例增加，增加營業額無法降低食材率，故不提供此解法
            revenue_increase=(cost / avg - revenue) if is_fixed else None,
        ))

    sensitivity = []
    scenarios = [("預估營業額", 1.0)] + [(f"營業額少 {d:.0%}", 1 - d) for d in SENSITIVITY_DROPS]
    for label, factor in scenarios:
        r = revenue * factor
        sensitivity.append((label, r, r * cm_rate - fixed_cost))

    # ---------------- 法規檢查（不影響結論） ----------------
    legal_checks: list[Check] = []
    low_ft = [s for s in p.ft_salaries if s < MIN_MONTHLY_WAGE_2026]
    legal_checks.append(Check(
        "正職月薪不低於基本工資", not low_ft,
        f"2026 年基本工資 {MIN_MONTHLY_WAGE_2026:,} 元"
        + (f"；低於者：{'、'.join(f'{s:,.0f}' for s in low_ft)} 元" if low_ft else "")))
    if p.pt_hours:
        legal_checks.append(Check(
            "兼職時薪不低於基本時薪", p.pt_wage >= MIN_HOURLY_WAGE_2026,
            f"2026 年基本時薪 {MIN_HOURLY_WAGE_2026} 元，本計畫 {p.pt_wage:,.0f} 元"))

    # ---------------- 判斷表：三項通過標準 ----------------
    # 結論規則：第 1 項未通過 → 不可行；第 1 項通過、第 2 項未通過 → 不建議；
    # 只有第 3 項未通過 → 可行，但獲利偏低；全部通過（第 2 項可略過）→ 可行
    min_margin = bench["pre_dep_margin"][1]
    payback_text = ("無法回本" if math.isinf(payback_months)
                    else f"{payback_months:,.1f} 個月")
    profit_ok = cash_profit > 0
    payback_ok = (None if not contract_months
                  else payback_months <= contract_months)  # None = 略過
    margin_ok = cash_margin >= min_margin  # nan 時為 False

    def status(ok: bool | None) -> str:
        return "略過" if ok is None else ("通過" if ok else "未通過")

    criteria = [
        Criterion("① 營運是否賺錢", f"穩定期現金淨利 {fmt_money(cash_profit)} 元／月",
                  "大於 0 元", status(profit_ok)),
        Criterion("② 能否在租約內回本", f"含養店期回本 {payback_text}",
                  (f"不超過租約 {contract_months:,.0f} 個月" if contract_months
                   else "租約未填"), status(payback_ok)),
        Criterion("③ 獲利是否達業界水準", f"現金利益率 {pct_text(cash_margin)}",
                  f"至少 {min_margin:.1%}（{p.industry}折舊前營業利益率歷年最低值）",
                  status(margin_ok)),
    ]
    if not profit_ok:
        verdict, verdict_sentence = "不可行", "不可行：營運不賺錢，穩定期每月現金淨利未大於 0"
    elif payback_ok is False:
        verdict = "不建議"
        verdict_sentence = (f"不建議：無法在租約內回本（含養店期回本 {payback_text}，"
                            f"租約 {contract_months:,.0f} 個月）")
    elif not margin_ok:
        verdict = "可行，但獲利偏低"
        verdict_sentence = "可行，但獲利偏低：營運賺錢" + (
            "、能在租約內回本" if payback_ok else "") + "，但現金利益率未達業界水準"
    else:
        verdict = "可行"
        verdict_sentence = ("可行：三項檢查全部通過" if payback_ok
                            else "可行：其餘檢查全部通過（租約未填，回本檢查略過）")

    # ---------------- 風險說明（只說明，不影響結論） ----------------
    risks: list[str] = []
    for g in cost_gaps:
        if g.gap > 0:
            text = (f"{g.name}高於產業平均：本計畫 {g.ratio:.1%}，產業平均 {g.bench_avg:.1%}"
                    f"（{g.gap * 100:+.1f} 個百分點）。回到產業平均需每月減少成本 "
                    f"{fmt_money(g.cost_reduction)} 元")
            if g.revenue_increase is not None:
                text += f"，或增加營業額 {fmt_money(g.revenue_increase)} 元"
            risks.append(text + "。")
    if margin_of_safety < MOS_THRESHOLD or math.isnan(margin_of_safety):
        mos = "—" if math.isnan(margin_of_safety) else f"{margin_of_safety:.1%}"
        risks.append(f"安全邊際偏低：{mos}，低於 {MOS_THRESHOLD:.0%}。")
    for label, _, profit in sensitivity[1:]:
        risks.append(f"{label} 時，每月現金淨利為 {fmt_money(profit)} 元。")
    if splh_zone == "人力吃緊":
        risks.append(f"SPLH 進入人力吃緊區：{fmt_money(splh)} 元，高於上限 {fmt_money(splh_strained)} 元，"
                     "人手可能不足以支撐預估營業額。")
    if economic_profit < 0:
        risks.append(f"經濟淨利為負：每月 {fmt_money(economic_profit)} 元，"
                     "扣除老闆替代月薪與資金利息後，不如去上班。")

    return Result(
        revenue=revenue, variable_rate=variable_rate, cm_rate=cm_rate,
        contribution=contribution, labor_cost=labor_cost, fixed_cost=fixed_cost,
        cash_profit=cash_profit, cash_margin=cash_margin, opportunity_cost=opportunity_cost,
        economic_profit=economic_profit, breakeven_revenue=breakeven_revenue,
        margin_of_safety=margin_of_safety, total_hours=total_hours, splh=splh,
        splh_breakeven=splh_breakeven, splh_healthy=splh_healthy,
        splh_industry=splh_industry, splh_strained=splh_strained, splh_zone=splh_zone,
        ramp_schedule=ramp_schedule, payback_months=payback_months,
        stable_payback_months=stable_payback_months, contract_months=contract_months,
        ratios=ratios, cost_gaps=cost_gaps, sensitivity=sensitivity,
        legal_checks=legal_checks, criteria=criteria, verdict=verdict,
        verdict_sentence=verdict_sentence, risks=risks,
        highlights=_highlights(cash_profit, payback_months, contract_months, splh, splh_zone,
                               splh_breakeven, splh_healthy, splh_strained, cost_gaps),
    )


# ---------------------------------------------------------------------------
# 範例：作者經營的早午餐加盟門市（2025/04–2026/03 實際數字，作為回測）
# 未列出的欄位使用 Plan 預設值
# ---------------------------------------------------------------------------

EXAMPLE_STORE = {
    "industry": "餐館業",
    "weekday_ticket": 146, "weekday_customers": 104, "weekday_days": 14,
    "weekend_ticket": 190, "weekend_customers": 122, "weekend_days": 8.5,
    "food_rate": 0.3575, "packaging_rate": 0.015,
    "delivery_share": 0.045, "delivery_commission": 0.33,
    "tax_type": "小規模營業人（1%）",
    "ft_salaries": [45_000, 40_000],
    "pt_wage": 200, "pt_hours": 25 * 52 / 12,  # 每週 25 小時（A 17、B 8）
    "owner_hours": 0,
    "rent": 33_000, "utilities": 12_217, "other_fixed": 4_500,
    "capital": 900_000, "contract_years": 3, "owner_alt_wage": 0,
}

# ---------------------------------------------------------------------------
# 案例清單：畫面「案例」選單的選項。新增案例時，在上方定義一個 dict（欄位同 Plan，
# 未列出的欄位使用 Plan 預設值），再加到這裡即可。
# ---------------------------------------------------------------------------

CASES: dict[str, dict] = {
    "作者門市（2025/04–2026/03）": EXAMPLE_STORE,
}
