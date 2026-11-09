"""配置管理模块：负责读取/写入用户配置。

配置以 JSON 形式保存在用户主目录下的 ~/.earn_today/config.json。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field


CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".earn_today")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Config:
    # 基本薪资
    monthly_salary: float = 10000.0          # 税前月薪
    annual_bonus_months: float = 0.0         # 年终奖月数（折算进月均到手）
    # 是否将年终奖计入平均月薪（勾选后才参与相关计算），默认计入
    bonus_in_average: bool = True

    # 年终奖计税方式：
    # "combined" 并入当年综合所得计税；"separate" 单独计税（全年一次性奖金优惠）
    bonus_tax_mode: str = "combined"

    # 所在地（仅作展示/备注用途，社保比例以下方为准）
    city: str = "北京"

    # 社保缴纳基数
    # base_mode:
    #   "salary"     按工资作为统一基数
    #   "custom"     设定统一基数（所有项目共用 social_base_custom）
    #   "individual" 设定独立基数（每个项目使用各自的基数）
    social_base_mode: str = "salary"
    social_base_custom: float = 10000.0      # 当 base_mode == custom 时使用
    # 当 base_mode == individual 时，各项目单独的缴纳基数（元）
    pension_base: float = 10000.0            # 养老基数
    medical_base: float = 10000.0            # 医疗基数
    unemployment_base: float = 10000.0       # 失业基数
    housing_fund_base: float = 10000.0       # 公积金基数

    # 社保个人缴纳比例（%），可在设置页修改
    pension_rate: float = 8.0                # 养老
    medical_rate: float = 2.0                # 医疗
    unemployment_rate: float = 0.5           # 失业

    # 公积金个人缴纳比例（%）
    housing_fund_rate: float = 12.0

    # 其他保险（固定金额，元/月），直接加算计入五险一金个人合计
    other_insurance: float = 0.0

    # 个税：采用年度累计预扣法
    # 每月专项附加扣除合计（子女教育、房贷、赡养老人等）
    special_deduction: float = 0.0

    # 每月工作日天数（除零兜底用），默认 21.75 为法定月均计薪天数
    work_days_per_month: float = 21.75

    # 工作时段（"HH:MM" 字符串）：上班、下班、午休开始、午休结束
    work_start: str = "09:00"
    work_end: str = "18:00"
    lunch_start: str = "12:00"
    lunch_end: str = "13:00"

    # 晚餐时段（仅当下班晚于 19:00 时可用）：是否含不计入工时的晚餐
    dinner_enabled: bool = False
    dinner_start: str = "18:00"
    dinner_end: str = "18:30"

    # ---- 个性化 ----
    # 悬浮数字颜色（十六进制），默认淡黄色，与历史表现一致
    number_color: str = "#fcf2c8"
    # 悬浮数字透明度（0~60，表示透明的百分比；0 为完全不透明）
    number_opacity: int = 0
    # 是否在鼠标悬浮到浮窗上时恢复完全不透明
    hover_restore_opacity: bool = False
    # 悬浮数字显示的小数位数（0/1/2）
    number_decimals: int = 2

    # 浮窗是否置顶（大头钉插上），默认不置顶，状态跨启动保留
    pinned: bool = False

    # 浮窗上次退出时的位置（屏幕坐标）；为 None 时使用默认位置
    pos_x: int | None = None
    pos_y: int | None = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        valid = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**valid)


def load_config() -> Config:
    """从磁盘加载配置，不存在时返回默认配置。"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return Config.from_dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            return Config()
    return Config()


def save_config(config: Config) -> None:
    """将配置写入磁盘。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
