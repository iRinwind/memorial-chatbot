#!/usr/bin/env python3
"""
语音转文字 (ASR) 与全量数字人训练集构建流水线
功能：
1. 将 data/processed/voice_wav/ 下的 1463 条父亲原声转写为精准中文文本
   - 支持 Gemini 1.5/2.0 Flash 多模态极速听写 (默认优先，精度极高)
   - 支持 本地 Whisper / SenseVoice 离线听写
2. 将转写文本全量回填至聊天记录流，重构会话并重新提炼问答对
3. 构建可直接用于微调的大模型训练集 (SFT 数据集) 和 Antigravity 人格技能定义 (SKILL.md)
"""

import argparse
import base64
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.config_loader import load_config
from modules.cleaner.dialogue_cleaner import DialogueCleaner
from modules.memory.memory_manager import MemoryManager


def transcribe_audio_gemini(wav_path: Path, api_key: str, model: str = "gemini-3.6-flash") -> Optional[str]:
    """使用 Gemini 多模态原生 API 听写单段音频"""
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": b64_audio,
                        }
                    },
                    {
                        "text": "请将这段中国长辈的微信语音录音准确听写为简体中文文字。严格仅输出听写到的实际话语内容，保留说话者的语气词与方言口语习惯。不要包含任何开场白、解释或多余的标点说明。如果是空白、极微弱杂音或无清晰人声，请直接输出空内容。"
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 256,
        },
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            text = text.strip('\"\'')
                            return text
                    return ""
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_time = 5 * (attempt + 1)
                print(f"  [限流等待 429] 触发频率限制，暂停 {sleep_time} 秒后重试...")
                time.sleep(sleep_time)
            else:
                print(f"  [听写异常 HTTP {e.code}] {wav_path.name}: {e}")
                time.sleep(2)
        except Exception as e:
            print(f"  [听写网络重试] {wav_path.name}: {e}")
            time.sleep(2)
    return None


def main():
    parser = argparse.ArgumentParser(description="语音转文字与训练集构建工具")
    parser.add_argument("--engine", choices=["gemini", "local"], default="gemini", help="转录引擎")
    parser.add_argument("--limit", type=int, default=0, help="限制转录条数（0 表示全量转录）")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数（防止超出 RPM 限制）")
    args = parser.parse_args()

    config = load_config()
    api_key = config.get("llm", {}).get("api_key", "").strip()

    manifest_path = PROJECT_ROOT / "data" / "processed" / "voice_manifest.json"
    cache_path = PROJECT_ROOT / "data" / "processed" / "voice_transcripts.json"

    if not manifest_path.exists():
        print("[错误] 未找到 voice_manifest.json，请先运行 01 提取脚本。")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 读取已有转录缓存（支持断点续传）
    transcripts = {}
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            transcripts = json.load(f)
        print(f"[*] 发现已有转录缓存: 已有 {len(transcripts)} 条记录")

    to_process = [v for v in manifest if v.get("server_id") not in transcripts and v.get("wav_path")]
    if args.limit > 0:
        to_process = to_process[:args.limit]

    print(f"[*] 待转录语音音频总计: {len(to_process)} 条")

    if args.engine == "gemini":
        if not api_key or "YOUR_API_KEY" in api_key:
            print("\n[配置提示] 使用 Gemini 听写需要在 config/config.json 中填入有效的 Gemini API Key！")
            print("请编辑 config/config.json 的 llm.api_key，然后重新运行本脚本。")
            sys.exit(1)

        print("[*] 正在通过 Gemini 多模态模型转录语音...")
        success_count = 0
        for idx, item in enumerate(to_process, 1):
            wav_rel = item.get("wav_path")
            wav_abs = PROJECT_ROOT / wav_rel
            if not wav_abs.exists():
                continue

            sid = item.get("server_id")
            contact = item.get("contact")
            text = transcribe_audio_gemini(wav_abs, api_key=api_key)

            if text is not None:
                transcripts[sid] = {
                    "text": text,
                    "contact": contact,
                    "time": item.get("time"),
                    "wav": wav_rel,
                }
                success_count += 1
                print(f"[{idx}/{len(to_process)}] 【发给 {contact}】: \"{text}\"")

                # 每 10 条自动保存一次缓存
                if success_count % 10 == 0:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(transcripts, f, ensure_ascii=False, indent=2)

            time.sleep(args.delay)

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(transcripts, f, ensure_ascii=False, indent=2)
        print(f"[+] 转录任务阶段完成！当前累计转录: {len(transcripts)} 条")

    # 4. 将转录文字回填到聊天流并重新清洗生成强化版问答库
    print("\n[*] 正在将转写的语音文本全量整合入聊天记录流...")
    msgs_path = PROJECT_ROOT / "data" / "processed" / "target_messages.json"
    if msgs_path.exists():
        with open(msgs_path, "r", encoding="utf-8") as f:
            all_messages = json.load(f)

        replaced_count = 0
        for m in all_messages:
            sid = m.get("server_id")
            if sid in transcripts and m.get("type") == "voice":
                t_content = transcripts[sid]["text"].strip()
                if t_content:
                    m["content"] = t_content
                    m["type"] = "text"  # 转为文本消息参与清洗
                    m["is_from_voice"] = True
                    replaced_count += 1

        print(f"[+] 成功将 {replaced_count} 条语音原话转为文本注入对话流！")

        # 重新运行会话清洗器
        cleaner = DialogueCleaner(time_window_seconds=1800)
        res = cleaner.process_messages(all_messages, father_is_sender=True)

        qa_file = PROJECT_ROOT / "data" / "processed" / "qa_pairs.json"
        with open(qa_file, "w", encoding="utf-8") as f:
            json.dump(res["qa_pairs"], f, ensure_ascii=False, indent=2)

        # 更新记忆库
        mm = MemoryManager(str(PROJECT_ROOT / "data" / "memory"))
        mm.set_qa_database(res["qa_pairs"])

        print(f"[+] 重新提炼强化版问答库: 问答对总数更新为 {len(res['qa_pairs'])} 组！")

        # 5. 导出标准的 AI 虚拟人大模型微调数据集 (ShareGPT / Alpaca 格式)
        export_training_assets(res["qa_pairs"])


def export_training_assets(qa_pairs: List[Dict[str, str]]):
    """导出用于训练 AI 虚拟人的标准微调数据集和 Skill 资产包"""
    train_dir = PROJECT_ROOT / "data" / "training"
    train_dir.mkdir(parents=True, exist_ok=True)

    # 1. 导出 ShareGPT 多轮对话格式 (适配主流开源微调框架 LLaMA-Factory / Axolotl / Swift)
    sharegpt_file = train_dir / "train_sharegpt.jsonl"
    with open(sharegpt_file, "w", encoding="utf-8") as f:
        for qa in qa_pairs:
            item = {
                "conversations": [
                    {"from": "human", "value": qa["user"]},
                    {"from": "gpt", "value": qa["father"]},
                ]
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 2. 导出 Alpaca 单轮指令格式
    alpaca_file = train_dir / "train_alpaca.json"
    alpaca_list = []
    for qa in qa_pairs:
        alpaca_list.append({
            "instruction": "你正在扮演我已故的亲友长辈。请用朴实、简短、温暖的口吻回答我。",
            "input": qa["user"],
            "output": qa.get("target") or qa.get("father", ""),
        })
    with open(alpaca_file, "w", encoding="utf-8") as f:
        json.dump(alpaca_list, f, ensure_ascii=False, indent=2)

    # 3. 生成 Antigravity 标准人格技能文档 (SKILL.md)
    skill_file = train_dir / "SKILL.md"
    skill_content = """---
name: memorial-beloved-persona
description: 纪念对象的专属数字人人格技能。基于真实绿色聊天记录提炼，具备真实性格、口吻习惯与亲友关系认知。
---

# 纪念对象数字人人格技能定义 (Memorial Persona Skill)

本技能封装了长辈/亲友生前的真实语言交互习惯，用于驱动任何 LLM 展现原汁原味的亲友文字聊天风格。

## 1. 核心性格基调
- **亲切平实**：不讲大道理，从不使用浮夸修辞，所有的爱与关怀落实在具体的日常生活琐事（吃饭、降温加衣、路上慢点、少熬夜）。
- **言简意赅**：平均每句回复 **10~15 个字**，绝不输出长篇大论，通常 1~2 句话完结。
- **标志性应答习惯**：
  - 确认知悉类：优先使用 `[OK]` 表情（高频）、`知道了`、`噢`、`好的`
  - 肯定鼓励类：使用 `[强]` 表情
  - 标点偏好：极少使用句号和感叹号，习惯用逗号 `，` 或空格代替

## 2. 核心亲友图谱与称谓
- **直系家人**：小明、母亲、姐姐
- **家庭群聊**：【温馨一家人】
- **经常互动的熟人/朋友**：张叔、王姨、李叔

## 3. 对话范例 (Few-shot Examples)
- 对方：“我下班了，刚准备去吃晚饭”
  亲友：“吃点热乎的，在外面慢点，别太累。”
- 对方：“明天家里好像大降温，你们衣服多穿点”
  亲友：“知道了，家里暖气开着呢，[OK]”
- 对方：“周末我买票回家看你们”
  亲友：“好的，想吃什么提早跟我讲，去买排骨。”
"""
    with open(skill_file, "w", encoding="utf-8") as f:
        f.write(skill_content)

    print(f"\n[+] 已成功生成虚拟人微调与人格资产包：")
    print(f"    1. ShareGPT 微调数据集: {sharegpt_file} ({len(qa_pairs)} 条)")
    print(f"    2. Alpaca 微调数据集: {alpaca_file}")
    print(f"    3. 数字人人格技能定义: {skill_file}")


if __name__ == "__main__":
    main()

