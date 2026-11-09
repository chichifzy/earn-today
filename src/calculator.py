"""薪资计算模块。

计算五险一金个人缴纳、个人所得税（年度累计预扣法），
并给出月均实际到手薪资以及日薪。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import workdays
from .config import Config


# 个税基本减除费用（起征点）：5000 元/月
MONTHLY_BASIC_DEDUCTION = 5000.0

# 综合所得年度累计预扣预缴税率表（级距为累计应纳税所得额）
# 每项：(上限, 税率, 速算扣除数)
WITHHOLDING_BRACKETS = [
    (36000.0, 0.03, 0.0),
    (144000.0, 0.10, 2520.0),
    (300000.0, 0.20, 16920.0),
    (420000.0, 0.25, 31920.0),
    (660000.0, 0.30, 52920.0),
    (960000.0, 0.35, 85920.0),
    (float("inf"), 0.45, 181920.0),
]

# 全年一次性奖金单独计税税率表（按“奖金÷12”所处的按月级距确定税率）
# 每项：(月度上限, 税率, 速算扣除数)
MONTHLY_BONUS_BRACKETS = [
    (3000.0, 0.03, 0.0),
    (12000.0, 0.10, 210.0),
    (25000.0, 0.20, 1410.0),
    (35000.0, 0.25, 2660.0),
    (55000.0, 0.30, 4410.0),
    (80000.0, 0.35, 7160.0),
    (float("inf"), 0.45, 15160.0),
]


@dataclass
class SalaryResult:
    monthly_salary: float          # 税前月薪
    social_base: float             # 社保/公积金缴纳基数
    pension: float                 # 养老（个人）
    medical: float                 # 医疗（个人）
    unemployment: float            # 失业（个人）
    housing_fund: float            # 公积金（个人）
    insurance_total: float         # 五险一金个人合计
    annual_tax: float              # 全年个税合计
    monthly_avg_net: float         # 月均实际到手（含年终奖折算）
    daily_net: float               # 日薪
    work_days: int                 # 计算日薪所用的当月实际工作日天数


def _social_base(config: Config) -> float:
    if config.social_base_mode == "custom":
        return config.social_base_custom
    return config.monthly_salary


def _item_bases(config: Config) -> dict[str, float]:
    """返回各社保项目使用的缴纳基数（养老/医疗/失业/公积金）。

    - individual：各项目使用各自独立基数
    - custom/salary：所有项目共用统一基数（_social_base 结果）
    """
    if config.social_base_mode == "individual":
        return {
            "pension": config.pension_base,
            "medical": config.medical_base,
            "unemployment": config.unemployment_base,
            "housing_fund": config.housing_fund_base,
        }
    base = _social_base(config)
    return {
        "pension": base,
        "medical": base,
        "unemployment": base,
        "housing_fund": base,
    }


def _annual_tax(monthly_taxable_income: float, months: int = 12) -> float:
    """按年度累计预扣法计算全年个税合计。

    monthly_taxable_income 为每月的应纳税所得额
    （= 税前工资 - 五险一金 - 起征点 - 专项附加扣除）。
    假设每月金额相同，逐月累计计算各月预扣税额并求和。
    """
    total_tax = 0.0
    cumulative_income = 0.0
    cumulative_tax_paid = 0.0
    for _ in range(months):
        cumulative_income += monthly_taxable_income
        taxable = max(cumulative_income, 0.0)
        tax_this_period = _apply_brackets(taxable) - cumulative_tax_paid
        tax_this_period = max(tax_this_period, 0.0)
        cumulative_tax_paid += tax_this_period
        total_tax += tax_this_period
    return total_tax


def _apply_brackets(taxable: float) -> float:
    """根据累计应纳税所得额计算累计应纳税额。"""
    for upper, rate, quick in WITHHOLDING_BRACKETS:
        if taxable <= upper:
            return taxable * rate - quick
    return 0.0


def _separate_bonus_tax(bonus_total: float) -> float:
    """全年一次性奖金单独计税：以 奖金÷12 确定按月级距的税率与速算扣除数。"""
    if bonus_total <= 0:
        return 0.0
    monthly = bonus_total / 12.0
    for upper, rate, quick in MONTHLY_BONUS_BRACKETS:
        if monthly <= upper:
            return max(bonus_total * rate - quick, 0.0)
    return 0.0


def calculate(config: Config, ref_date: date | None = None) -> SalaryResult:
    """核心计算：返回完整的薪资结果。

    日薪 = 月均实际到手 / 当月实际工作日天数（排除法定节假日、计入调休补班）。
    ref_date 用于指定按哪个月份计算工作日，默认取今天所在月份。
    """
    salary = config.monthly_salary
    bases = _item_bases(config)

    pension = bases["pension"] * config.pension_rate / 100.0
    medical = bases["medical"] * config.medical_rate / 100.0
    unemployment = bases["unemployment"] * config.unemployment_rate / 100.0
    housing_fund = bases["housing_fund"] * config.housing_fund_rate / 100.0
    insurance_total = pension + medical + unemployment + housing_fund + config.other_insurance

    # 每月应纳税所得额
    monthly_taxable = (
        salary - insurance_total - MONTHLY_BASIC_DEDUCTION - config.special_deduction
    )

    # 年终奖：按并入综合所得处理（折算为额外的应纳税所得额）
    # 这里将年终奖视为一次性并入全年综合所得计算，简化为增加年度收入。
    # 仅当勾选"年终奖计入平均月薪"时才参与相关计算，否则视为 0。
    if config.bonus_in_average:
        bonus_total = salary * config.annual_bonus_months
    else:
        bonus_total = 0.0

    # 全年个税：工资部分按 12 个月累计预扣，年终奖按所选方式叠加
    tax_without_bonus = _annual_tax(monthly_taxable, months=12)
    if config.bonus_tax_mode == "separate":
        # 单独计税：年终奖不并入综合所得，按全年一次性奖金税率表单独计
        bonus_tax = _separate_bonus_tax(bonus_total)
    else:
        # 并入计税：全年应纳税所得额整体增加 bonus_total 后取增量税额
        annual_taxable_base = max(monthly_taxable, 0.0) * 12
        tax_with_bonus = max(
            _apply_brackets(max(annual_taxable_base + bonus_total, 0.0)), 0.0
        )
        tax_base_only = max(_apply_brackets(annual_taxable_base), 0.0)
        bonus_tax = max(tax_with_bonus - tax_base_only, 0.0)
    annual_tax = tax_without_bonus + bonus_tax

    # 全年到手 = 全年税前(工资12月 + 年终奖) - 全年五险一金(12月) - 全年个税
    annual_gross = salary * 12 + bonus_total
    annual_insurance = insurance_total * 12
    annual_net = annual_gross - annual_insurance - annual_tax

    monthly_avg_net = annual_net / 12.0

    if ref_date is None:
        ref_date = date.today()
    work_days = workdays.workdays_in_month(ref_date.year, ref_date.month)
    # 极端兜底：万一某月工作日为 0，退回法定月计薪天数，避免除零
    divisor = work_days if work_days > 0 else config.work_days_per_month
    daily_net = monthly_avg_net / divisor

    return SalaryResult(
        monthly_salary=salary,
        social_base=_social_base(config),
        pension=pension,
        medical=medical,
        unemployment=unemployment,
        housing_fund=housing_fund,
        insurance_total=insurance_total,
        annual_tax=annual_tax,
        monthly_avg_net=monthly_avg_net,
        daily_net=daily_net,
        work_days=work_days,
    )
