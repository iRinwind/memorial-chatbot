#!/usr/bin/env python3
"""
数据导入与清洗流水线
用法：
  python scripts/01_import_and_clean.py [--input data/raw/your_export.json]
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.config_loader import load_config
from modules.parser.wechat_db_parser import WeChatMsgParser
from modules.cleaner.dialogue_cleaner import DialogueCleaner
from modules.parser.silk_decoder import SilkDecoder


def main():
    parser = argparse.ArgumentParser(description="微信备份数据解析与清洗流水线")
    parser.add_argument(
        "--input",
        type=str,
        default="",
        help="原始备份文件或目录路径（默认读取 config.yaml 中的 data_raw_dir）",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="data/processed",
        help="清洗后数据输出目录",
    )
    args = parser.parse_args()

    config = load_config()
    raw_dir = args.input or config.get("paths", {}).get("data_raw_dir", "data/raw")
    raw_path = Path(raw_dir)

    if not raw_path.exists():
        print(f"[错误] 数据路径不存在: {raw_path}")
        print("请将您的微信备份文件（.json/.csv/.db/语音文件）放入 data/raw 目录下，或通过 --input 指定。")
        sys.exit(1)

    print(f"[*] 正在解析原始数据: {raw_path} ...")
    parser_tool = WeChatMsgParser(str(raw_path))
    raw_messages = parser_tool.parse()
    print(f"[+] 成功提取原始记录共: {len(raw_messages)} 条")

    if not raw_messages:
        print("[提示] 未提取到任何有效消息，请检查文件格式。")
        return

    # 清洗与问答提炼
    print("[*] 正在清洗文本与提取会话问答对...")
    cleaner = DialogueCleaner()
    processed_result = cleaner.process_messages(raw_messages, father_is_sender=True)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    qa_file = out_dir / "qa_pairs.json"
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(processed_result["qa_pairs"], f, ensure_ascii=False, indent=2)

    stats_file = out_dir / "father_style_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(processed_result["father_style_stats"], f, ensure_ascii=False, indent=2)

    print(f"[+] 成功提炼对话问答对: {len(processed_result['qa_pairs'])} 对，已保存至 {qa_file}")
    print(f"[+] 父亲语言习惯统计：")
    stats = processed_result["father_style_stats"]
    print(f"    - 发言总数: {stats.get('total_father_messages', 0)} 条")
    print(f"    - 平均字数: {stats.get('average_length_chars', 0)} 字")
    print(f"    - 常用短句: {stats.get('frequent_short_replies', [])}")
    print(f"    - 标点习惯: {stats.get('punctuation_preferences', {})}")


if __name__ == "__main__":
    main()

