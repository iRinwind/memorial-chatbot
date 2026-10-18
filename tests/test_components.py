"""
单元与组件功能测试 (无需网络 Socket 绑定)
"""

import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.config_loader import load_config
from modules.parser.wechat_db_parser import WeChatMsgParser
from modules.cleaner.dialogue_cleaner import DialogueCleaner
from modules.memory.memory_manager import MemoryManager
from modules.persona.persona_engine import PersonaEngine
from modules.voice.tts_client import MockTTSClient
from modules.bot.gateway import BotGateway


def test_components():
    print("[1] 测试配置加载器...")
    cfg = load_config()
    assert "project" in cfg
    assert "paths" in cfg
    print("    -> 配置加载通过")

    print("[2] 测试数据解析器...")
    sample_file = Path("data/raw/sample_chat.json")
    assert sample_file.exists()
    parser = WeChatMsgParser(str(sample_file))
    msgs = parser.parse()
    assert len(msgs) > 0
    print(f"    -> 解析到 {len(msgs)} 条测试消息")

    print("[3] 测试清洗器与问答提取...")
    cleaner = DialogueCleaner()
    res = cleaner.process_messages(msgs, father_is_sender=True)
    assert "qa_pairs" in res
    assert len(res["qa_pairs"]) > 0
    print(f"    -> 成功提炼 {len(res['qa_pairs'])} 组问答对，父亲发言平均字数: {res['father_style_stats']['average_length_chars']}")

    print("[4] 测试记忆管理与检索...")
    mm = MemoryManager()
    ctx = mm.retrieve_relevant_context("当年高考下暴雨")
    assert len(ctx["memories"]) > 0
    print(f"    -> 成功召回记忆: {[m['title'] for m in ctx['memories']]}")

    print("[5] 测试数字人提示词组装...")
    engine = PersonaEngine(cfg, memory_manager=mm)
    prompt = engine.build_system_prompt("爸，当年高考下暴雨你还记得吗？")
    assert "高考送考那天下大雨" in prompt
    print("    -> 提示词动态注入验证通过")

    print("[6] 测试声音合成 (Mock TTS)...")
    tts = MockTTSClient()
    audio_path = tts.synthesize("孩子，注意身体按时吃饭。")
    assert audio_path and os.path.exists(audio_path)
    print(f"    -> 成功合成测试音频: {audio_path}, 大小: {os.path.getsize(audio_path)} 字节")

    print("[7] 测试机器人调度中枢 (BotGateway)...")
    gw = BotGateway(cfg)
    resp = gw.handle_message("爸，今天下大雪，你冷不冷？", need_voice=True)
    assert "text" in resp
    assert resp["audio_path"] is not None
    assert os.path.exists(resp["audio_path"])
    print(f"    -> 网关应答测试通过: 回复='{resp['text']}', 语音文件='{resp['audio_path']}'")

    print("\n" + "=" * 50)
    print(" ALL UNIT & INTEGRATION TESTS PASSED! ")
    print("=" * 50)


if __name__ == "__main__":
    test_components()

