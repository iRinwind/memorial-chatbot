#!/usr/bin/env python3
"""
手机端传入语音 (AMR) 实时转写器 (Inbound Voice Transcriber)
- 将手机端录制并接收到的 8kHz AMR 语音无损上采样重采样为 16kHz 单声道 WAV
- 接入 Whisper 离线模型，执行毫秒级中文语音转文字 (ASR)
- 零外部云端依赖，保护家庭隐私
"""

import sys
import os
import subprocess
import tempfile


def transcribe(audio_path: str) -> str:
    if not os.path.exists(audio_path):
        return ""

    ffmpeg_bin = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"

    # 创建临时的 16kHz WAV 音频文件供 Whisper 模型分析
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        temp_wav = tf.name

    try:
        subprocess.run([
            ffmpeg_bin, "-y", "-i", audio_path,
            "-ar", "16000", "-ac", "1", temp_wav
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        import whisper
        # 加载本地缓存的 'small' 或 'base' 中文语音识别模型
        download_root = os.environ.get("WHISPER_CACHE_DIR", os.path.expanduser("~/.cache/whisper"))
        model = whisper.load_model("small", download_root=download_root)
        result = model.transcribe(
            temp_wav,
            language="zh",
            initial_prompt="以下是普通话简体中文日常对话：",
            fp16=False
        )
        text = result.get("text", "").strip()
        return text
    except Exception as e:
        sys.stderr.write(f"[语音转写异常] {e}\n")
        return ""
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 transcribe_inbound_voice.py <in_audio_file>")
        sys.exit(1)

    audio_file = sys.argv[1]
    res = transcribe(audio_file)
    sys.stdout.write(res)
    sys.stdout.flush()
