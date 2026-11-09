"""工作日计算模块。

数据源：holiday-cn 开源项目（https://github.com/NateScarlet/holiday-cn），
按年提供中国法定节假日与调休补班日的 JSON 数据。

- isOffDay == True  ：法定放假（即使是工作日也不上班）
- isOffDay == False ：调休补班（即使是周末也要上班）

数据按年缓存在 ~/.earn_today/holidays/<year>.json，
联网失败时回退为"仅排除周末"的估算。
"""

from __future__ import annotations

import calendar
import json
import os
import threading
import urllib.request
from datetime import date

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".earn_today", "holidays")
DATA_URL = "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"

# 内存缓存：{year: {date_str: isOffDay}}
_memory_cache = {}

# 并发控制：已在本次会话中尝试过下载的年份（避免重复起线程/失败后每秒重试）
_attempted = set()
_lock = threading.Lock()

# 数据到位后的回调（在后台线程中调用），供 UI 层刷新
_load_callbacks = []


def register_load_callback(cb) -> None:
    """注册一个回调：某年节假日数据后台加载完成时调用（参数为年份 int）。
    注意：回调在后台线程中被调用，UI 更新需自行切回主线程。"""
    _load_callbacks.append(cb)


def _load_from_cache(year: int) -> dict | None:
    """仅从内存/本地文件缓存加载（不联网），找不到返回 None。"""
    if year in _memory_cache:
        return _memory_cache[year]

    cache_path = os.path.join(CACHE_DIR, f"{year}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            table = {d["date"]: d["isOffDay"] for d in data.get("days", [])}
            _memory_cache[year] = table
            return table
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    return None


def _download_year(year: int) -> None:
    """后台线程：下载某年数据，成功后写入缓存并通知回调。"""
    try:
        url = DATA_URL.format(year=year)
        with urllib.request.urlopen(url, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        table = {d["date"]: d["isOffDay"] for d in data.get("days", [])}
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, f"{year}.json"), "w", encoding="utf-8") as f:
            f.write(raw)
        _memory_cache[year] = table
    except Exception:
        return  # 失败则保持估算，不通知；本次会话不再重试
    for cb in list(_load_callbacks):
        try:
            cb(year)
        except Exception:
            pass


def _load_year(year: int) -> dict | None:
    """加载某年的节假日调整表，返回 {"YYYY-MM-DD": isOffDay}。

    优先返回本地缓存；若无缓存，则触发后台下载（每年每会话仅一次）并立即返回
    None，由调用方回退为"仅排除周末"估算，避免阻塞主线程。
    """
    table = _load_from_cache(year)
    if table is not None:
        return table
    with _lock:
        if year not in _attempted:
            _attempted.add(year)
            threading.Thread(
                target=_download_year, args=(year,), daemon=True
            ).start()
    return None


def is_workday(day: date) -> bool:
    """判断某一天是否为需要上班的工作日。

    规则：先看节假日表的特殊标记，再按周末判断。
    数据不可用时回退为"周一至周五即工作日"。
    """
    table = _load_year(day.year)
    key = day.isoformat()
    if table is not None and key in table:
        # isOffDay True=放假不上班；False=调休补班要上班
        return not table[key]
    # 无特殊标记：周末休息，工作日上班
    return day.weekday() < 5


def workdays_in_month(year: int, month: int) -> int:
    """计算指定月份的实际工作日天数（含调休补班，排除法定节假日）。"""
    _, days_in_month = calendar.monthrange(year, month)
    count = 0
    for d in range(1, days_in_month + 1):
        if is_workday(date(year, month, d)):
            count += 1
    return count
