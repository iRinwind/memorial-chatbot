#!/bin/bash
# 启动 GPT-SoVITS 本地常驻 WebAPI 服务 (监听 127.0.0.1:9880)
# 模型常驻在 Mac mini 内存中，后续每次语音合成仅需 ~1.5 秒

export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

SOVITS_DIR="/Volumes/YottaServer/WorkingData/Projects/api/OmniVoice-Studio-Pinokio.git/app/TTS-Engines/GPT-SoVITS"
PYTHON_BIN="/Volumes/YottaServer/WorkingData/Projects/api/OmniVoice-Studio-Pinokio.git/app/.venv/bin/python"

cd "$SOVITS_DIR" || exit 1
echo "[*] 正在启动 GPT-SoVITS 常驻语音服务 (127.0.0.1:9880)..."
exec "$PYTHON_BIN" api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
