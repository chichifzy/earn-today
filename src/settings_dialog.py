"""设置页对话框。

允许用户配置月薪、年终奖月数、所在地、社保基数、
社保各项比例、公积金比例、专项附加扣除、月工作日等，
并实时预览计算出的月均到手与日薪。
"""

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import calculator
from . import workdays
from .config import Config, save_config
from datetime import date


# 淡黄色可爱风样式表（{CHECK} 在运行时替换为对勾图标的绝对路径）
CUTE_STYLE = """
QDialog {
    background: #fffffc;
}
QTabWidget::pane {
    border: 2px solid #fdf6dc;
    border-radius: 14px;
    background: #fffffd;
    top: -1px;
}
QTabBar::tab {
    background: #fdfaea;
    color: #c2a35c;
    padding: 8px 22px;
    margin-right: 6px;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #fcf2c8;
    color: #a98a3f;
}
QTabBar::tab:hover {
    background: #fdf7dc;
}
QLabel {
    color: #a98f52;
    font-size: 13px;
}
QDoubleSpinBox, QComboBox, QTimeEdit {
    background: #fffffd;
    border: 1.5px solid #fdf6dc;
    border-radius: 9px;
    padding: 5px 8px;
    color: #8a7233;
    selection-background-color: #fcf2c8;
    min-height: 20px;
}
QDoubleSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
    border: 1.5px solid #f6e6ac;
    background: #fffef7;
}
QComboBox::drop-down, QTimeEdit::up-button, QTimeEdit::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    border: none;
    background: transparent;
    width: 18px;
}
QComboBox QAbstractItemView {
    background: #fffffd;
    border: 1.5px solid #fdf6dc;
    border-radius: 8px;
    selection-background-color: #fdf7dc;
    selection-color: #8a7233;
    outline: none;
}
QCheckBox {
    color: #a98f52;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1.5px solid #f3e7b5;
    border-radius: 6px;
    background: #fffffd;
}
QCheckBox::indicator:checked {
    background: #fcf2c8;
    border: 1.5px solid #f0dc8f;
    image: url("{CHECK}");
}
QLabel#previewLabel {
    background: #fdfaea;
    border: 1.5px dashed #f0dc8f;
    border-radius: 12px;
    padding: 12px;
    color: #a98a3f;
    font-size: 13px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #fdf6dc;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #f6e6ac;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: #fcf2c8;
    border: 1.5px solid #f0dc8f;
}
QSlider::handle:horizontal:hover {
    background: #fdf7dc;
}
QPushButton {
    background: #fcf2c8;
    color: #a98a3f;
    border: none;
    border-radius: 10px;
    padding: 7px 20px;
    font-weight: bold;
}
QPushButton:hover {
    background: #fdf7dc;
}
QPushButton:pressed {
    background: #f3e7b5;
}
"""


def _to_qtime(text: str) -> QTime:
    """将 "HH:MM" 字符串转为 QTime。"""
    t = QTime.fromString(text, "HH:mm")
    return t if t.isValid() else QTime(9, 0)


def _from_qtime(t: QTime) -> str:
    """将 QTime 转为 "HH:MM" 字符串。"""
    return t.toString("HH:mm")


CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "其他"]

# 悬浮数字可选颜色：(名称, 十六进制)，第一个为默认（淡黄色，与历史一致）
NUMBER_COLORS = [
    ("淡黄色", "#fcf2c8"),
    ("淡粉色", "#f8c8d8"),
    ("淡绿色", "#c8e6c9"),
    ("淡蓝色", "#c5e1f5"),
    ("浅灰色", "#dcdcdc"),
    ("深灰色", "#7a7a7a"),
]

# 各城市社保个人缴纳比例（%）：养老、医疗、失业
# 养老全国统一 8%，医疗多为 2%，失业各地略有差异
# "其他" 不做自动填充，保留用户手动输入
CITY_RATES = {
    "北京": {"pension": 8.0, "medical": 2.0, "unemployment": 0.5},
    "上海": {"pension": 8.0, "medical": 2.0, "unemployment": 0.5},
    "广州": {"pension": 8.0, "medical": 2.0, "unemployment": 0.2},
    "深圳": {"pension": 8.0, "medical": 2.0, "unemployment": 0.3},
    "杭州": {"pension": 8.0, "medical": 2.0, "unemployment": 0.5},
    "成都": {"pension": 8.0, "medical": 2.0, "unemployment": 0.4},
}


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("设置 - 今天赚了多少")
        self.setFixedWidth(440)
        self._build_ui()
        self._load_from_config()
        self._update_preview()
        # 窗口高度的锁定推迟到首次显示后进行（见 showEvent）。
        # __init__ 阶段对话框尚未显示，样式表 padding/min-height 与字体度量
        # 未完全应用到子控件的 sizeHint，此时测量会偏小，打包后（字体/DPI 不同）
        # 会导致底部控件（如“个人比例”小输入框）被裁掉下半部分。
        self._height_locked = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._height_locked:
            self._height_locked = True
            # 此时样式表与字体度量均已生效，测量最大高度并锁定，
            # 底部弹簧吸收晚餐行显隐的高度差，保证任意状态下尺寸稳定
            self.setFixedHeight(self._max_height())

    def _max_height(self) -> int:
        """临时展开全部晚餐控件，测出最大高度后恢复。"""
        widgets = [self.dinner_enabled, self.dinner_start, self.dinner_end]
        labels = [
            self._time_form.labelForField(self.dinner_start),
            self._time_form.labelForField(self.dinner_end),
        ]
        for w in widgets + labels:
            if w is not None:
                w.setVisible(True)
        # 社保基数的“统一基数”行与“独立基数”行都用 setRowVisible 增删会改变高度，
        # 测量时同时展开，锁定高度覆盖最高的情况，避免任一模式下底部被裁
        self._salary_form.setRowVisible(self.social_base_custom, True)
        self._salary_form.setRowVisible(self._bases_row, True)
        # 确保样式表已应用到所有子控件并强制布局重新计算，
        # 避免测量到的高度偏小
        self.ensurePolished()
        for child in self.findChildren(QWidget):
            child.ensurePolished()
        if self.layout() is not None:
            self.layout().activate()
        h = self.sizeHint().height()
        # 恢复到与当前配置一致的显隐状态（不能依赖 isVisible 快照，
        # 因为对话框尚未显示时 isVisible 恒为 False）
        self._update_dinner_visibility()
        self._on_base_mode_changed()
        return h

    def _build_ui(self):
        from .resources import resource_path

        check_path = resource_path("check.svg")
        self.setStyleSheet(CUTE_STYLE.replace("{CHECK}", check_path.replace("\\", "/")))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.monthly_salary = self._spin(0, 10_000_000, 100, " 元")
        self.annual_bonus_months = self._spin(0, 60, 0.5, " 个月")

        self.bonus_in_average = QCheckBox("年终奖计入平均月薪")

        self.bonus_tax_mode = QComboBox()
        self.bonus_tax_mode.addItems(["并入综合所得", "单独计税"])
        self.bonus_tax_mode.setFixedWidth(220)

        self.city = QComboBox()
        self.city.addItems(CITIES)
        self.city.setFixedWidth(220)
        self.city.currentIndexChanged.connect(self._on_city_changed)

        self.social_base_mode = QComboBox()
        self.social_base_mode.addItems(["按工资", "设定统一基数（元）", "设定独立基数（元）"])
        self.social_base_mode.setFixedWidth(220)
        self.social_base_mode.currentIndexChanged.connect(self._on_base_mode_changed)

        self.social_base_custom = self._spin(0, 10_000_000, 100, " 元")

        # 独立基数：养老/医疗/失业/公积金各自的缴纳基数（元），小尺寸横排
        self.pension_base = self._spin(0, 10_000_000, 100, "")
        self.medical_base = self._spin(0, 10_000_000, 100, "")
        self.unemployment_base = self._spin(0, 10_000_000, 100, "")
        self.housing_fund_base = self._spin(0, 10_000_000, 100, "")
        for _base_spin in (
            self.pension_base,
            self.medical_base,
            self.unemployment_base,
            self.housing_fund_base,
        ):
            _base_spin.setFixedWidth(60)
            _base_spin.setDecimals(0)
            _base_spin.setSuffix("")
            _base_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)

        self.pension_rate = self._spin(0, 100, 0.1, " %")
        self.medical_rate = self._spin(0, 100, 0.1, " %")
        self.unemployment_rate = self._spin(0, 100, 0.1, " %")
        self.housing_fund_rate = self._spin(0, 100, 0.5, " %")
        # 四个比例横排显示，改为小尺寸输入框
        for _rate_spin in (
            self.pension_rate,
            self.medical_rate,
            self.unemployment_rate,
            self.housing_fund_rate,
        ):
            _rate_spin.setFixedWidth(52)
            _rate_spin.setDecimals(1)
            _rate_spin.setSuffix("")
            _rate_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)

        self.special_deduction = self._spin(0, 1_000_000, 100, " 元")
        # 其他保险：固定金额，加算计入五险一金
        self.other_insurance = self._spin(0, 1_000_000, 100, " 元")
        # 每月计薪天数：按当月实际工作日自动计算，只读展示
        self.work_days = self._spin(1, 31, 0.25, " 天")
        self.work_days.setReadOnly(True)
        self.work_days.setButtonSymbols(QDoubleSpinBox.NoButtons)

        # 工作时段控件
        self.work_start = self._time_edit()
        self.work_end = self._time_edit()
        self.lunch_start = self._time_edit()
        self.lunch_end = self._time_edit()

        # 晚餐：勾选项 + 起止时间（默认隐藏，下班晚于 19:00 才出现）
        self.dinner_enabled = QCheckBox("上下班区间内含不计入工时的晚餐")
        self.dinner_start = self._time_edit()
        self.dinner_end = self._time_edit()

        # ---- Tab 1：薪资相关 ----
        salary_form = QFormLayout()
        salary_form.setSpacing(10)
        salary_form.setContentsMargins(16, 16, 16, 16)
        salary_form.addRow("税前月薪", self.monthly_salary)
        salary_form.addRow("年终奖月数", self.annual_bonus_months)
        salary_form.addRow("", self.bonus_in_average)
        salary_form.addRow("年终奖计税方式", self.bonus_tax_mode)
        salary_form.addRow("所在地", self.city)
        salary_form.addRow("社保基数方式", self.social_base_mode)
        salary_form.addRow("社保基数(统一)", self.social_base_custom)
        # 独立基数横排：第一行标题，第二行小输入框（与"个人比例"平行）
        bases_row = QWidget()
        bases_grid = QGridLayout(bases_row)
        bases_grid.setContentsMargins(0, 0, 0, 0)
        bases_grid.setHorizontalSpacing(4)
        bases_grid.setVerticalSpacing(2)
        _base_items = [
            ("养老", self.pension_base),
            ("医疗", self.medical_base),
            ("失业", self.unemployment_base),
            ("公积金", self.housing_fund_base),
        ]
        for col, (title, spin) in enumerate(_base_items):
            label = QLabel(title)
            label.setAlignment(Qt.AlignHCenter)
            bases_grid.addWidget(label, 0, col, Qt.AlignHCenter)
            bases_grid.addWidget(spin, 1, col, Qt.AlignHCenter)
        bases_grid.setColumnStretch(len(_base_items), 1)
        self._bases_row = bases_row
        salary_form.addRow("独立基数", bases_row)
        # 养老/医疗/失业/公积金比例横排：第一行标题，第二行小输入框
        rates_row = QWidget()
        rates_grid = QGridLayout(rates_row)
        rates_grid.setContentsMargins(0, 0, 0, 0)
        rates_grid.setHorizontalSpacing(10)
        rates_grid.setVerticalSpacing(2)
        _rate_items = [
            ("养老(%)", self.pension_rate),
            ("医疗(%)", self.medical_rate),
            ("失业(%)", self.unemployment_rate),
            ("公积金(%)", self.housing_fund_rate),
        ]
        for col, (title, spin) in enumerate(_rate_items):
            label = QLabel(title)
            label.setAlignment(Qt.AlignHCenter)
            rates_grid.addWidget(label, 0, col, Qt.AlignHCenter)
            rates_grid.addWidget(spin, 1, col, Qt.AlignHCenter)
        rates_grid.setColumnStretch(len(_rate_items), 1)
        salary_form.addRow("个人比例", rates_row)
        salary_form.addRow("其他保险", self.other_insurance)
        salary_form.addRow("每月专项附加扣除", self.special_deduction)
        self._salary_form = salary_form  # 供显隐社保基数行使用
        salary_tab = QWidget()
        salary_outer = QVBoxLayout(salary_tab)
        salary_outer.setContentsMargins(0, 0, 0, 0)
        salary_outer.addLayout(salary_form)
        salary_outer.addStretch(1)

        # ---- Tab 2：时间相关 ----
        time_form = QFormLayout()
        time_form.setSpacing(10)
        time_form.setContentsMargins(16, 16, 16, 16)
        # 表单整体水平居中（标签+字段一组居中排布）
        time_form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        # 字段保持自身尺寸，不横向撑满，才能真正被居中
        time_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        # 计薪天数框右侧加"（自动计算）"标签
        work_days_row = QWidget()
        work_days_box = QHBoxLayout(work_days_row)
        work_days_box.setContentsMargins(0, 0, 0, 0)
        work_days_box.setSpacing(6)
        self.work_days.setFixedWidth(120)
        work_days_box.addWidget(self.work_days)
        work_days_box.addWidget(QLabel("（自动计算）"))
        work_days_box.addStretch(1)
        time_form.addRow("每月计薪天数", work_days_row)
        time_form.addRow("上班时间", self.work_start)
        time_form.addRow("下班时间", self.work_end)
        time_form.addRow("午休开始", self.lunch_start)
        time_form.addRow("午休结束", self.lunch_end)
        time_form.addRow(self.dinner_enabled)
        time_form.addRow("晚餐开始", self.dinner_start)
        time_form.addRow("晚餐结束", self.dinner_end)
        time_tab = QWidget()
        time_outer = QVBoxLayout(time_tab)
        time_outer.setContentsMargins(0, 0, 0, 0)
        # 用左右弹簧夹住表单，使标签+字段整组在 tab 内水平居中
        time_center = QHBoxLayout()
        time_center.addStretch(1)
        time_center.addLayout(time_form)
        time_center.addStretch(1)
        time_outer.addLayout(time_center)
        time_outer.addStretch(1)

        self._time_form = time_form  # 供显隐晚餐行使用

        # ---- Tab 3：个性化 ----
        personal_tab = self._build_personal_tab()

        # 晚餐相关控件隐藏时仍保留占位高度，避免显隐引起整体上下跳动
        self._dinner_widgets = [
            self.dinner_enabled,
            self.dinner_start,
            time_form.labelForField(self.dinner_start),
            self.dinner_end,
            time_form.labelForField(self.dinner_end),
        ]
        for w in self._dinner_widgets:
            if w is not None:
                sp = w.sizePolicy()
                sp.setRetainSizeWhenHidden(True)
                w.setSizePolicy(sp)

        tabs = QTabWidget()
        tabs.addTab(salary_tab, "薪资")
        tabs.addTab(time_tab, "时间")
        tabs.addTab(personal_tab, "个性化")
        layout.addWidget(tabs)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 任意输入变化时刷新预览
        for w in (
            self.monthly_salary,
            self.annual_bonus_months,
            self.social_base_custom,
            self.pension_base,
            self.medical_base,
            self.unemployment_base,
            self.housing_fund_base,
            self.pension_rate,
            self.medical_rate,
            self.unemployment_rate,
            self.housing_fund_rate,
            self.other_insurance,
            self.special_deduction,
            self.work_days,
        ):
            w.valueChanged.connect(self._update_preview)
        self.social_base_mode.currentIndexChanged.connect(self._update_preview)
        self.bonus_tax_mode.currentIndexChanged.connect(self._update_preview)
        self.bonus_in_average.toggled.connect(self._update_preview)

        # 时间控件变化：刷新预览；下班时间变化还需联动晚餐行显隐
        for te in (
            self.work_start,
            self.work_end,
            self.lunch_start,
            self.lunch_end,
            self.dinner_start,
            self.dinner_end,
        ):
            te.timeChanged.connect(self._update_preview)
        self.work_end.timeChanged.connect(self._update_dinner_visibility)
        self.dinner_enabled.toggled.connect(self._update_dinner_visibility)
        self.dinner_enabled.toggled.connect(self._update_preview)

    def _time_edit(self) -> QTimeEdit:
        te = QTimeEdit()
        te.setDisplayFormat("HH:mm")
        te.setFixedWidth(220)
        return te

    def _spin(self, minimum, maximum, step, suffix):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setSuffix(suffix)
        spin.setFixedWidth(220)
        return spin

    def _build_personal_tab(self) -> QWidget:
        """构建“个性化”分栏：悬浮数字颜色、透明度、悬浮恢复不透明。"""
        # 颜色选择：一排可点击的颜色圆圈，互斥选中
        self._color_group = QButtonGroup(self)
        self._color_group.setExclusive(True)
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(10)
        for i, (name, hex_color) in enumerate(NUMBER_COLORS):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            btn.setProperty("hex", hex_color)
            self._style_color_button(btn, hex_color, checked=False)
            btn.toggled.connect(
                lambda checked, b=btn, h=hex_color: self._on_color_toggled(
                    checked, b, h
                )
            )
            self._color_group.addButton(btn, i)
            color_row.addWidget(btn)
        color_row.addStretch(1)
        color_wrap = QWidget()
        color_wrap.setLayout(color_row)

        # 透明度滑块：0~60（%）
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 60)
        self.opacity_slider.setSingleStep(5)
        self.opacity_slider.setPageStep(10)
        self.opacity_slider.setFixedWidth(180)
        self.opacity_value_label = QLabel("0%")
        # 固定宽度并右对齐，避免百分比数字变化时整体排版抖动
        self.opacity_value_label.setFixedWidth(36)
        self.opacity_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opacity_row = QWidget()
        opacity_box = QHBoxLayout(opacity_row)
        opacity_box.setContentsMargins(0, 0, 0, 0)
        opacity_box.setSpacing(8)
        opacity_box.addWidget(self.opacity_slider)
        opacity_box.addWidget(self.opacity_value_label)
        opacity_box.addStretch(1)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value_label.setText(f"{v}%")
        )

        self.hover_restore = QCheckBox("鼠标悬浮时恢复透明度")

        # 小数位数：不显示 / 1 位 / 2 位（索引即位数）
        self.decimals_combo = QComboBox()
        self.decimals_combo.addItems(["不显示小数", "显示1位小数", "显示2位小数"])
        self.decimals_combo.setFixedWidth(220)

        personal_form = QFormLayout()
        personal_form.setSpacing(10)
        personal_form.setContentsMargins(16, 16, 16, 16)
        personal_form.addRow("数字颜色", color_wrap)
        personal_form.addRow("数字透明度", opacity_row)
        # 用空标签占据标签列，使勾选项左边与滑块（字段列）对齐
        personal_form.addRow("", self.hover_restore)
        personal_form.addRow("小数点位数", self.decimals_combo)

        personal_tab = QWidget()
        personal_outer = QVBoxLayout(personal_tab)
        personal_outer.setContentsMargins(0, 0, 0, 0)
        personal_outer.addLayout(personal_form)
        personal_outer.addStretch(1)
        return personal_tab

    def _style_color_button(self, btn: QPushButton, hex_color: str, checked: bool):
        """按选中状态设置颜色圆圈样式（选中时加深色描边）。"""
        border = "2.5px solid #a98a3f" if checked else "1.5px solid #e6d9a8"
        btn.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; border: {border};"
            f" border-radius: 13px; }}"
        )

    def _on_color_toggled(self, checked: bool, btn: QPushButton, hex_color: str):
        self._style_color_button(btn, hex_color, checked)

    def _selected_color(self) -> str:
        """返回当前选中的颜色十六进制，未选中时回退默认。"""
        btn = self._color_group.checkedButton()
        if btn is not None:
            return btn.property("hex")
        return NUMBER_COLORS[0][1]

    def _on_base_mode_changed(self):
        idx = self.social_base_mode.currentIndex()
        # 0=按工资 1=设定统一基数 2=设定独立基数
        # 统一基数行仅在"设定统一基数"时显示；独立基数行仅在"设定独立基数"时显示
        self._salary_form.setRowVisible(self.social_base_custom, idx == 1)
        self._salary_form.setRowVisible(self._bases_row, idx == 2)

    def _on_city_changed(self):
        """切换所在地时，按城市自动填充养老/医疗/失业比例。"""
        if getattr(self, "_loading", False):
            return
        rates = CITY_RATES.get(self.city.currentText())
        if rates:
            self.pension_rate.setValue(rates["pension"])
            self.medical_rate.setValue(rates["medical"])
            self.unemployment_rate.setValue(rates["unemployment"])

    def _update_dinner_visibility(self):
        """下班晚于 19:00 才显示晚餐勾选；勾选后才显示晚餐起止时间。
        用 setVisible 切换可见性（配合 RetainSizeWhenHidden 保留占位），
        而非 setRowVisible 移除行，避免显隐引起整体上下跳动。"""
        late = self.work_end.time() >= QTime(19, 0)
        self.dinner_enabled.setVisible(late)
        # 下班不晚于 19:00 时，强制取消勾选
        if not late and self.dinner_enabled.isChecked():
            self.dinner_enabled.setChecked(False)
        show_times = late and self.dinner_enabled.isChecked()
        self.dinner_start.setVisible(show_times)
        self.dinner_end.setVisible(show_times)
        start_label = self._time_form.labelForField(self.dinner_start)
        end_label = self._time_form.labelForField(self.dinner_end)
        if start_label is not None:
            start_label.setVisible(show_times)
        if end_label is not None:
            end_label.setVisible(show_times)

    def _load_from_config(self):
        self._loading = True
        c = self.config
        self.monthly_salary.setValue(c.monthly_salary)
        self.annual_bonus_months.setValue(c.annual_bonus_months)
        self.bonus_in_average.setChecked(c.bonus_in_average)
        self.bonus_tax_mode.setCurrentIndex(
            1 if c.bonus_tax_mode == "separate" else 0
        )
        idx = self.city.findText(c.city)
        self.city.setCurrentIndex(idx if idx >= 0 else 0)
        self.social_base_mode.setCurrentIndex(
            {"salary": 0, "custom": 1, "individual": 2}.get(c.social_base_mode, 0)
        )
        self.social_base_custom.setValue(c.social_base_custom)
        self.pension_base.setValue(c.pension_base)
        self.medical_base.setValue(c.medical_base)
        self.unemployment_base.setValue(c.unemployment_base)
        self.housing_fund_base.setValue(c.housing_fund_base)
        self.pension_rate.setValue(c.pension_rate)
        self.medical_rate.setValue(c.medical_rate)
        self.unemployment_rate.setValue(c.unemployment_rate)
        self.housing_fund_rate.setValue(c.housing_fund_rate)
        self.other_insurance.setValue(c.other_insurance)
        self.special_deduction.setValue(c.special_deduction)
        # 计薪天数按当月实际工作日自动计算（打开设置页时即为最新）
        today = date.today()
        self.work_days.setValue(workdays.workdays_in_month(today.year, today.month))
        self.work_start.setTime(_to_qtime(c.work_start))
        self.work_end.setTime(_to_qtime(c.work_end))
        self.lunch_start.setTime(_to_qtime(c.lunch_start))
        self.lunch_end.setTime(_to_qtime(c.lunch_end))
        self.dinner_start.setTime(_to_qtime(c.dinner_start))
        self.dinner_end.setTime(_to_qtime(c.dinner_end))
        self.dinner_enabled.setChecked(c.dinner_enabled)
        # 个性化：选中与当前颜色匹配的圆圈（无匹配则默认第一个）
        color_idx = next(
            (i for i, (_, hx) in enumerate(NUMBER_COLORS) if hx == c.number_color),
            0,
        )
        self._color_group.button(color_idx).setChecked(True)
        self.opacity_slider.setValue(c.number_opacity)
        self.opacity_value_label.setText(f"{c.number_opacity}%")
        self.hover_restore.setChecked(c.hover_restore_opacity)
        self.decimals_combo.setCurrentIndex(max(0, min(2, c.number_decimals)))
        self._on_base_mode_changed()
        self._update_dinner_visibility()
        self._loading = False

    def _collect_config(self) -> Config:
        return Config(
            monthly_salary=self.monthly_salary.value(),
            annual_bonus_months=self.annual_bonus_months.value(),
            bonus_in_average=self.bonus_in_average.isChecked(),
            bonus_tax_mode=(
                "separate" if self.bonus_tax_mode.currentIndex() == 1 else "combined"
            ),
            city=self.city.currentText(),
            social_base_mode=(
                {0: "salary", 1: "custom", 2: "individual"}[
                    self.social_base_mode.currentIndex()
                ]
            ),
            social_base_custom=self.social_base_custom.value(),
            pension_base=self.pension_base.value(),
            medical_base=self.medical_base.value(),
            unemployment_base=self.unemployment_base.value(),
            housing_fund_base=self.housing_fund_base.value(),
            pension_rate=self.pension_rate.value(),
            medical_rate=self.medical_rate.value(),
            unemployment_rate=self.unemployment_rate.value(),
            housing_fund_rate=self.housing_fund_rate.value(),
            other_insurance=self.other_insurance.value(),
            special_deduction=self.special_deduction.value(),
            work_days_per_month=self.work_days.value(),
            work_start=_from_qtime(self.work_start.time()),
            work_end=_from_qtime(self.work_end.time()),
            lunch_start=_from_qtime(self.lunch_start.time()),
            lunch_end=_from_qtime(self.lunch_end.time()),
            dinner_enabled=self.dinner_enabled.isChecked(),
            dinner_start=_from_qtime(self.dinner_start.time()),
            dinner_end=_from_qtime(self.dinner_end.time()),
            number_color=self._selected_color(),
            number_opacity=self.opacity_slider.value(),
            hover_restore_opacity=self.hover_restore.isChecked(),
            number_decimals=self.decimals_combo.currentIndex(),
        )

    def _update_preview(self):
        if getattr(self, "_loading", False):
            return
        result = calculator.calculate(self._collect_config())
        avg_label = "月均到手（含年终）" if self.bonus_in_average.isChecked() else "月均到手（不含年终）"
        self.preview_label.setText(
            f"五险一金个人部分：{result.insurance_total:,.2f} 元/月\n"
            f"全年个税：{result.annual_tax:,.2f} 元\n"
            f"{avg_label}：{result.monthly_avg_net:,.2f} 元\n"
            f"到手日薪：{result.daily_net:,.2f} 元/天（当月工作日 {result.work_days} 天）"
        )

    def _on_save(self):
        self.config = self._collect_config()
        save_config(self.config)
        self.accept()
