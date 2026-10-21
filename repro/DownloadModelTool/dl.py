#!/usr/bin/env python3
"""独立模型下载工具的入口：python dl.py <子命令> [参数]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dltool.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
