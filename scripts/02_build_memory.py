#!/usr/bin/env python3
"""
记忆库与问答对注入脚本
用法：
  python scripts/02_build_memory.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.config_loader import load_config
from modules.memory.memory_manager import MemoryManager


def main():
    config = load_config()
    memory_dir = config.get("paths", {}).get("memory_dir", "data/memory")
    processed_dir = Path(config.get("paths", {}).get("data_processed_dir", "data/processed"))

    qa_file = processed_dir / "qa_pairs.json"
    manager = MemoryManager(memory_dir)

    if qa_file.exists():
        with open(qa_file, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)
        manager.set_qa_database(qa_pairs)
        print(f"[+] 成功将 {len(qa_pairs)} 组历史对话问答注入记忆库 ({manager.qa_store_path})")
    else:
        print(f"[提示] 未找到 {qa_file}，请先运行 01_import_and_clean.py 生成清洗数据。")

    print(f"[+] 当前人物画像文件位于: {manager.profile_path}")
    print(f"[+] 当前情境记忆文件位于: {manager.memories_path}")
    print("您可以随时使用文本编辑器手动编辑上述文件，添加父亲喜爱的习惯和生平故事。")


if __name__ == "__main__":
    main()

