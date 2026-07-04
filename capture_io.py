"""捕获条目的文件保存工具（纯逻辑，无 Qt 依赖，便于单测）。"""

from __future__ import annotations

import os
from typing import Iterable

# 在 Windows/macOS 上不适合做文件名的字符
_ILLEGAL_FILENAME_CHARS = set('/\\:*?"<>|')
_FILENAME_FALLBACK = "capture"


def sanitize_filename(name: str) -> str:
    """把不适合做文件名的字符替换为下划线。

    - 去掉首尾空白
    - 非法字符 / \\ : * ? " < > | 及控制字符（ord < 32）→ "_"
    - 结果为空时回退为 "capture"
    """
    stripped = name.strip()
    cleaned = "".join(
        "_" if (ch in _ILLEGAL_FILENAME_CHARS or ord(ch) < 32) else ch
        for ch in stripped
    )
    return cleaned or _FILENAME_FALLBACK


def resolve_unique_path(directory: str, base: str, ext: str, used: set[str]) -> str:
    """在 directory 下为 base+ext 找一个不冲突的完整路径。

    冲突判定同时考虑 used（本批已分配的路径）与磁盘上已存在的文件；
    冲突时依次尝试 base_1、base_2…。返回的路径会登记进 used。
    """
    candidate = os.path.join(directory, base + ext)
    counter = 1
    while candidate in used or os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base}_{counter}{ext}")
        counter += 1
    used.add(candidate)
    return candidate


def write_spectrum_csv(x: Iterable, y: Iterable, path: str) -> None:
    """把光谱数据逐行写成 "xi,yi" 的 CSV（无表头，与单个保存保持一致）。"""
    with open(path, "w") as f:
        for xi, yi in zip(x, y):
            f.write(f"{xi},{yi}\n")


def copy_screenshot(src: str, path: str) -> None:
    """把截图文件按原始字节拷贝到目标路径。"""
    with open(src, "rb") as fin, open(path, "wb") as fout:
        fout.write(fin.read())
