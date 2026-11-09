"""程序入口：启动桌面浮窗。"""

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.floating_widget import FloatingWidget
from src.resources import resource_path


APP_ICON = resource_path("AppIcon.png")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，由右键菜单退出
    if os.path.exists(APP_ICON):
        app.setWindowIcon(QIcon(APP_ICON))

    widget = FloatingWidget()
    widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
