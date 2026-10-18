"""
微信语音 SILK 格式转码器
微信语音采用 SILK v3 编码（文件头通常为 '#!SILK_V3' 或无头裸流）。
本模块支持：
1. 识别 SILK 头部特征
2. 若系统已安装 silk-v3-decoder / ffmpeg / pilk，直接转为 WAV
3. 若导出的音频已经是 wav/mp3/m4a/amr，则自动适配
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class SilkDecoder:
    """SILK 语音解码与转码器"""

    SILK_HEADER = b"#!SILK_V3"

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir) if output_dir else Path("data/processed/audio_clean")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._check_environment()

    def _check_environment(self):
        """检测系统中可用的音频转码工具"""
        self.has_ffmpeg = shutil.which("ffmpeg") is not None
        self.has_silk_decoder = shutil.which("silk_v3_decoder") is not None

    def is_silk_file(self, file_path: Path) -> bool:
        """根据文件头判断是否为 SILK 格式"""
        try:
            with open(file_path, "rb") as f:
                header = f.read(10)
                if self.SILK_HEADER in header:
                    return True
                # 部分微信版本去掉头部以 0x02 开头
                if len(header) > 0 and header[0] == 0x02:
                    return True
        except Exception:
            pass
        return False

    def convert_to_wav(self, input_file: str, target_sr: int = 24000) -> Optional[str]:
        """
        将微信语音文件（.silk / .aud / .amr / .mp3）转为标准 WAV 文件
        target_sr: 目标采样率 (默认 24000Hz，适配声音克隆模型)
        """
        src = Path(input_file)
        if not src.exists():
            return None

        out_wav = self.output_dir / f"{src.stem}.wav"
        if out_wav.exists():
            return str(out_wav)

        # 如果已经是 WAV 且不需要重采样
        if src.suffix.lower() == ".wav":
            return str(src)

        # 尝试通过 ffmpeg 转换普通音频格式
        if self.has_ffmpeg:
            try:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-ar",
                    str(target_sr),
                    "-ac",
                    "1",
                    str(out_wav),
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0 and out_wav.exists():
                    return str(out_wav)
            except Exception:
                pass

        # 尝试使用专用 silk_v3_decoder
        if self.has_silk_decoder:
            try:
                raw_pcm = self.output_dir / f"{src.stem}.pcm"
                subprocess.run(["silk_v3_decoder", str(src), str(raw_pcm)], check=True)
                if self.has_ffmpeg and raw_pcm.exists():
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-f",
                            "s16le",
                            "-ar",
                            "24000",
                            "-ac",
                            "1",
                            "-i",
                            str(raw_pcm),
                            str(out_wav),
                        ],
                        check=True,
                    )
                    raw_pcm.unlink(missing_ok=True)
                    return str(out_wav)
            except Exception as e:
                print(f"[警告] SILK 转码失败 {src.name}: {e}")

        # 若无法直接转码，打印指引
        print(f"[提示] 未能转码 {src.name}，建议安装 ffmpeg 或使用预转码好的音频。")
        return None

