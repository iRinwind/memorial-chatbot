"""
消息调度与机器人网关 (Gateway)
统一接收消息、调用人设引擎与声音合成，并分发回前端或微信协议端
"""

from typing import Any, Dict, List, Optional
from modules.memory.memory_manager import MemoryManager
from modules.persona.persona_engine import PersonaEngine
from modules.voice.tts_client import get_tts_client, BaseTTSClient


class BotGateway:
    """机器人中枢控制器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.memory_manager = MemoryManager(config.get("paths", {}).get("memory_dir"))
        self.persona_engine = PersonaEngine(config, memory_manager=self.memory_manager)
        self.tts_client: BaseTTSClient = get_tts_client(config)

        self.chat_history: List[Dict[str, str]] = []

    def handle_message(
        self,
        user_text: str,
        need_voice: bool = True,
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        处理一条用户发来的消息
        返回：
        {
            "text": "回复文本",
            "audio_path": "生成的声音文件路径",
            "memory_triggered": [...]
        }
        """
        # 1. 检索激活的相关记忆条目 (供界面展示与溯源)
        context = self.memory_manager.retrieve_relevant_context(user_text)
        triggered_mems = [m.get("title") for m in context.get("memories", [])]

        # 2. 生成文字回复
        reply_text = self.persona_engine.generate_reply(
            user_message=user_text,
            chat_history=self.chat_history,
        )

        # 记录会话历史
        self.chat_history.append({"role": "user", "content": user_text})
        self.chat_history.append({"role": "assistant", "content": reply_text})

        # 3. 语音合成 (如果启用)
        audio_path = None
        if need_voice and self.config.get("tts", {}).get("enabled", True):
            try:
                audio_path = self.tts_client.synthesize(reply_text)
            except Exception as e:
                print(f"[网关语音异常] 合成失败: {e}")

        # 4. 动态记忆沉淀：检测孩子是否提到了过往家庭故事/生活细节，实时存入记忆库
        new_memory = None
        llm_cfg = self.config.get("llm", {})
        api_key = llm_cfg.get("api_key", "").strip()
        if api_key and "YOUR_API_KEY" not in api_key:
            try:
                new_memory = self.memory_manager.auto_consolidate_from_conversation(
                    user_text=user_text,
                    assistant_reply=reply_text,
                    api_key=api_key,
                    model=llm_cfg.get("model", "gemini-3.6-flash"),
                )
            except Exception as e:
                print(f"[记忆自动沉淀提示] {e}")

        return {
            "text": reply_text,
            "audio_path": audio_path,
            "triggered_memories": triggered_mems,
            "new_memory": new_memory,
        }

    def clear_history(self):
        """清空会话上下文"""
        self.chat_history.clear()

