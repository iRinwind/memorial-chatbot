#!/usr/bin/env python3
"""
启动微信数字人 Web 测试面板
用法：
  python scripts/04_run_webui.py [--port 7860]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_ui.server import run_server


def main():
    parser = argparse.ArgumentParser(description="启动数字人 Web 测试界面")
    parser.add_argument("--port", type=int, default=7860, help="Web 服务监听端口 (默认 7860)")
    args = parser.parse_args()

    run_server(port=args.port)


if __name__ == "__main__":
    main()

