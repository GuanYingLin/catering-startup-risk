"""餐飲單店創業前財務風險評估｜Streamlit 介面。

執行：streamlit run app.py
"""
import math
from dataclasses import asdict

import altair as alt
import pandas as pd
import streamlit as st

from engine import (ASSUMPTIONS, BENCHMARKS, EXAMPLE_STORE, FT_MONTHLY_HOURS,
                    MIN_HOURLY_WAGE_2026, MIN_MONTHLY_WAGE_2026, MOS_THRESHOLD, RAMP_MONTHS,
                    TAX_RATES, Plan, evaluate, fmt_money, pct_text)

st.set_page_config(page_title="餐飲單店創業前財務風險評估", layout="wide")

PCT_KEYS = {"food_rate", "packaging_rate", "delivery_share", "delivery_commission",
            "capital_rate"}
MAX_FT = 10


# ---------------------------------------------------------------------------
# 欄位預設值與範例載入
# ---------------------------------------------------------------------------
def ui_values(overrides: dict | None = None) -> dict:
    """以 Plan 預設值為底、套上 overrides，轉成畫面欄位（session_state）的值。"""
    values = asdict(Plan())
    values.update(overrides or {})
    state = {}
    ft = values.pop("ft_salaries")
    state["ft_count"] = len(ft)
    for i in range(MAX_FT):
        state[f"ft_{i}"] = float(ft[i]) if i < len(ft) else 0.0
    for i, share in enumerate(values.pop("ramp")):
        state[f"ramp_{i}"] = round(share * 100, 2)
    for k, v in values.items():
        if isinstance(v, str):
            state[k] = v
        elif k in PCT_KEYS:
            state[k] = round(v * 100, 4)
        else:
            state[k] = float(v)
    return state


def load_example():
    st.session_state.update(ui_values(EXAMPLE_STORE))


for _k, _v in ui_values().items():
    st.session_state.setdefault(_k, _v)


def money(x: float, unit: str = " 元") -> str:
    s = fmt_money(x)
    return s if s == "—" else s + unit


def months(x: float) -> str:
    if math.isinf(x):
        return "無法回本"
    return "—" if math.isnan(x) else f"{x:,.1f} 個月"


pct = pct_text


# ---------------------------------------------------------------------------
# 輸入（側欄）
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("創業計畫")
    st.button("載入範例：作者門市（2025/04–2026/03）", on_click=load_example,
              width="stretch")

    st.selectbox("業別", list(BENCHMARKS), key="industry")

    with st.expander("A 營收（穩定期）", expanded=True):
        c1, c2 = st.columns(2)
        c1.caption("平日")
        c2.caption("假日")
        c1.number_input("客單價（元）", 0.0, step=5.0, key="weekday_ticket")
        c2.number_input("客單價（元） ", 0.0, step=5.0, key="weekend_ticket")
        c1.number_input("每日來客數", 0.0, step=5.0, key="weekday_customers")
        c2.number_input("每日來客數 ", 0.0, step=5.0, key="weekend_customers")
        c1.number_input("每月天數", 0.0, 31.0, step=0.5, key="weekday_days")
        c2.number_input("每月天數 ", 0.0, 31.0, step=0.5, key="weekend_days")

    with st.expander("B 變動成本", expanded=True):
        st.number_input("食材成本率（%）", 0.0, 100.0, step=0.5, key="food_rate")
        st.number_input("包材率（%，已含在食材內填 0）", 0.0, 100.0, step=0.5,
                        key="packaging_rate")
        st.number_input("外送占營收（%）", 0.0, 100.0, step=0.5, key="delivery_share")
        st.number_input("外送平台抽成（%）", 0.0, 100.0, step=1.0, key="delivery_commission")
        st.selectbox("營業稅類型", list(TAX_RATES), key="tax_type")

    with st.expander("C 人力", expanded=True):
        ft_count = int(st.number_input("正職人數", 0, MAX_FT, step=1, key="ft_count"))
        for i in range(ft_count):
            st.number_input(f"正職 {i + 1} 月薪（元）", 0.0, step=1000.0, key=f"ft_{i}")
        st.number_input("兼職時薪（元）", 0.0, step=5.0, key="pt_wage")
        st.number_input("兼職每月總工時（小時）", 0.0, step=10.0, key="pt_hours")
        st.number_input("老闆每月在店工時（小時）", 0.0, step=10.0, key="owner_hours",
                        help="算進總工時（影響 SPLH），不算進人事成本")

    with st.expander("D 固定費用", expanded=True):
        st.number_input("月租金（元）", 0.0, step=1000.0, key="rent")
        st.number_input("每月水電瓦斯（元）", 0.0, step=500.0, key="utilities")
        st.number_input("其他固定費用（元／月）", 0.0, step=500.0, key="other_fixed")

    with st.expander("E 投資", expanded=True):
        st.number_input("啟動資金（元）", 0.0, step=10000.0, key="capital")
        st.number_input("租約或加盟合約年限（年）", 0.0, 20.0, step=0.5, key="contract_years")
        st.number_input("老闆不開店、去上班的月薪（元）", 0.0, step=1000.0,
                        key="owner_alt_wage")

    with st.expander("F 養店期", expanded=True):
        st.caption(f"第 1–{RAMP_MONTHS} 個月營業額占穩定期的百分比，"
                   f"第 {RAMP_MONTHS + 1} 個月起為 100%。")
        st.warning("預設值來自作者單一門市經驗，請依自身情況調整。")
        cols = st.columns(3)
        for i in range(RAMP_MONTHS):
            cols[i % 3].number_input(f"第 {i + 1} 月（%）", 0.0, 100.0, step=5.0,
                                     key=f"ramp_{i}")

    with st.expander("進階設定"):
        st.number_input("資金機會成本年利率（%）", 0.0, 20.0, step=0.1, key="capital_rate",
                        help="假設值，待查證後更新")
        st.number_input("正職法定負擔倍數", 1.0, 2.0, step=0.01, key="ft_multiplier")
        st.number_input("兼職法定負擔倍數", 1.0, 2.0, step=0.01, key="pt_multiplier",
                        help="假設值，待依投保級距查證")

ss = st.session_state
plan = Plan(
    industry=ss.industry,
    weekday_ticket=ss.weekday_ticket, weekday_customers=ss.weekday_customers,
    weekday_days=ss.weekday_days, weekend_ticket=ss.weekend_ticket,
    weekend_customers=ss.weekend_customers, weekend_days=ss.weekend_days,
    food_rate=ss.food_rate / 100, packaging_rate=ss.packaging_rate / 100,
    delivery_share=ss.delivery_share / 100,
    delivery_commission=ss.delivery_commission / 100,
    tax_type=ss.tax_type,
    ft_salaries=[ss[f"ft_{i}"] for i in range(ft_count)],
    pt_wage=ss.pt_wage, pt_hours=ss.pt_hours, owner_hours=ss.owner_hours,
    rent=ss.rent, utilities=ss.utilities, other_fixed=ss.other_fixed,
    capital=ss.capital, contract_years=ss.contract_years, owner_alt_wage=ss.owner_alt_wage,
    ramp=[ss[f"ramp_{i}"] / 100 for i in range(RAMP_MONTHS)],
    capital_rate=ss.capital_rate / 100,
    ft_multiplier=ss.ft_multiplier, pt_multiplier=ss.pt_multiplier,
)

# ---------------------------------------------------------------------------
# 輸出
# ---------------------------------------------------------------------------
st.title("餐飲單店創業前財務風險評估")
st.caption("輸入創業計畫，系統以現金基礎計算月損益與含養店期的回本月數，"
           "並與經濟部餐飲業產業數據比較。")

r = evaluate(plan)
bench = BENCHMARKS[plan.industry]

if r.revenue <= 0:
    st.info("請在左側輸入創業計畫，或按「載入範例」。")
    st.stop()

# 1. 結論卡
with st.container(border=True):
    for c in r.legal_checks:
        if not c.passed:
            st.error(f"**法規未通過：{c.name}**（{c.detail}）。此項不改變結論，但必須修正。")
    st.subheader("結論")
    show = {"可行": st.success, "可行，但獲利偏低": st.warning,
            "不建議": st.error, "不可行": st.error}[r.verdict]
    show(f"**{r.verdict_sentence}**")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("穩定期每月現金淨利", money(r.cash_profit))
    m2.metric("現金利益率", pct(r.cash_margin),
              help=f"{plan.industry}折舊前營業利益率：平均 {bench['pre_dep_margin'][0]:.1%}，"
                   f"歷年最低 {bench['pre_dep_margin'][1]:.1%}")
    m3.metric("損益兩平營業額", money(r.breakeven_revenue)
              if math.isfinite(r.breakeven_revenue) else "無法損益兩平")
    m4.metric("含養店期回本", months(r.payback_months))
    with st.expander("判斷表", expanded=True):
        mark = {"通過": "✓ 通過", "未通過": "✗ 未通過", "略過": "略過"}
        st.dataframe(pd.DataFrame([
            {"檢查項目": c.name, "本計畫": c.actual, "標準": c.standard,
             "結果": mark[c.status]} for c in r.criteria]),
            hide_index=True, width="stretch")
        st.caption("結論規則：第 1 項未通過為「不可行」；第 1 項通過、第 2 項未通過為「不建議」；"
                   "只有第 3 項未通過為「可行，但獲利偏低」；全部通過為「可行」。"
                   "租約未填時第 2 項略過，不影響結論。")

left, right = st.columns(2)

# 2. 月損益表
with left:
    st.subheader("月損益表（穩定期）")
    pnl = pd.DataFrame([
        ("營業額", r.revenue),
        ("− 變動成本（食材、包材、外送抽成、營業稅）", -r.revenue * r.variable_rate),
        ("＝ 邊際貢獻", r.contribution),
        ("− 人事成本（含法定負擔）", -r.labor_cost),
        ("− 租金", -plan.rent),
        ("− 水電瓦斯與其他", -(plan.utilities + plan.other_fixed)),
        ("＝ 穩定期現金淨利", r.cash_profit),
        ("− 機會成本（老闆替代月薪、資金利息）", -r.opportunity_cost),
        ("＝ 經濟淨利", r.economic_profit),
    ], columns=["項目", "每月金額（元）"])
    st.dataframe(pnl.style.format({"每月金額（元）": fmt_money}), hide_index=True,
                 width="stretch")
    st.caption(f"邊際貢獻率 {r.cm_rate:.2%}：每 100 元營業額，扣掉變動成本後留下 "
               f"{r.cm_rate * 100:.1f} 元。採現金基礎，不攤提啟動資金。")

# 3. 成本結構對照
with right:
    st.subheader("成本結構與產業比較")
    rows = []
    for g in r.cost_gaps:
        lo, hi = bench[g.key][1:]
        rows.append({"項目": g.name, "本計畫": g.ratio, "產業平均": g.bench_avg,
                     "差距": f"{g.gap * 100:+.1f} 個百分點", "產業歷年區間": f"{lo:.1%}–{hi:.1%}"})
    avg, lo, hi = bench["pre_dep_margin"]
    rows.append({"項目": "現金利益率（對照折舊前營業利益率）", "本計畫": r.cash_margin,
                 "產業平均": avg, "差距": f"{(r.cash_margin - avg) * 100:+.1f} 個百分點",
                 "產業歷年區間": f"{lo:.1%}–{hi:.1%}"})
    st.dataframe(pd.DataFrame(rows).style.format({"本計畫": "{:.1%}", "產業平均": "{:.1%}"}),
                 hide_index=True, width="stretch")

    chart_labels = ["食材（含包材）", "人事", "租金", "現金利益率"]
    series = ["本計畫", "產業平均"]
    chart_df = pd.DataFrame(
        [{"項目": lab, "系列": "本計畫", "比率": row["本計畫"] * 100}
         for lab, row in zip(chart_labels, rows)]
        + [{"項目": lab, "系列": "產業平均", "比率": row["產業平均"] * 100}
           for lab, row in zip(chart_labels, rows)])
    chart = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X("項目:N", sort=chart_labels, title=None,
                axis=alt.Axis(labelAngle=0, labelLimit=0)),
        xOffset=alt.XOffset("系列:N", sort=series),
        y=alt.Y("比率:Q", title="%"),
        color=alt.Color("系列:N", sort=series, title=None,
                        legend=alt.Legend(orient="bottom")),
        tooltip=["項目", "系列", alt.Tooltip("比率:Q", format=".1f", title="%")],
    )
    st.altair_chart(chart, width="stretch")
    st.caption(f"產業數據：經濟部經營實況調查，{plan.industry}，2018–2024 六個調查年平均，"
               "以營業額加權，大型業者影響較大。現金利益率對照的是折舊前營業利益率"
               "（營業利益率 + 折舊率）。")

# 4. SPLH 區間
st.subheader("人力與 SPLH（每工時營業額）")
zone_msg = {"虧損": st.error, "獲利偏低": st.warning, "健康": st.success,
            "人力吃緊": st.warning}.get(r.splh_zone, st.info)
zone_msg(f"本計畫 SPLH **{money(r.splh)}**，落在「**{r.splh_zone}**」區。")
s1, s2, s3, s4 = st.columns(4)
s1.metric("損益平衡 SPLH", money(r.splh_breakeven), help="低於此值：虧損")
s2.metric("健康下限", money(r.splh_healthy),
          help="現金利益率等於產業折舊前營業利益率歷年最低值時的 SPLH；低於此值：獲利偏低")
s3.metric("產業平均水準", money(r.splh_industry),
          help="現金利益率等於產業折舊前營業利益率平均值時的 SPLH")
s4.metric("人力吃緊上限", money(r.splh_strained),
          help="平均每工時人事成本 ÷ 產業人事成本率歷年最低值；高於此值：人力吃緊")
st.caption(f"總工時 {r.total_hours:,.2f} 小時／月（正職每人以 {FT_MONTHLY_HOURS} 小時計，"
           "含兼職與老闆工時）。健康區間："
           f"{fmt_money(r.splh_healthy)}–{fmt_money(r.splh_strained)} 元。")

left2, right2 = st.columns(2)

# 5. 養店期與回本
with left2:
    st.subheader("養店期與回本")
    b1, b2, b3 = st.columns(3)
    b1.metric("含養店期回本", months(r.payback_months))
    b2.metric("不含養店期回本", months(r.stable_payback_months), help="僅供對照")
    b3.metric("租約月數", f"{r.contract_months:,.0f} 個月" if r.contract_months else "未填")
    sched = pd.DataFrame(
        [(f"第 {m} 月" if m <= RAMP_MONTHS else f"第 {m} 月起", rev, profit, cum)
         for m, rev, profit, cum in r.ramp_schedule],
        columns=["月份", "營業額（元）", "現金淨利（元）", "累計現金淨利（元）"])
    st.dataframe(sched.style.format({c: fmt_money for c in sched.columns[1:]}),
                 hide_index=True, width="stretch")
    st.caption("養店期預設值來自作者單一門市經驗，請依自身情況調整。"
               "累計現金淨利達到啟動資金的月份即為回本月數，以內插法計算。")

# 6. 風險說明
with right2:
    st.subheader("風險說明")
    st.caption("以下只做說明，不影響結論。")
    st.metric("安全邊際", pct(r.margin_of_safety), help="營業額少多少就會開始虧損")
    for risk in r.risks:
        st.markdown(f"- {risk}")
    sens = pd.DataFrame(r.sensitivity, columns=["情境", "營業額（元）", "現金淨利（元）"])
    st.dataframe(sens.style.format({"營業額（元）": fmt_money, "現金淨利（元）": fmt_money}),
                 hide_index=True, width="stretch")

st.caption(f"法規參數：2026 年基本工資月薪 {MIN_MONTHLY_WAGE_2026:,} 元、時薪 "
           f"{MIN_HOURLY_WAGE_2026} 元。安全邊際提示門檻 {MOS_THRESHOLD:.0%} 為設計預設值，"
           "非官方標準。")

with st.expander("假設與資料來源"):
    st.dataframe(pd.DataFrame(ASSUMPTIONS, columns=["類別", "項目", "數值", "來源與說明"]),
                 hide_index=True, width="stretch")
    st.caption("公開資料：政府統計；法規：現行法令與公告；設計假設：本工具的預設值，"
               "非官方標準；作者經驗：作者單一門市的經營數字。")
