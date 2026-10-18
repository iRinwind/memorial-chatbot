#!/usr/bin/env python3
"""
父亲专属声音本地离线合成脚本 (基于已安装的 OmniVoice/GPT-SoVITS 引擎)
"""

import argparse
import os
import sys
from pathlib import Path

# 设置关键 PyTorch 环境变量
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

print("[*] 正在启动语音合成脚本...", flush=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# GPT-SoVITS 路径 (Windows 优先检测本地或归档路径，Mac 降级远程路径)
if sys.platform == "win32":
    candidates = [
        r"E:\VibeProjects\GPT-SoVITS-v2-240821",
        r"F:\Archive\GPT-SoVITS\GPT-SoVITS-v2-240821",
        r"E:\GPT-SoVITS-v2-240821"
    ]
    BASE_SOVITS_DIR = next((p for p in candidates if os.path.exists(p)), candidates[0])
else:
    BASE_SOVITS_DIR = "/Volumes/YottaServer/WorkingData/Projects/api/OmniVoice-Studio-Pinokio.git/app/TTS-Engines/GPT-SoVITS"

sys.path.insert(0, BASE_SOVITS_DIR)
sys.path.insert(0, os.path.join(BASE_SOVITS_DIR, "GPT_SoVITS"))
sys.path.insert(0, os.path.join(BASE_SOVITS_DIR, "GPT_SoVITS", "eres2net"))
os.chdir(BASE_SOVITS_DIR)

print("[*] 正在加载 PyTorch 深度学习运行时 (硬盘读取中，请稍候约15-30秒)...", flush=True)
import numpy as np
import soundfile as sf
import torch
print(f"[+] PyTorch 加载成功 (版本: {torch.__version__})", flush=True)

print("[*] 正在加载 GPT-SoVITS 引擎模块...", flush=True)
from pypinyin import load_phrases_dict
from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
print("[+] 引擎模块加载就绪！", flush=True)

# 可选：注入方言/口音读音修正规则 (示例：针对特定专有名词的发音覆盖)
CUSTOM_PRONUNCIATION = {
    # "特定词": [["pin"], ["yin"]],
}
if CUSTOM_PRONUNCIATION:
    load_phrases_dict(CUSTOM_PRONUNCIATION)
    try:
        import text.g2pw.g2pw as g2pw_mod
        for k, v in CUSTOM_PRONUNCIATION.items():
            g2pw_mod.pp_dict[k] = [p[0] for p in v]
    except Exception:
        pass


PRESET_SAMPLES = {
    "010": ("father_sample_010_20201017_105201.wav", "啊你现在是早饭中午饭一起吃是。", "稳重日常"),
    "009": ("father_sample_009_20201012_204150.wav", "我马上到家了，你晚饭吃了没有？", "随和家常·亲切"),
    "002": ("father_sample_002_20200822_204011.wav", "二大爷又玩游戏啦，哈？开心的嘛。", "轻松打趣·带笑意"),
    "012": ("father_sample_012_20201114_104633.wav", "老婆，你在家里，也是依然还没起床是。", "慵懒随性·生活化"),
    "020": ("father_sample_020_20210425_100751.wav", "好，开始走了啊。开慢点，开慢点，好。", "关切温和·叮嘱"),
    "028": ("father_sample_028_20210514_180206.wav", "这个这个这个没什么好买的，我看。", "随性口语·家常"),
}


def synthesize(
    text: str,
    output_path: str = None,
    ref_audio_path: str = None,
    prompt_text: str = None,
    sample_key: str = "009",
    temperature: float = 0.7,
    top_k: int = 10,
    speed: float = 1.0,
    seed: int = 3540805864,
) -> str:
    if not output_path:
        out_dir = PROJECT_ROOT / "data" / "processed" / "generated_audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / "father_voice_reply.wav")

    # 根据预设样本或者自定义参考音频加载
    clean_wavs_dir = PROJECT_ROOT / "data" / "training" / "voice_dataset_clean" / "wavs"
    if not ref_audio_path:
        if sample_key in PRESET_SAMPLES and (clean_wavs_dir / PRESET_SAMPLES[sample_key][0]).exists():
            wav_name, p_text, desc = PRESET_SAMPLES[sample_key]
            ref_audio_path = str(clean_wavs_dir / wav_name)
            prompt_text = p_text
            print(f"[*] 选用基准音色预设 [{sample_key}]: {desc} (\"{p_text}\")")
        else:
            clean_sample_wav = clean_wavs_dir / "father_sample_010_20201017_105201.wav"
            if clean_sample_wav.exists():
                ref_audio_path = str(clean_sample_wav)
                prompt_text = "啊你现在是早饭中午饭一起吃是。"
            else:
                ref_audio_path = str(
                    PROJECT_ROOT / "data" / "training" / "voice_dataset" / "wavs" / "father_sample_030_20220607_103523.wav"
                )
                prompt_text = "好的好的好的，那你预约一下下午。"

    config_yaml = os.path.join(BASE_SOVITS_DIR, "GPT_SoVITS/configs/tts_infer.yaml")
    config = TTS_Config(config_yaml)
    
    # 动态检测最新训练的权重
    models_dir = PROJECT_ROOT / "data" / "models" / "weights"
    clean_gpt = list(models_dir.glob("father_voice_clean*.ckpt"))
    clean_sovits = list(models_dir.glob("father_voice_clean*.pth"))

    if clean_gpt and clean_sovits:
        config.t2s_weights_path = str(sorted(clean_gpt, key=os.path.getmtime)[-1])
        config.vits_weights_path = str(sorted(clean_sovits, key=os.path.getmtime)[-1])
    else:
        config.t2s_weights_path = str(models_dir / "father_voice-e15.ckpt")
        config.vits_weights_path = str(models_dir / "father_voice_e10_s110.pth")

    if torch.cuda.is_available():
        config.device = "cuda"
        config.is_half = True
    else:
        config.device = "cpu"
        config.is_half = False

    print(f"[*] 正在载入父亲声音模型 ({config.device}, half={config.is_half})...")
    tts_pipeline = TTS(config)

    # 1. 文本预处理：将结尾问号/感叹号转换为温和平静的陈述语气
    processed_text = text.strip()
    processed_text = processed_text.replace("？", "。").replace("?", "。")
    processed_text = processed_text.replace("！", "。").replace("!", "。")

    # 使用按标点切分或凑字切分，杜绝整句不切导致的早停截断
    split_method = "cut5"

    req = {
        "text": processed_text,
        "text_lang": "zh",
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": "zh",
        "text_split_method": split_method,
        "batch_size": 1,
        "split_bucket": True,
        "return_fragment": False,
        "fragment_interval": 0.22,
        "top_k": top_k,
        "top_p": 1.0,
        "temperature": temperature,
        "speed_factor": speed,
        "seed": seed,
    }

    print(f"[*] 原始输入: \"{text}\"")
    if processed_text != text:
        print(f"[*] 韵律平滑后输入: \"{processed_text}\"")
    print(f"[*] 语气调优参数: temperature={temperature}, top_k={top_k}, speed={speed}")
    print(f"[*] 正在合成语音...")
    gen = tts_pipeline.run(req)

    audio_chunks = []
    sample_rate = 32000

    for sr, chunk in gen:
        sample_rate = sr
        audio_chunks.append(chunk)

    if not audio_chunks:
        raise RuntimeError("合成失败，未生成有效音频数据")

    full_audio = np.concatenate(audio_chunks).astype(np.float32)

    # 全局整段温和主峰值平衡（拉升至 28000，约 -1.3dBFS），杜绝局部静音杂音
    c_max = np.max(np.abs(full_audio))
    if c_max > 500:
        full_audio = (full_audio / c_max) * 28000.0

    full_audio = full_audio.astype(np.int16)
    sf.write(output_path, full_audio, sample_rate)

    duration = len(full_audio) / float(sample_rate)
    print(f"[+] 语音合成成功！")
    print(f"    输出文件: {output_path}")
    print(f"    音频时长: {duration:.2f} 秒")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="本地纪念对象声音合成工具")
    parser.add_argument("--text", type=str, default="饭吃了没啊，今天工作忙不忙？", help="合成文本")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    parser.add_argument("--sample", type=str, default="009", choices=list(PRESET_SAMPLES.keys()), help="预设参考音频编号 (009随和家常, 002轻松带笑, 010稳重日常, 012慵懒随性, 020关切温和, 028极度口语)")
    parser.add_argument("--temperature", type=float, default=0.7, help="采样随机度 (默认0.7更灵动自然，0.5较工整平直)")
    parser.add_argument("--top_k", type=int, default=10, help="采样候选集大小 (默认10)")
    parser.add_argument("--speed", type=float, default=1.0, help="语速调节系数 (默认1.0)")
    parser.add_argument("--seed", type=int, default=3540805864, help="随机种子")
    parser.add_argument("--play", action="store_true", help="合成后通过 Mac 自带喇叭播放")
    args = parser.parse_args()

    out_file = synthesize(
        text=args.text,
        output_path=args.output,
        sample_key=args.sample,
        temperature=args.temperature,
        top_k=args.top_k,
        speed=args.speed,
        seed=args.seed,
    )

    if args.play:
        print("[*] 正在播放合成语音...")
        os.system(f"afplay '{out_file}'")


if __name__ == "__main__":
    main()

