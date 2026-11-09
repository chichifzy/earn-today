"""资源路径解析。

开发环境下资源位于项目根目录的 assets/；
使用 PyInstaller 打包后，资源被解压到临时目录 sys._MEIPASS。
统一通过 resource_path() 获取，保证两种情况都能正确定位。
"""

import os
import sys


def resource_path(*parts):
    """返回资源文件的绝对路径，兼容开发运行与 PyInstaller 打包。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        # 开发环境：src/ 的上一级即项目根目录
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", *parts)
