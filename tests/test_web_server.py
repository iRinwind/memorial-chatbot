"""
自动化端到端测试 Web UI 服务与 API 接口
"""

import json
import threading
import time
import urllib.request
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_ui.server import run_server


def test_server():
    # 启动后台服务
    thread = threading.Thread(target=run_server, kwargs={"port": 7869}, daemon=True)
    thread.start()
    time.sleep(1)

    base_url = "http://127.0.0.1:7869"

    # 1. 测试 HTML 页面获取
    with urllib.request.urlopen(f"{base_url}/") as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "绿色聊天软件" in html or "Memorial Bot" in html
        print("[PASS] Web 聊天页面加载成功")

    # 2. 测试 Profile API
    with urllib.request.urlopen(f"{base_url}/api/profile") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "profile" in data
        print("[PASS] Profile API 响应成功")

    # 3. 测试 Chat API
    chat_payload = json.dumps({"message": "爸，今天降温了", "need_voice": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=chat_payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "text" in data
        assert "audio_url" in data
        print(f"[PASS] Chat API 响应成功，回复: {data['text']}, 音频: {data['audio_url']}")

    print("\n[SUCCESS] 全部端到端自动化测试顺利通过！")


if __name__ == "__main__":
    test_server()

