"""项目统一异常。

本文件只定义类型；捕获与降级策略待实现。
"""

from __future__ import annotations


class TravelAssistantError(Exception):
    """本项目所有自定义异常的基类。"""


class ParseError(TravelAssistantError):
    """自然语言解析失败：无法从文本中识别出可用的行程或意图。"""


class DataError(TravelAssistantError):
    """数据层错误：缺文件、表头不符、引用不存在的节点等。"""