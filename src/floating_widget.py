"""桌面浮窗。

显示"今天已经赚了的金额"，按工作时段实时累计。
- 左键拖动可移动浮窗
- 右键弹出菜单：进入设置页 / 退出程序
"""

import os
import sys
from datetime import date, datetime, time

try:
    import objc
except ImportError:
    objc = None

from PySide6.QtCore import Qt, QTimer, QSize, Signal, QByteArray
from PySide6.QtGui import QAction, QCursor, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import calculator
from . import workdays
from .config import load_config, save_config
from .resources import resource_path
from .settings_dialog import SettingsDialog


APP_ICON = resource_path("AppIcon.png")

# 大头钉图标：未插（不置顶）/ 已插（置顶）
PIN_OFF_ICON = resource_path("pin_off.svg")
PIN_ON_ICON = resource_path("pin_on.svg")

# Comic Mono：软润可爱的等宽字体（随项目附带，避免依赖系统安装）
FONT_PATH = resource_path("fonts", "ComicMono.ttf")

# 右键菜单：与设置页一致的淡黄可爱风
MENU_STYLE = """
QMenu {
    background: #fffffd;
    border: 1.5px solid #fdf6dc;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    background: transparent;
    color: #a98a3f;
    font-size: 13px;
    padding: 7px 22px;
    border-radius: 8px;
}
QMenu::item:selected {
    background: #fcf2c8;
    color: #8a7233;
}
QMenu::separator {
    height: 1.5px;
    background: #fdf6dc;
    margin: 5px 8px;
}
"""

def _parse_time(text: str) -> time:
    """将 "HH:MM" 字符串解析为 time，非法时回退 09:00。"""
    try:
        h, m = text.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return time(9, 0)


class FloatingWidget(QWidget):
    # 后台线程加载完节假日数据后发射（携带年份），用于切回主线程刷新
    holidays_loaded = Signal(int)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.result = calculator.calculate(self.config)
        self._calc_month = date.today().month  # 记录当前计算所属月份，跨月重算

        self._drag_pos = None

        self._build_ui()
        self._init_window()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)  # 每秒刷新
        self._refresh()

        # 悬停轮询：兜底处理后台窗口收不到 enter/leave 事件的情况
        self.hover_timer = QTimer(self)
        self.hover_timer.timeout.connect(self._poll_hover)
        self.hover_timer.start(200)

        # 节假日数据后台加载完成后重算日薪并刷新（信号确保回到主线程执行）
        self.holidays_loaded.connect(self._on_holidays_loaded)
        workdays.register_load_callback(self.holidays_loaded.emit)

    def _on_holidays_loaded(self, year: int):
        """后台节假日数据到位后，重算并刷新（此前用的是仅排除周末的估算）。"""
        self.result = calculator.calculate(self.config)
        self._refresh()

    def _init_window(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        # 仅在已固定时才加 Qt 层级置顶提示；默认启动不置顶
        if self.config.pinned:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if os.path.exists(APP_ICON):
            self.setWindowIcon(QIcon(APP_ICON))
        self.resize(180, 70)
        # 位置：优先恢复上次退出时的位置，否则用默认（屏幕右上角附近）
        if self.config.pos_x is not None and self.config.pos_y is not None:
            self.move(self.config.pos_x, self.config.pos_y)
        else:
            self.move(1000, 80)

    def showEvent(self, event):
        super().showEvent(event)
        # 窗口原生句柄在 show 后才可用，按已保存的 pinned 状态应用原生层级
        self._set_window_level("status" if self.config.pinned else "normal")

    def _set_window_level(self, level_name: str):
        """macOS：设置浮窗的原生层级。仅在 macOS 且 pyobjc 可用时生效。
        level_name: 'status' 置顶（压过普通 app 窗口），'normal' 恢复普通层级。"""
        if sys.platform != "darwin" or objc is None:
            return
        try:
            import AppKit
        except ImportError:
            return
        view = objc.objc_object(c_void_p=int(self.winId()))
        window = view.window()
        if window is None:
            return
        if level_name == "status":
            # 状态栏级：高于普通窗口，但不至于盖住菜单/通知；跨所有 Space 显示
            window.setLevel_(AppKit.NSStatusWindowLevel)
            # Qt.Tool 在 macOS 上是 NSPanel，默认 hidesOnDeactivate=YES，
            # 会在 app 失焦时自动隐藏（表现为被其他 app 覆盖），需关闭。
            window.setHidesOnDeactivate_(False)
            window.setCollectionBehavior_(
                AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
                | AppKit.NSWindowCollectionBehaviorStationary
                | AppKit.NSWindowCollectionBehaviorIgnoresCycle
                | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            )
        else:
            window.setLevel_(AppKit.NSNormalWindowLevel)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        family = self._load_font()

        # 数字行：左侧占位弹簧 + 居中数字 + 右侧大头钉按钮，保持数字视觉居中
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.amount_label = QLabel("0.00")
        self.amount_label.setAlignment(Qt.AlignCenter)
        self._font_family = family
        self._apply_number_style(hovering=False)

        # 大头钉按钮：默认隐藏，鼠标移入浮窗时显示；点击切换置顶
        self.pin_button = QPushButton()
        self.pin_button.setFixedSize(22, 22)
        self.pin_button.setIconSize(QSize(16, 16))
        self.pin_button.setCursor(Qt.PointingHandCursor)
        self.pin_button.setToolTip("固定在最上层")
        self.pin_button.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 30);"
            " border-radius: 6px; }"
        )
        self.pin_button.clicked.connect(self._toggle_pin)
        # 隐藏时仍保留占位，避免显隐时数字左右跳动
        sp = self.pin_button.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.pin_button.setSizePolicy(sp)
        self.pin_button.setVisible(False)

        row.addSpacing(22)  # 与右侧按钮等宽，抵消偏移使数字居中
        row.addWidget(self.amount_label, 1)
        row.addWidget(self.pin_button, 0, Qt.AlignVCenter)

        layout.addLayout(row)

        self.setStyleSheet(
            """
            FloatingWidget {
                background: rgba(30, 30, 30, 210);
                border-radius: 12px;
            }
            """
        )
        self._update_pin_icon()

    def _apply_number_style(self, hovering: bool):
        """按配置的颜色与透明度设置数字样式。
        number_opacity 为“透明百分比”(0~60)，0 为完全不透明；
        若开启悬浮恢复且当前处于悬浮，则强制完全不透明。"""
        hex_color = (self.config.number_color or "#fcf2c8").lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        transparent = self.config.number_opacity
        if hovering and self.config.hover_restore_opacity:
            transparent = 0
        alpha = max(0.0, min(1.0, (100 - transparent) / 100.0))
        self.amount_label.setStyleSheet(
            f"color: rgba({r}, {g}, {b}, {alpha:.3f}); font-size: 22px; "
            f"font-weight: bold; font-family: '{self._font_family}', monospace;"
        )

    def _render_pin_icon(self, svg_path: str, color: str) -> QIcon:
        """读取大头钉 SVG，将其颜色替换为指定颜色后渲染成图标。"""
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                svg = f.read()
        except OSError:
            return QIcon(svg_path)
        svg = svg.replace("#fcf2c8", color)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        size = self.pin_button.iconSize()
        dpr = self.devicePixelRatioF()  # Retina 屏通常为 2.0，按物理像素渲染避免模糊
        pixmap = QPixmap(size * dpr)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(dpr)
        return QIcon(pixmap)

    def _update_pin_icon(self):
        """按当前 pinned 状态刷新大头钉图标与提示，颜色跟随数字颜色。"""
        pinned = self.config.pinned
        icon_path = PIN_ON_ICON if pinned else PIN_OFF_ICON
        color = self.config.number_color or "#fcf2c8"
        self.pin_button.setIcon(self._render_pin_icon(icon_path, color))
        self.pin_button.setToolTip("已固定在最上层，点击取消" if pinned else "点击固定在最上层")

    def _toggle_pin(self):
        """切换置顶状态并持久化。"""
        self.config.pinned = not self.config.pinned
        self._set_window_level("status" if self.config.pinned else "normal")
        self._update_pin_icon()
        save_config(self.config)

    def _poll_hover(self):
        """轮询全局鼠标位置判断是否悬停在浮窗上，切换大头钉按钮显隐。
        macOS 上后台窗口（app 未激活）收不到 enter/leave 事件，故用轮询统一处理。"""
        inside = self.geometry().contains(QCursor.pos())
        if inside != self.pin_button.isVisible():
            self.pin_button.setVisible(inside)
            # 悬浮恢复透明度：进出浮窗时刷新数字样式
            if self.config.hover_restore_opacity and self.config.number_opacity > 0:
                self._apply_number_style(hovering=inside)

    def _load_font(self) -> str:
        """加载随项目附带的 Comic Mono 字体，返回其字体族名；
        加载失败则回退到通用等宽字体。"""
        if os.path.exists(FONT_PATH):
            font_id = QFontDatabase.addApplicationFont(FONT_PATH)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
        return "monospace"

    # ---------- 收益计算 ----------
    def _breaks(self) -> list[tuple[time, time]]:
        """返回不计薪的休息时段列表（午休，及启用时的晚餐）。"""
        c = self.config
        breaks = [(_parse_time(c.lunch_start), _parse_time(c.lunch_end))]
        if c.dinner_enabled:
            breaks.append((_parse_time(c.dinner_start), _parse_time(c.dinner_end)))
        return breaks

    def _worked_fraction(self, now: datetime) -> float:
        """返回今日已完成的计薪时间占全天计薪时间的比例(0~1)。"""
        work_start = _parse_time(self.config.work_start)
        work_end = _parse_time(self.config.work_end)
        breaks = self._breaks()

        # 全天计薪总时长 = 上下班区间 - 各休息时段
        total = self._seconds_between(work_start, work_end)
        for b_start, b_end in breaks:
            total -= self._seconds_between(b_start, b_end)
        if total <= 0:
            return 0.0

        cur = now.time()
        if cur <= work_start:
            return 0.0
        if cur >= work_end:
            return 1.0

        worked = self._seconds_between(work_start, cur)
        # 扣除已经过去（含正在进行）的各休息时段
        for b_start, b_end in breaks:
            if cur >= b_end:
                worked -= self._seconds_between(b_start, b_end)
            elif cur > b_start:
                worked -= self._seconds_between(b_start, cur)
        return max(0.0, min(worked / total, 1.0))

    @staticmethod
    def _seconds_between(t1: time, t2: time) -> float:
        s1 = t1.hour * 3600 + t1.minute * 60 + t1.second
        s2 = t2.hour * 3600 + t2.minute * 60 + t2.second
        return max(0.0, s2 - s1)

    def _today_earned(self) -> float:
        now = datetime.now()
        # 非工作日不计薪（排除法定节假日，计入调休补班）
        if not workdays.is_workday(now.date()):
            return 0.0
        return self.result.daily_net * self._worked_fraction(now)

    def _refresh(self):
        # 跨月后按新月份的实际工作日重新计算日薪
        this_month = date.today().month
        if this_month != self._calc_month:
            self._calc_month = this_month
            self.result = calculator.calculate(self.config)
        earned = self._today_earned()
        decimals = max(0, min(2, self.config.number_decimals))
        self.amount_label.setText(f"{earned:,.{decimals}f}")

    # ---------- 拖动 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            # 拖动结束后保存新位置，供下次启动恢复
            pos = self.pos()
            self.config.pos_x = pos.x()
            self.config.pos_y = pos.y()
            save_config(self.config)
        self._drag_pos = None

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        settings_action = QAction("进入设置页", self)
        settings_action.triggered.connect(self._open_settings)
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def _open_settings(self):
        # 打开设置页时把浮窗降回普通层级，避免置顶的浮窗挡住设置页
        self._set_window_level("normal")
        try:
            dialog = SettingsDialog(self.config, self)
            if dialog.exec():
                # 设置页不涉及置顶开关与窗口位置，保留当前状态
                new_config = dialog.config
                new_config.pinned = self.config.pinned
                new_config.pos_x = self.config.pos_x
                new_config.pos_y = self.config.pos_y
                self.config = new_config
                save_config(self.config)
                self.result = calculator.calculate(self.config)
                # 应用个性化设置（颜色/透明度）到数字与大头钉
                self._apply_number_style(
                    hovering=self.geometry().contains(QCursor.pos())
                )
                self._update_pin_icon()
                self._refresh()
        finally:
            # 关闭设置页后按 pinned 状态恢复层级
            self._set_window_level("status" if self.config.pinned else "normal")

    def _quit(self):
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()
