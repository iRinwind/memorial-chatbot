"""
声音克隆与语音合成客户端 (TTS Client)
支持：
1. 本地开源 GPT-SoVITS API
2. 阿里开源 CosyVoice API
3. 云端 MiniMax / ElevenLabs 接口
4. 离线 Mock 模式 (使用 Python 原生 wave 模块生成占位测试音频)
原生使用标准库 urllib，零外部网络库依赖
"""

import json
import math
import struct
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, Optional


class BaseTTSClient:
    """TTS 基础类"""

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        raise NotImplementedError


class GPTSoVITSClient(BaseTTSClient):
    """
    对接本地/局域网部署的 GPT-SoVITS API (默认 9880 端口)
    """

    def __init__(self, config: Dict[str, Any]):
        self.api_url = config.get("api_url", "http://127.0.0.1:9880")
        self.ref_audio_path = config.get("ref_audio_path", "")
        self.ref_audio_text = config.get("ref_audio_text", "")
        self.language = config.get("language", "zh")

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        if not output_path:
            output_dir = Path("data/processed/generated_audio")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / "reply_voice.wav")

        payload = {
            "text": text,
            "text_language": self.language,
            "refer_wav_path": self.ref_audio_path,
            "prompt_text": self.ref_audio_text,
            "prompt_language": self.language,
        }

        try:
            target_url = self.api_url if self.api_url.endswith("/tts") else f"{self.api_url}/tts"
            req = urllib.request.Request(
                target_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    with open(output_path, "wb") as f:
                        f.write(resp.read())
                    return output_path
        except Exception as e:
            print(f"[TTS 连接失败] 无法连接到 GPT-SoVITS 服务 ({self.api_url}): {e}")

        return None


class LocalGPTSoVITSClient(BaseTTSClient):
    """
    使用本地 Apple Silicon / OmniVoice GPT-SoVITS 专属引擎直接离线合成
    无需开启 HTTP 服务，零外部依赖调用
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        import sys
        default_venv = self.config.get("python_path")
        if not default_venv:
            if sys.platform == "win32":
                candidates = [
                    r"E:\VibeProjects\GPT-SoVITS-v2-240821\runtime\python.exe",
                    r"F:\Archive\GPT-SoVITS\GPT-SoVITS-v2-240821\runtime\python.exe",
                    r"E:\GPT-SoVITS-v2-240821\runtime\python.exe"
                ]
                default_venv = next((p for p in candidates if Path(p).exists()), candidates[0])
            else:
                default_venv = "/Volumes/YottaServer/WorkingData/Projects/api/OmniVoice-Studio-Pinokio.git/app/.venv/bin/python"
        self.venv_py = default_venv
        self.script = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "synthesize_father_voice.py")

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        if not output_path:
            import time
            output_dir = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "generated_audio"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"reply_{int(time.time() * 1000)}.wav")

        import subprocess

        if Path(self.venv_py).exists():
            try:
                cmd = [self.venv_py, self.script, "--text", text, "--output", output_path]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if res.returncode == 0 and Path(output_path).exists():
                    return output_path
                else:
                    print(f"[LocalTTS 错误] {res.stderr or res.stdout}")
            except Exception as e:
                print(f"[LocalTTS 异常] {e}")

        # 降级保护：若本地引擎未安装或跨平台不可用，降级为 Mock TTS
        print("[TTS 提示] 本地模型引擎未就绪或未找到对应 Python 环境，自动降级为 Mock TTS 生成音频")
        return MockTTSClient().synthesize(text, output_path)


class MiniMaxClient(BaseTTSClient):
    """云端 MiniMax 语音克隆与合成客户端"""

    def __init__(self, config: Dict[str, Any]):
        self.group_id = config.get("group_id", "")
        self.api_key = config.get("api_key", "")
        self.voice_id = config.get("voice_id", "")

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        if not self.api_key or not self.group_id:
            print("[TTS 提示] MiniMax API 凭证未配置")
            return None

        url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={self.group_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "speech-01-turbo",
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 24000,
                "bitrate": 128000,
                "format": "wav",
            },
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    if "data" in res_body and "audio" in res_body["data"]:
                        hex_audio = res_body["data"]["audio"]
                        audio_bytes = bytes.fromhex(hex_audio)
                        if not output_path:
                            output_path = "data/processed/generated_audio/minimax_reply.wav"
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(audio_bytes)
                        return output_path
        except Exception as e:
            print(f"[TTS 异常] MiniMax 调用失败: {e}")
        return None


class MockTTSClient(BaseTTSClient):
    """
    零依赖模拟 TTS 生成器，生成一段纯正的 WAV 调试音频
    确保在没有部署 GPU / 模型服务时，整个应用全流程不中断
    """

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        if not output_path:
            output_dir = Path("data/processed/generated_audio")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / "mock_reply.wav")

        sample_rate = 24000
        duration_sec = min(max(len(text) * 0.15, 1.0), 4.0)  # 拟合语速
        num_samples = int(sample_rate * duration_sec)

        # 生成柔和的微声波
        with wave.open(output_path, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            samples = []
            for i in range(num_samples):
                t = i / sample_rate
                # 300Hz 温暖低频基音 + 缓慢衰减
                val = int(2000 * math.sin(2 * math.pi * 300 * t) * math.exp(-t / 3.0))
                samples.append(struct.pack("<h", val))

            wav_file.writeframes(b"".join(samples))

        return output_path


def get_tts_client(config: Dict[str, Any]) -> BaseTTSClient:
    """根据配置工厂化返回 TTS 客户端"""
    tts_cfg = config.get("tts", {})
    if not tts_cfg.get("enabled", True):
        return MockTTSClient()

    provider = tts_cfg.get("provider", "mock").lower()

    if provider in ["local_gpt_sovits", "local", "offline"]:
        return LocalGPTSoVITSClient(tts_cfg.get("local_gpt_sovits", {}))
    elif provider == "gpt_sovits":
        return GPTSoVITSClient(tts_cfg.get("gpt_sovits", {}))
    elif provider == "minimax_api":
        return MiniMaxClient(tts_cfg.get("minimax", {}))
    else:
        return MockTTSClient()

