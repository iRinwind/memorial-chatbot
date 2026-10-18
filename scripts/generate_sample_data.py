#!/usr/bin/env python3
"""
生成样例测试聊天数据
用于在未放置真实微信备份时，验证全套流水线与功能
"""

import json
from pathlib import Path


def generate_sample_chat():
    sample_dir = Path("data/raw")
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_file = sample_dir / "sample_chat.json"

    records = [
        # Session 1: 关心晚饭与工作
        {
            "msg_id": "1001",
            "sender": "user",
            "is_sender": 0,
            "type": 1,
            "content": "爸，今天加班，刚下班准备去吃点东西",
            "timestamp": 1690000000,
        },
        {
            "msg_id": "1002",
            "sender": "father",
            "is_sender": 1,
            "type": 1,
            "content": "这么晚才吃。别吃太油腻的，找家干净的热汤面吃，天冷。",
            "timestamp": 1690000060,
        },
        {
            "msg_id": "1003",
            "sender": "user",
            "is_sender": 0,
            "type": 1,
            "content": "好的，我知道了，您和妈吃过了吗？",
            "timestamp": 1690000100,
        },
        {
            "msg_id": "1004",
            "sender": "father",
            "is_sender": 1,
            "type": 1,
            "content": "早吃过了。不用操心我们，你吃完早点回宿舍休息，别熬夜。",
            "timestamp": 1690000140,
        },

        # Session 2: 天气与生活叮嘱 (间隔2天)
        {
            "msg_id": "1005",
            "sender": "user",
            "is_sender": 0,
            "type": 1,
            "content": "爸，我看天气预报家里明天大降温，你们记得把厚棉袄翻出来穿上。",
            "timestamp": 1690200000,
        },
        {
            "msg_id": "1006",
            "sender": "father",
            "is_sender": 1,
            "type": 1,
            "content": "看到了。家里地暖开着呢，不冷。你那边风大，出门把帽子围巾戴好。",
            "timestamp": 1690200100,
        },

        # Session 3: 杂项/系统消息测试 (会被自动过滤)
        {
            "msg_id": "1007",
            "sender": "system",
            "is_sender": 0,
            "type": 10000,
            "content": "你拍了拍“父亲”",
            "timestamp": 1690300000,
        },
        {
            "msg_id": "1008",
            "sender": "user",
            "is_sender": 0,
            "type": 1,
            "content": "爸，周末我买票回家看你们。",
            "timestamp": 1690300050,
        },
        {
            "msg_id": "1009",
            "sender": "father",
            "is_sender": 1,
            "type": 1,
            "content": "好啊。想吃什么提早跟我说，我去菜场买你爱吃的排骨和河虾。",
            "timestamp": 1690300100,
        },
    ]

    with open(sample_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[+] 已生成测试微信聊天数据: {sample_file}")


if __name__ == "__main__":
    generate_sample_chat()

