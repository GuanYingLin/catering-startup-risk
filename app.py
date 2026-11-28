"""餐飲個店創業前財務風險評估｜Streamlit 介面。

執行：streamlit run app.py
"""
import math
from dataclasses import asdict

import altair as alt
import pandas as pd
import streamlit as st

from engine import (ASSUMPTIONS, AUTHOR, BENCHMARKS, CASES, DATA_UPDATED, DISCLAIMER,
                    FT_MONTHLY_HOURS, GITHUB_URL, INDUSTRY_MARGIN_NAME,
                    MIN_HOURLY_WAGE_2026, MIN_MONTHLY_WAGE_2026, MOS_THRESHOLD, RAMP_DEFAULT,
                    RAMP_MAX_MONTHS, SPLH_ZONES, TAX_RATES, VERDICTS, Plan, calculation_details,
                    evaluate, fmt_money, fmt_yuan, pct_text)

st.set_page_config(page_title="餐飲個店創業前財務風險評估", layout="wide")

PCT_KEYS = {"food_rate", "packaging_rate", "delivery_share", "delivery_commission",
            "capital_rate"}
MAX_FT = 10

# 側欄數字欄位的顯示格式（只影響顯示，不影響計算）；未指定的百分比與倍數欄位維持兩位小數
FMT_INT = "%.0f"  # 金額、人數：不顯示小數
FMT_1 = "%.1f"  # 天數、工時、租約年數：一位小數

# 「成本結構與產業平均」長條圖配色（配合簡報替換時只改這兩個）
COLOR_PLAN = "#1F5C46"  # 本計畫：深綠（與簡報強調色一致）
COLOR_BENCHMARK = "#948E82"  # 產業平均：暖灰

# 輸入欄位上限：設計預設值，只為擋掉明顯打錯的數字（例如多打幾個 0）
INPUT_MAX = {
    "ticket": 10_000.0,  # 客單價（元）
    "customers": 5_000.0,  # 每日來客數
    "ft_salary": 500_000.0,  # 正職月薪（元）
    "pt_wage": 5_000.0,  # 兼職時薪（元）
    "pt_hours": 5_000.0,  # 兼職每月總工時（小時）
    "owner_hours": 744.0,  # 老闆每月在店工時（31 天 × 24 小時）
    "rent": 5_000_000.0,  # 月租金（元）
    "utilities": 1_000_000.0,  # 每月水電瓦斯（元）
    "other_fixed": 5_000_000.0,  # 其他固定費用（元／月）
    "capital": 500_000_000.0,  # 啟動資金（元）
    "owner_alt_wage": 5_000_000.0,  # 老闆去上班的月薪（元）
}


# ---------------------------------------------------------------------------
# 欄位預設值與案例載入
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
    ramp = values.pop("ramp")
    state["ramp_months"] = len(ramp)
    for i, share in enumerate(ramp):
        state[f"ramp_{i}"] = round(share * 100, 2)
    for k, v in values.items():
        if isinstance(v, str):
            state[k] = v
        elif k in PCT_KEYS:
            state[k] = round(v * 100, 4)
        else:
            state[k] = float(v)
    return state


CUSTOM_CASE = "自行輸入"
CASE_OPTIONS = [*CASES, CUSTOM_CASE]  # 新增案例請改 engine.CASES，這裡不用動


def apply_case():
    """依「案例」選單重設所有欄位：選案例時載入該案例，選自行輸入時清空。"""
    for i in range(RAMP_MAX_MONTHS):  # 清掉舊的養店期月份，避免沿用先前輸入
        st.session_state.pop(f"ramp_{i}", None)
    case = st.session_state.case
    st.session_state.update(ui_values(None if case == CUSTOM_CASE else CASES[case]))


if "case" not in st.session_state:  # 第一次開啟：預設載入第一個案例
    st.session_state.case = CASE_OPTIONS[0]
    apply_case()
for _k, _v in ui_values().items():
    st.session_state.setdefault(_k, _v)


def footer():
    """頁尾：作者、GitHub、資料更新日期、免責聲明。"""
    st.divider()
    st.caption(f"作者：{AUTHOR}｜GitHub：[{GITHUB_URL.removeprefix('https://')}]({GITHUB_URL})"
               f"｜資料更新：{DATA_UPDATED}")
    st.caption(DISCLAIMER)


# ---------------------------------------------------------------------------
# 輸入（側欄）
# ---------------------------------------------------------------------------
with st.sidebar:
    st.selectbox("案例", CASE_OPTIONS, key="case", on_change=apply_case,
                 help="選擇案例會載入該案例的數字；選「自行輸入」會清空所有欄位。"
                      "載入後仍可修改任何欄位。")
    st.header("創業計畫")

    st.selectbox("業別", list(BENCHMARKS), key="industry")
    ref = BENCHMARKS[st.session_state.industry]  # 欄位說明裡的產業參考值（依所選業別）
    ref_name = st.session_state.industry

    with st.expander("A 營收（穩定期）", expanded=True):
        c1, c2 = st.columns(2)
        c1.caption("平日")
        c2.caption("假日")
        help_ticket = "每位客人平均消費金額（含外帶、外送）。"
        help_customers = "每天的客人數（含外帶、外送）。"
        help_weekday_days = "週一到週五的營業天數。一個月約 21.5 個平日；每週公休一天，約扣 4.3 天（約 17 天）。"
        help_weekend_days = "週六、週日的營業天數。一個月約 8.5 天。"
        c1.number_input("客單價（元）", 0.0, INPUT_MAX["ticket"], step=5.0, format=FMT_INT, key="weekday_ticket",
                        help=help_ticket)
        c2.number_input("客單價（元） ", 0.0, INPUT_MAX["ticket"], step=5.0,
                        format=FMT_INT, key="weekend_ticket", help=help_ticket)
        c1.number_input("每日來客數", 0.0, INPUT_MAX["customers"], step=5.0,
                        format=FMT_INT, key="weekday_customers", help=help_customers)
        c2.number_input("每日來客數 ", 0.0, INPUT_MAX["customers"], step=5.0,
                        format=FMT_INT, key="weekend_customers", help=help_customers)
        c1.number_input("每月平日天數", 0.0, 31.0, step=0.5, format=FMT_1, key="weekday_days",
                        help=help_weekday_days)
        c2.number_input("每月假日天數", 0.0, 31.0, step=0.5, format=FMT_1, key="weekend_days",
                        help=help_weekend_days)

    with st.expander("B 變動成本", expanded=True):
        st.caption("變動成本：跟著營業額等比例增減的成本。")
        st.number_input("食材成本率（%）", 0.0, 100.0, step=0.5, key="food_rate",
                        help=f"食材進貨 ÷ 營業額。{ref_name}產業平均約 {ref['food'][0]:.0%}"
                             f"（歷年 {ref['food'][1]:.1%}–{ref['food'][2]:.1%}）。")
        st.number_input("包材率（%，已含在食材內填 0）", 0.0, 100.0, step=0.5,
                        key="packaging_rate")
        st.number_input("外送占營收（%）", 0.0, 100.0, step=0.5, key="delivery_share",
                        help="外送平台訂單占營業額的比例；沒有外送填 0。")
        st.number_input("外送平台抽成（%）", 0.0, 100.0, step=1.0, key="delivery_commission",
                        help="外送平台向店家收取的抽成，依平台合約填寫（作者門市為 33%）。")
        st.selectbox("營業稅類型", list(TAX_RATES), key="tax_type")

    st.caption("這裡只填員工；老闆自己的收入看營業淨利。")
    with st.expander("C 人力", expanded=True):
        st.caption(f"{ref_name}產業人事成本率平均約 {ref['labor'][0]:.1%}（含法定負擔，"
                   "占營業額）。")
        ft_count = int(st.number_input("正職人數", 0, MAX_FT, step=1, key="ft_count"))
        for i in range(ft_count):
            st.number_input(f"正職 {i + 1} 月薪（元）", 0.0, INPUT_MAX["ft_salary"],
                            step=1000.0, format=FMT_INT, key=f"ft_{i}",
                            help=f"不可低於 2026 年基本工資 {MIN_MONTHLY_WAGE_2026:,} 元。")
        st.number_input("兼職時薪（元）", 0.0, INPUT_MAX["pt_wage"], step=5.0, format=FMT_INT, key="pt_wage",
                        help=f"不可低於 2026 年基本時薪 {MIN_HOURLY_WAGE_2026} 元。")
        st.number_input("兼職每月總工時（小時）", 0.0, INPUT_MAX["pt_hours"], step=10.0,
                        format=FMT_1, key="pt_hours",
                        help="所有兼職人員一個月的工時加總。"
                             "例如每週 25 小時：25 × 52 ÷ 12 ≈ 108 小時。")
        st.number_input("老闆每月在店工時（小時）", 0.0, INPUT_MAX["owner_hours"], step=10.0,
                        format=FMT_1, key="owner_hours", help="算進總工時（影響 SPLH），不算進人事成本")

    with st.expander("D 固定費用", expanded=True):
        st.number_input("月租金（元）", 0.0, INPUT_MAX["rent"], step=1000.0, format=FMT_INT, key="rent",
                        help=f"{ref_name}產業租金平均約占營業額 {ref['rent'][0]:.1%}。")
        st.number_input("每月水電瓦斯（元）", 0.0, INPUT_MAX["utilities"], step=500.0,
                        format=FMT_INT, key="utilities", help="每月水費、電費、瓦斯費合計。")
        st.number_input("其他固定費用（元／月）", 0.0, INPUT_MAX["other_fixed"], step=500.0,
                        format=FMT_INT, key="other_fixed",
                        help="不隨營業額變動的每月支出，例如網路、POS 月費、記帳、保險、清潔。")

    with st.expander("E 投資", expanded=True):
        st.number_input("啟動資金（元）", 0.0, INPUT_MAX["capital"], step=10000.0,
                        format=FMT_INT, key="capital", help="開店前一次投入的總額：裝潢、設備、加盟金、押金等。")
        st.number_input("租約或加盟合約年限（年）", 0.0, 20.0, step=0.5, format=FMT_1, key="contract_years",
                        help="用來判斷能否在約滿前回本；沒有租約填 0，第 2 項檢查會略過。")
        st.number_input("老闆不開店、去上班的月薪（元）", 0.0, INPUT_MAX["owner_alt_wage"],
                        step=1000.0, format=FMT_INT, key="owner_alt_wage",
                        help="如果不開店、改去上班，每月大約能領多少薪水。系統會從營業淨利中扣除"
                             "這筆薪水和啟動資金的利息，算出『經濟淨利』：大於 0，代表開店比去上班"
                             "划算。人事欄位只填員工的薪水；老闆自己的收入，就是營業淨利。")

    with st.expander("F 養店期", expanded=True):
        ramp_months = int(st.number_input("養店期長度（月）", 0, RAMP_MAX_MONTHS, step=1,
                                          key="ramp_months",
                                          help="0 代表沒有養店期，第 1 個月起即為穩定期營業額"))
        if ramp_months:
            st.caption(f"第 1–{ramp_months} 個月營業額占穩定期的百分比，"
                       f"第 {ramp_months + 1} 個月起為 100%。")
        else:
            st.caption("沒有養店期：第 1 個月起即為穩定期營業額。")
        st.warning("預設值來自作者單一門市經驗，請依自身情況調整。")
        cols = st.columns(3)
        for i in range(ramp_months):
            key = f"ramp_{i}"
            if key not in st.session_state:
                # 前 6 個月用預設值；第 7 個月之後沿用前一個月（即第 6 個月起的值）
                st.session_state[key] = (round(RAMP_DEFAULT[i] * 100, 2) if i < len(RAMP_DEFAULT)
                                         else st.session_state[f"ramp_{i - 1}"])
            cols[i % 3].number_input(f"第 {i + 1} 月（%）", 0.0, 100.0, step=5.0, key=key)

    with st.expander("進階設定"):
        st.number_input("資金機會成本年利率（%）", 0.0, 20.0, step=0.1, key="capital_rate",
                        help="啟動資金如果不拿來開店、改放銀行，每年大約能賺的利率。"
                             "預設為臺灣銀行一年期定期存款一般牌告固定利率 1.70%（2026）。")
        st.number_input("正職法定負擔倍數", 1.0, 2.0, step=0.01, key="ft_multiplier",
                        help="雇主除了薪水，還要負擔勞保、健保、勞退、職保。"
                             "1.20 代表每付 100 元薪水，店家實際成本約 120 元。")
        st.number_input("兼職法定負擔倍數", 1.0, 2.0, step=0.01, key="pt_multiplier",
                        help="兼職的勞保、勞退依實際薪資投保，職保有最低級距；健保若由店家投保，"
                             "負擔更高。依投保方式約 1.16–1.26，預設取 1.20。")

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
    ramp=[ss[f"ramp_{i}"] / 100 for i in range(ramp_months)],
    capital_rate=ss.capital_rate / 100,
    ft_multiplier=ss.ft_multiplier, pt_multiplier=ss.pt_multiplier,
)

# ---------------------------------------------------------------------------
# 輸出
# ---------------------------------------------------------------------------
st.title("餐飲個店創業前財務風險評估")
st.caption("輸入創業計畫，系統以現金基礎計算月損益與含養店期的回本月數，"
           "並與經濟部餐飲業產業數據比較。")
st.caption("在左側欄輸入你的計畫或切換案例（手機請點左上角 »）。")

r = evaluate(plan)
bench = BENCHMARKS[plan.industry]

if ss.case == CUSTOM_CASE:
    # 自行輸入模式：最少要填的欄位，填好的打勾
    todo = [
        ("A 營收：平日、假日的客單價、來客數、每月天數", r.revenue > 0),
        ("B 變動成本：食材成本率", plan.food_rate > 0),
        ("C 人力：至少一位員工（正職月薪，或兼職時薪與工時）", r.labor_cost > 0),
        ("D 固定費用：月租金", plan.rent > 0),
        ("E 投資：啟動資金與租約年限", plan.capital > 0 and plan.contract_years > 0),
    ]
    if not all(done for _, done in todo):
        st.info("**最少要填（在左側欄）**\n" + "\n".join(
            f"- {'✓' if done else '☐'} {item}" for item, done in todo)
            + "\n\n其他欄位可先用預設值。不知道怎麼填？可以先在「案例」選單選作者門市，"
              "再把數字改成自己的。欄位旁的問號有說明與參考值。")

if r.revenue <= 0:
    if ss.case != CUSTOM_CASE:
        st.info("請在左側輸入創業計畫，或在「案例」選單選擇一個案例。")
    footer()
    st.stop()

# ===========================================================================
# 重點摘要
# ===========================================================================
st.header("重點摘要")
for c in r.legal_checks:
    if not c.passed:
        st.error(f"**法規未通過：{c.name}**（{c.detail}）。此項不改變結論，但必須修正。")
if r.missing_inputs:
    st.warning(f"以下欄位為 0，可能尚未填寫：{'、'.join(r.missing_inputs)}。"
               "結論可能過於樂觀，請確認；若確實為 0，可忽略此提醒。")

# 結論一行
show = dict(zip(VERDICTS, (st.error, st.error, st.warning, st.success)))[r.verdict]
show(f"**{r.verdict_sentence}**")

# 三項檢查表（結果放第二欄，手機上不用往右滑就看得到）
mark = {"通過": "✓ 通過", "未通過": "✗ 未通過", "略過": "略過"}
st.dataframe(pd.DataFrame([
    {"檢查項目": c.name, "結果": mark[c.status], "本計畫": c.actual, "標準": c.standard}
    for c in r.criteria]), hide_index=True, width="stretch")
with st.expander("結論規則"):
    st.markdown("第 1 項未通過為「不可行」；第 1 項通過、第 2 項未通過為「不建議」；"
                "只有第 3 項未通過為「可行，但獲利偏低」；全部通過為「可行」。"
                "租約未填時第 2 項略過，不影響結論。")

# 三句白話重點
st.markdown("\n".join(f"{i}. {h}" for i, h in enumerate(r.highlights, start=1)))

# 成本結構對照長條圖（橫向，手機上標籤不會被擠掉）
st.subheader("成本結構與產業平均")
chart_labels = {"food": "食材（含包材）", "labor": "人事", "rent": "租金"}
chart_rows = ([(chart_labels[g.key], g.ratio, g.bench_avg) for g in r.cost_gaps]
              + [("營業淨利率（折舊前）", r.cash_margin, bench["pre_dep_margin"][0])])
order = [row[0] for row in chart_rows]
series = ["本計畫", "產業平均"]
chart_df = pd.DataFrame(
    [{"項目": lab, "系列": name, "比率": val * 100,
      "標籤": f"{val:.1%}".rstrip("%")}  # 與表格同一套四捨五入，避免圖表與表格差 0.1
     for lab, mine, avg in chart_rows for name, val in zip(series, (mine, avg))])
x_max = max(chart_df["比率"].max(), 0) * 1.18 or 1  # 右側留空間給數值標籤
x_min = min(chart_df["比率"].min(), 0)
base = alt.Chart(chart_df).encode(
    y=alt.Y("項目:N", sort=order, title=None, axis=alt.Axis(labelLimit=0)),
    yOffset=alt.YOffset("系列:N", sort=series),
    x=alt.X("比率:Q", title="%", scale=alt.Scale(domain=[x_min, x_max], nice=False)),
)
bars = base.mark_bar().encode(
    color=alt.Color("系列:N", sort=series, title=None, legend=alt.Legend(orient="bottom"),
                    scale=alt.Scale(domain=series, range=[COLOR_PLAN, COLOR_BENCHMARK])),
    tooltip=["項目", "系列", alt.Tooltip("比率:Q", format=".1f", title="%")],
)
label_color = "#FAFAFA" if st.context.theme.type == "dark" else "#31333F"  # 跟著深淺色主題
labels = base.mark_text(align="left", baseline="middle", dx=4, fontSize=12,
                        color=label_color).encode(
    text=alt.Text("標籤:N"))
st.altair_chart((bars + labels).properties(height=300), width="stretch")
st.caption("資料來源：經濟部經營實況調查 2018–2024")

# ===========================================================================
# 計算依據
# ===========================================================================
st.divider()
st.header("計算依據")

with st.expander("計算明細：每個數字怎麼算出來"):
    for title, lines in calculation_details(plan, r):
        st.markdown(f"**{title}**\n" + "\n".join(f"- {line}" for line in lines))
    st.caption("各項金額四捨五入到元；合計以未四捨五入的金額計算，與各項加總可能差 1 元。")

left, right = st.columns(2)

# 月損益表
with left:
    st.subheader("月損益表（穩定期）")
    pnl = pd.DataFrame([
        ("營業額", r.revenue),
        ("− 變動成本", -r.revenue * r.variable_rate),
        ("＝ 邊際貢獻", r.contribution),
        ("− 人事", -r.labor_cost),
        ("− 租金", -plan.rent),
        ("− 水電與其他", -(plan.utilities + plan.other_fixed)),
        ("＝ 營業淨利（折舊前）", r.cash_profit),
        ("− 機會成本", -r.opportunity_cost),
        ("＝ 經濟淨利", r.economic_profit),
    ], columns=["項目", "每月（元）"])
    st.dataframe(pnl.style.format({"每月（元）": fmt_money}), hide_index=True,
                 width="stretch")
    st.caption("變動成本：食材、包材、外送抽成、營業稅，跟著營業額等比例增減。"
               "人事：員工薪資含勞健保等法定負擔。水電與其他：水電瓦斯與其他固定費用。"
               "機會成本：老闆去上班的月薪與啟動資金的利息。"
               "邊際貢獻：營業額扣掉變動成本後，拿來支付人事、租金等固定費用的錢；"
               f"邊際貢獻率 {r.cm_rate:.2%}，代表每 100 元營業額留下 {r.cm_rate * 100:.1f} 元。"
               "經濟淨利大於 0，代表開店比去上班划算。採現金基礎，不攤提啟動資金。")

# 成本結構明細（長條圖的數字）
with right:
    st.subheader("成本結構明細")
    # 欄名與項目名稱用短版（同長條圖），產業歷年區間移到表下說明，手機上才看得到「差距」
    detail_rows = ([(chart_labels[g.key], g.key, g.ratio) for g in r.cost_gaps]
                   + [("營業淨利率（折舊前）", "pre_dep_margin", r.cash_margin)])
    rows, ranges = [], []
    for label, key, mine in detail_rows:
        avg, lo, hi = bench[key]
        rows.append({"項目": label, "本計畫": mine, "產業平均": avg,
                     "差距": f"{(mine - avg) * 100:+.1f}"})
        ranges.append(f"{label} {lo:.1%}–{hi:.1%}")
    st.dataframe(pd.DataFrame(rows).style.format({"本計畫": "{:.1%}", "產業平均": "{:.1%}"}),
                 hide_index=True, width="stretch")
    st.caption("差距＝本計畫 − 產業平均，單位為百分點（依未四捨五入的比率計算）。"
               f"產業歷年區間：{'；'.join(ranges)}。")

# SPLH 區間
st.subheader("人力與 SPLH（每工時營業額）")
st.caption("SPLH（Sales Per Labor Hour，每工時營業額）= 營業額 ÷ 總工時（員工＋老闆）。"
           "數字越高，代表每小時人力創造的營業額越多；太低會虧損，太高代表人手可能不夠。")
zone_msg = dict(zip(SPLH_ZONES, (st.error, st.warning, st.success, st.warning))).get(
    r.splh_zone, st.info)
zone_msg(f"本計畫 SPLH **{fmt_yuan(r.splh)}**，落在「**{r.splh_zone}**」區。")
s1, s2, s3, s4 = st.columns(4)
s1.metric("損益平衡 SPLH", fmt_yuan(r.splh_breakeven), help="低於此值：虧損")
s2.metric("健康下限", fmt_yuan(r.splh_healthy),
          help=f"營業淨利率（折舊前）等於{INDUSTRY_MARGIN_NAME}歷年最低值時的 SPLH；"
               "低於此值：獲利偏低")
s3.metric("產業平均水準", fmt_yuan(r.splh_industry),
          help=f"營業淨利率（折舊前）等於{INDUSTRY_MARGIN_NAME}平均值時的 SPLH")
s4.metric("人力吃緊上限", fmt_yuan(r.splh_strained),
          help="平均每工時人事成本 ÷ 產業人事成本率歷年最低值；高於此值：人力吃緊")
st.caption(f"總工時 {r.total_hours:,.2f} 小時／月（正職每人以 {FT_MONTHLY_HOURS} 小時計，"
           "含兼職與老闆工時）。健康區間："
           f"{fmt_money(r.splh_healthy)}–{fmt_money(r.splh_strained)} 元。")

left2, right2 = st.columns(2)

# 養店期逐月表
with left2:
    st.subheader("養店期與回本")
    b1, b2, b3 = st.columns(3)
    b1.metric("含養店期回本", r.payback_text)
    b2.metric("不含養店期回本", r.stable_payback_text, help="僅供對照")
    b3.metric("租約月數", f"{r.contract_months:,.0f} 個月" if r.contract_months else "未填")
    sched = pd.DataFrame(
        [(f"第 {m} 月" if m <= len(plan.ramp) else f"第 {m} 月起", rev, profit, cum)
         for m, rev, profit, cum in r.ramp_schedule],
        columns=["月份", "營業額（元）", "營業淨利（折舊前，元）", "累計營業淨利（折舊前，元）"])
    st.dataframe(sched.style.format({c: fmt_money for c in sched.columns[1:]}),
                 hide_index=True, width="stretch")
    st.caption("養店期預設值來自作者單一門市經驗，請依自身情況調整。"
               "累計營業淨利（折舊前）達到啟動資金的月份即為回本月數，以內插法計算。")

# 營業額下滑情境與風險說明
with right2:
    st.subheader("營業額下滑情境")
    v1, v2 = st.columns(2)
    v1.metric("損益平衡營業額", fmt_yuan(r.breakeven_revenue)
              if math.isfinite(r.breakeven_revenue) else "無法損益平衡",
              help="每月營業額要超過這個數字，營業淨利（折舊前）才會大於 0。")
    v2.metric("安全邊際", pct_text(r.margin_of_safety),
              help="營業額最多可以比預估少多少，還不會虧損。"
                   "例如 28.8% 代表營業額少 28.8% 以內，營業淨利仍大於 0。")
    sens = pd.DataFrame(r.sensitivity, columns=["情境", "營業額（元）", "營業淨利（折舊前，元）"])
    st.dataframe(sens.style.format({"營業額（元）": fmt_money, "營業淨利（折舊前，元）": fmt_money}),
                 hide_index=True, width="stretch")
    st.markdown("**風險說明**（只做說明，不影響結論）")
    for risk in r.risks:
        st.markdown(f"- {risk}")

# 假設與資料來源
with st.expander("假設與資料來源"):
    st.dataframe(pd.DataFrame(ASSUMPTIONS, columns=["類別", "項目", "數值", "來源與說明"]),
                 hide_index=True, width="stretch")
    st.caption("公開資料：政府統計；法規：現行法令與公告；設計假設：本工具的預設值，"
               "非官方標準；作者經驗：作者單一門市的經營數字。")
    st.caption(f"法規參數：2026 年基本工資月薪 {MIN_MONTHLY_WAGE_2026:,} 元、時薪 "
               f"{MIN_HOURLY_WAGE_2026} 元。安全邊際提示門檻 {MOS_THRESHOLD:.0%} 為設計預設值，"
               "非官方標準。")

footer()
