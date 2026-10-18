#!/usr/bin/env python3
"""
命令行交互调试父亲数字人人格
用法：
  python scripts/03_test_dialogue.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.config_loader import load_config
from modules.bot.gateway import BotGateway


def main():
    print("=" * 60)
    print(" 父亲微信数字人 - 命令行对话调试")
    print(" 输入 'exit' 或 'quit' 退出，输入 'clear' 清空会话历史")
    print("=" * 60)

    config = load_config()
    gateway = BotGateway(config)

    while True:
        try:
            user_input = input("\n[我]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit"]:
            print("退出对话。")
            break
        if user_input.lower() == "clear":
            gateway.clear_history()
            print("[会话历史已清空]")
            continue

        result = gateway.handle_message(user_input, need_voice=False)
        reply = result.get("text", "")
        memories = result.get("triggered_memories", [])

        print(f"[父亲]: {reply}")
        if memories:
            print(f"       *(唤醒记忆: {', '.join(memories)})*")


if __name__ == "__main__":
    main()

