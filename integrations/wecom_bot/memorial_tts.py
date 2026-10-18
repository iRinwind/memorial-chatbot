#!/usr/bin/env python3
"""
纪念对象专属声音合成与绿色通信软件原生音频编码器 (Production Synthesizer & AMR-NB Encoder)
- 高保真 GPT-SoVITS 本地常驻 WebAPI (默认 127.0.0.1:9880)
- 语气词平滑与分句策略 (杜绝整句过长导致的 T2S 采样漂移)
- T2S 解码器终止符 (<EOS>) 防死循环与四级智能降级重试机制
- 广播级音频滤波：highpass 60Hz, lowpass 3400Hz
- opencore-amrnb 12.2kbps 原生语音格式封包 (无需微信转码，秒发秒播)
"""

import sys
import os
import io
import re
import json
import time
import wave
import ctypes
import subprocess
import urllib.request
from pathlib import Path

# 配置默认服务地址与参考音频（请在部署时根据实际路径调整或通过环境变量注入）
SOVITS_URL = os.environ.get("SOVITS_URL", "http://127.0.0.1:9880/tts")
REF_AUDIO = os.environ.get("REF_AUDIO", "data/processed/voice_reference/sample_ref.wav")
PROMPT_TEXT = os.environ.get("PROMPT_TEXT", "我马上到家了，你晚饭吃了没有？")

# opencore-amrnb 动态链接库路径 (macOS Homebrew 路径 / Linux 路径)
LIB_AMR_PATH = os.environ.get("LIB_AMR_PATH", "/opt/homebrew/lib/libopencore-amrnb.dylib")
if not os.path.exists(LIB_AMR_PATH):
    # Linux 常见路径
    if os.path.exists("/usr/lib/x86_64-linux-gnu/libopencore-amrnb.so.0"):
        LIB_AMR_PATH = "/usr/lib/x86_64-linux-gnu/libopencore-amrnb.so.0"
    elif os.path.exists("/usr/lib/libopencore-amrnb.so"):
        LIB_AMR_PATH = "/usr/lib/libopencore-amrnb.so"

try:
    lib = ctypes.CDLL(LIB_AMR_PATH)
    lib.Encoder_Interface_init.restype = ctypes.c_void_p
    lib.Encoder_Interface_init.argtypes = [ctypes.c_int]
    lib.Encoder_Interface_exit.argtypes = [ctypes.c_void_p]
    lib.Encoder_Interface_Encode.restype = ctypes.c_int
    lib.Encoder_Interface_Encode.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_short),
        ctypes.POINTER(ctypes.c_char),
        ctypes.c_int
    ]
    HAS_AMR_LIB = True
except Exception:
    HAS_AMR_LIB = False


def clean_text_for_tts(text: str) -> str:
    """清理文本中的特殊字符与多余表情，转换为最适宜长辈口语表达的短促呼吸停顿"""
    processed = text.strip()
    # 1. 过滤聊天软件自带的表情括号标签（如 [强], [OK], [合十]）
    processed = re.sub(r"\[[^\]]{1,8}\]", "", processed)
    # 2. 过滤 Unicode Emoji 图标与符号
    processed = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]", "", processed)
    # 3. 将文字中的连续空格转为逗号以保留呼吸停顿
    processed = re.sub(r"\s+", "，", processed.strip())
    # 4. 标点归一化：将内嵌问号、感叹号、分号转化为逗号，句尾以句号收束
    processed = re.sub(r"[？?！!；;…~～，,、：:。\.]+", "，", processed)
    processed = re.sub(r"，{2,}", "，", processed).strip("，")

    if not processed:
        return ""
    return processed + "。"


def add_modal_tail(cleaned_text: str) -> str:
    """句尾语气词柔化：当长辈说话语气较为生硬短促时，补充自然的收尾语气词（如'啊。'）辅助命中模型结束符"""
    core = cleaned_text.rstrip("。，")
    if not core:
        return cleaned_text
    if core[-1] not in "啊呀哦吧呢了的吗哈呐噢":
        return core + "啊。"
    return core + "。"


def get_wav_duration(wav_bytes: bytes) -> float:
    """基于 wave 模块解析音频二进制时长"""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return frames / float(rate) if rate > 0 else 0.0


def request_tts_wav(text: str, seed: int, top_k: int = 15, temperature: float = 0.6) -> bytes:
    """调用 GPT-SoVITS WebAPI 接口获取 WAV 音频字节流"""
    payload = {
        "text": text,
        "text_lang": "zh",
        "ref_audio_path": REF_AUDIO,
        "prompt_text": PROMPT_TEXT,
        "prompt_lang": "zh",
        "temperature": temperature,
        "top_k": top_k,
        "top_p": 1.0,
        "repetition_penalty": 1.35,  # 开启重复惩罚，从算法层杜绝尾音死循环
        "seed": seed,
        "text_split_method": "cut0",
        "speed_factor": 1.0,        # 锁定 1.0 以启用 GPT-SoVITS 原生并行分桶加速
        "fragment_interval": 0.12,
        "media_type": "wav"
    }
    req = urllib.request.Request(
        SOVITS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        if resp.status != 200:
            raise RuntimeError(f"TTS API failed: {resp.status}")
        return resp.read()


def synthesize_voice(text: str, out_amr_path: str = None) -> str:
    """
    带四级防死循环回退与物理时长熔断的高可用语音合成主流程
    """
    if not out_amr_path:
        out_amr_path = f"/tmp/memorial_voice_{int(time.time()*1000)}.amr"
    wav_path = f"/tmp/memorial_temp_{int(time.time()*1000)}.wav"

    processed = clean_text_for_tts(text)
    if not processed or processed in ("。", "，"):
        raise ValueError("输入文本经清洗后为空")

    pure_chars = re.sub(r"[，。]", "", processed)
    # 人类正常语速约为 3.5~4.5 字/秒 (0.22~0.28s/字)。超过阈值说明 T2S 未能正常生成 <EOS> 终止符
    max_valid_duration = max(6.0, len(pure_chars) * 0.42 + 2.0)

    processed_modal = add_modal_tail(processed)

    # 四级重试候选管线
    candidates = [
        (processed,       3540805864, 15, 0.60),  # 原始文本 + 默认稳定种子
        (processed_modal, 3540805864, 15, 0.60),  # 补充自然语气助词 + 默认稳定种子
        (processed_modal, 20260417,   20, 0.65),  # 扩宽采样候选集 + 备选种子
        (processed,       19591101,   20, 0.55),  # 降低温度增强确定性
    ]

    best_wav = None
    best_dur = 999.0

    for cand_text, seed, top_k, temp in candidates:
        try:
            wav_bytes = request_tts_wav(cand_text, seed=seed, top_k=top_k, temperature=temp)
            dur = get_wav_duration(wav_bytes)
            if 0.6 <= dur < best_dur:
                best_wav = wav_bytes
                best_dur = dur
            if 0.6 <= dur <= max_valid_duration:
                # 命中预期正常时长范围，跳出重试
                break
        except Exception as e:
            sys.stderr.write(f"[TTS 异常警告] 候选方案合成失败: {e}\n")

    if not best_wav:
        raise RuntimeError("所有候选方案均未生成有效音频")

    with open(wav_path, "wb") as f:
        f.write(best_wav)

    # 物理时长硬熔断 (-t max_valid_duration) + 广播级带通滤波 (60Hz~3400Hz 对应电话/人声标准频带)
    ffmpeg_bin = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
    cmd = [
        ffmpeg_bin, "-y", "-i", wav_path,
        "-t", f"{max_valid_duration:.2f}",
        "-af", "highpass=f=60,lowpass=f=3400",
        "-ar", "8000", "-ac", "1", "-f", "s16le", "-"
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    pcm_data = p.stdout

    # 调用 opencore-amrnb 库封装为原生 12.2kbps AMR-NB 语音文件
    if HAS_AMR_LIB:
        enc = lib.Encoder_Interface_init(0)
        try:
            with open(out_amr_path, "wb") as f:
                f.write(b"#!AMR\n")
                frame_size = 320
                out_buf = (ctypes.c_char * 32)()
                for i in range(0, len(pcm_data), frame_size):
                    chunk = pcm_data[i:i+frame_size]
                    if len(chunk) < frame_size:
                        chunk += b"\x00" * (frame_size - len(chunk))
                    short_array = (ctypes.c_short * 160).from_buffer_copy(chunk)
                    n = lib.Encoder_Interface_Encode(enc, 7, short_array, out_buf, 0)
                    f.write(bytes(out_buf[:n]))
        finally:
            lib.Encoder_Interface_exit(enc)
    else:
        # 若未找到 libopencore-amrnb 动态库，则使用 ffmpeg 作为兜底编码
        subprocess.run([
            ffmpeg_bin, "-y", "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", "-",
            "-c:a", "libopencore_amrnb", "-b:a", "12.2k", out_amr_path
        ], input=pcm_data, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(wav_path):
        os.remove(wav_path)

    return out_amr_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 memorial_tts.py <text> [out_amr_path]")
        sys.exit(1)
    if len(sys.argv) > 2 and sys.argv[-1].endswith(".amr"):
        t = " ".join(sys.argv[1:-1])
        o = sys.argv[-1]
    else:
        t = " ".join(sys.argv[1:])
        o = None
    res = synthesize_voice(t, o)
    print(res)
