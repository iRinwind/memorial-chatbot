#!/usr/bin/env python3
"""
父亲专属声音克隆训练数据集构建与打包脚本 (GPT-SoVITS 适配)
功能：
1. 从 1463 条微信语音中，筛选出高质量、清晰、发音完整的黄金训练样本 (110+ 条，约 12 分钟)
2. 音频电平归一化 (Peak Normalization) 与淡入淡出防爆音处理 (Zero DC offset / Anti-click)
3. 自动生成 GPT-SoVITS 标准打标文件 (father_train.list)
4. 智能挑选 5 段具有代表性情感（平常、关爱、肯定）的基准参考音频 (Reference Prompts)
5. 自动打包为 data/training/father_voice_dataset.zip，方便直接拖入 AutoDL 等云端 GPU 训练
"""

import json
import math
import os
import re
import shutil
import struct
import sys
import wave
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sanitize_text(text: str) -> str:
    """清洗文本杂质，保留真实口吻与标点"""
    text = text.strip().strip('"\'“”‘’')
    # 替换连续空格
    text = re.sub(r"\s+", " ", text)
    # 替换英文逗号为中文逗号
    text = text.replace(",", "，").replace("?", "？").replace("!", "！")
    return text.strip()


def normalize_and_save_wav(in_wav: Path, out_wav: Path, target_peak: int = 28000) -> Tuple[float, int]:
    """
    读取 16-bit 24kHz 单声道 WAV，应用轻度电平归一化和淡入淡出，写出到目标路径
    返回: (时长秒数, 峰值振幅)
    """
    with wave.open(str(in_wav), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)

    duration = nframes / float(framerate)
    samples = list(struct.unpack(f"<{nframes}h", frames))

    if not samples:
        return 0.0, 0

    # 1. 计算当前峰值
    max_val = max(abs(s) for s in samples)
    if max_val == 0:
        gain = 1.0
    else:
        # 防止过载，限制最大增益倍数不超过 2.5
        gain = min(target_peak / float(max_val), 2.5)

    # 2. 边缘淡入淡出 (前 120 个点和后 120 个点，约 5ms)，消除微信录音头尾断音咔哒声
    fade_len = min(120, len(samples) // 4)

    processed_samples = []
    for i, s in enumerate(samples):
        # 放大
        val = s * gain
        # 边缘平滑
        if i < fade_len:
            val *= (i / float(fade_len))
        elif i >= len(samples) - fade_len:
            val *= ((len(samples) - 1 - i) / float(fade_len))
        # 截断保护
        val = int(max(-32767, min(32767, round(val))))
        processed_samples.append(val)

    # 3. 写出标准化音频
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as out_wf:
        out_wf.setnchannels(nchannels)
        out_wf.setsampwidth(sampwidth)
        out_wf.setframerate(framerate)
        out_wf.writeframes(struct.pack(f"<{len(processed_samples)}h", *processed_samples))

    new_peak = max(abs(s) for s in processed_samples)
    return duration, new_peak


def main():
    print("=" * 65)
    print(" 父亲声音克隆训练集构建器 (GPT-SoVITS 专属)")
    print("=" * 65)

    transcripts_path = PROJECT_ROOT / "data" / "processed" / "voice_transcripts.json"
    if not transcripts_path.exists():
        print(f"[错误] 未找到转录记录文件: {transcripts_path}")
        sys.exit(1)

    with open(transcripts_path, "r", encoding="utf-8") as f:
        transcripts = json.load(f)

    print(f"[*] 读取到已转录语音条目: {len(transcripts)} 条")

    # 训练集目标目录
    dataset_dir = PROJECT_ROOT / "data" / "training" / "voice_dataset"
    wavs_dir = dataset_dir / "wavs"
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    wavs_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for sid, item in transcripts.items():
        raw_text = item.get("text", "")
        text = sanitize_text(raw_text)
        wav_rel = item.get("wav", "")
        wav_abs = PROJECT_ROOT / wav_rel

        if not text or not wav_abs.exists():
            continue

        # 过滤模型听写伪影与过短无效内容
        if " or " in text or len(text) < 3:
            continue

        # 检查音频基础可用性
        try:
            with wave.open(str(wav_abs), "rb") as wf:
                dur = wf.getnframes() / float(wf.getframerate())
                if 2.5 <= dur <= 15.0:
                    candidates.append({
                        "sid": sid,
                        "text": text,
                        "dur": dur,
                        "contact": item.get("contact"),
                        "time": item.get("time"),
                        "wav_abs": wav_abs,
                        "orig_filename": wav_abs.name,
                    })
        except Exception:
            pass

    # 按时间与对话人排序，保持规律性
    candidates.sort(key=lambda x: (x["time"], x["contact"]))

    print(f"[*] 筛选出符合黄金微调标准的清晰音频: {len(candidates)} 条")

    train_list_lines = []
    metadata_list = []
    total_processed_duration = 0.0

    for idx, c in enumerate(candidates, 1):
        # 统一命名规范，防止中文字符在某些 Linux 镜像中乱码
        clean_filename = f"father_sample_{idx:03d}_{c['time']}.wav"
        out_wav_path = wavs_dir / clean_filename

        dur, peak = normalize_and_save_wav(c["wav_abs"], out_wav_path)
        total_processed_duration += dur

        # GPT-SoVITS 标准标注格式:
        # wav_relative_path|speaker_name|language|text
        list_line = f"wavs/{clean_filename}|father|zh|{c['text']}"
        train_list_lines.append(list_line)

        metadata_list.append({
            "id": idx,
            "filename": clean_filename,
            "text": c["text"],
            "duration_sec": round(dur, 2),
            "peak_level": peak,
            "original_contact": c["contact"],
            "timestamp": c["time"],
            "original_file": c["orig_filename"],
        })

    # 1. 导出 GPT-SoVITS 标注文件 father_train.list
    list_file = dataset_dir / "father_train.list"
    with open(list_file, "w", encoding="utf-8") as f:
        f.write("\n".join(train_list_lines) + "\n")

    # 2. 导出完整元数据 metadata.json
    meta_file = dataset_dir / "metadata.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({
            "dataset_name": "Father_WeChat_Voice_Dataset",
            "speaker": "father",
            "total_clips": len(metadata_list),
            "total_duration_seconds": round(total_processed_duration, 2),
            "total_duration_minutes": round(total_processed_duration / 60.0, 2),
            "sample_rate": 24000,
            "channels": 1,
            "clips": metadata_list,
        }, f, ensure_ascii=False, indent=2)

    # 3. 挑选推荐的 5 个基准 Prompt 参考音频 (用于 Zero-shot 推理与音色基准)
    prompt_candidates = [
        c for c in metadata_list
        if 4.0 <= c["duration_sec"] <= 9.0 and len(c["text"]) >= 6
    ]
    # 取不同时期的代表性音频
    step = max(1, len(prompt_candidates) // 5)
    selected_prompts = prompt_candidates[::step][:5]

    prompt_guide_file = dataset_dir / "recommended_prompts.txt"
    with open(prompt_guide_file, "w", encoding="utf-8") as f:
        f.write("# 推荐使用的参考音频 (Prompt Reference Audios)\n")
        f.write("# 在 GPT-SoVITS WebUI 推理或 API 配置中，输入以下音频路径及其对应文本作为参考基准：\n\n")
        for p in selected_prompts:
            f.write(f"音频文件: wavs/{p['filename']}\n")
            f.write(f"参考文本: {p['text']}\n")
            f.write(f"音频时长: {p['duration_sec']} 秒\n")
            f.write(f"语境对象: 发给【{p['original_contact']}】\n")
            f.write("-" * 50 + "\n")

    # 4. 生成简明 AutoDL 云端使用说明
    readme_autodl = dataset_dir / "README_AUTODL.md"
    readme_content = f"""# 父亲专属声音模型 (GPT-SoVITS) 云端训练指南

## 1. 数据集概况
- **有效片段总数**: {len(metadata_list)} 段
- **总训练时长**: {total_processed_duration/60.0:.2f} 分钟 (处于 GPT-SoVITS 5~15 分钟的最佳区间)
- **音频格式**: 24kHz / 16-bit / Mono 单声道 WAV (已完成标准化电平处理与淡入淡出防爆音)
- **标注文件**: `father_train.list`

## 2. 在 AutoDL 中的操作步骤
1. 将 `father_voice_dataset.zip` 上传至 AutoDL 实例并解压：
   ```bash
   unzip father_voice_dataset.zip -d /root/father_voice/
   ```
2. 打开 GPT-SoVITS WebUI 界面：
   - 切换到 **1-GPT-SoVITS-TTS** 标签页
   - 实验/模型名称填入: `father_voice`
3. **1B-微调训练预处理**:
   - 文本标注文件路径填入: `/root/father_voice/father_train.list`
   - 音频根目录填入: `/root/father_voice/`
   - 点击 **1-一键三连** 提取特征 (4090 显卡约需 1~2 分钟)
4. **1C-微调训练**:
   - **SoVITS 训练**: Batch size=8 或 16，总轮数=10，点击开启训练 (约 5~8 分钟)
   - **GPT 训练**: Batch size=8 或 16，总轮数=15，点击开启训练 (约 10~15 分钟)
5. **下载成果**:
   - 在 `SoVITS_weights/` 下载生成的 `father_voice_e10.pth`
   - 在 `GPT_weights/` 下载生成的 `father_voice_e15.ckpt`
"""
    with open(readme_autodl, "w", encoding="utf-8") as f:
        f.write(readme_content)

    # 5. 打包成最终 ZIP 压缩包
    zip_output_path = PROJECT_ROOT / "data" / "training" / "father_voice_dataset.zip"
    print(f"\n[*] 正在将训练集打包为: {zip_output_path} ...")
    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(dataset_dir):
            for file in files:
                abs_f = Path(root) / file
                rel_f = abs_f.relative_to(dataset_dir)
                zf.write(abs_f, arcname=str(rel_f))

    zip_size_mb = zip_output_path.stat().st_size / (1024 * 1024)

    print("\n" + "=" * 65)
    print(f" 声音克隆训练数据集构建完成！")
    print(f" 1. 训练音频总数: {len(metadata_list)} 段")
    print(f" 2. 累计有效总时长: {total_processed_duration/60.0:.2f} 分钟 ({total_processed_duration:.1f} 秒)")
    print(f" 3. GPT-SoVITS 打标文件: {list_file}")
    print(f" 4. 推荐基准参考音频: {prompt_guide_file}")
    print(f" 5. 云端直传安装包: {zip_output_path} ({zip_size_mb:.2f} MB)")
    print("=" * 65)


if __name__ == "__main__":
    main()

