"""
数字人人格与对话风格引擎 (Persona Engine)
支持：
1. 原生 Google Gemini API (零外部依赖，直接基于 urllib)
2. OpenAI 兼容协议 (DeepSeek, GPT-4o, Qwen, Ollama 等)
3. 离线保护模式
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request


class PersonaEngine:
    """父亲人设对话引擎"""

    def __init__(self, config: Dict[str, Any], memory_manager: Any = None):
        self.config = config
        self.memory_manager = memory_manager
        self.llm_cfg = config.get("llm", {})

        template_path = Path(__file__).resolve().parent.parent.parent / "config" / "persona_template.md"
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                self.system_template = f.read()
        else:
            self.system_template = "你扮演我已故的长辈亲人，语言朴实、短促、充满关切与体贴。"

        self._init_client()

    def _init_client(self):
        """初始化客户端参数"""
        self.provider = self.llm_cfg.get("provider", "openai_compatible").lower()
        self.api_key = self.llm_cfg.get("api_key", "").strip()
        self.base_url = self.llm_cfg.get("base_url", "https://api.openai.com/v1").strip()
        self.model = self.llm_cfg.get("model", "gemini-1.5-flash").strip()

        # 环境变量回退
        if not self.api_key or "YOUR_API_KEY" in self.api_key:
            self.api_key = (
                os.environ.get("GEMINI_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or ""
            )

        # 自动探测 Gemini
        if self.api_key.startswith("AIzaSy") or "gemini" in self.provider:
            self.is_gemini = True
        else:
            self.is_gemini = False

        # 初始化 OpenAI SDK (若可用且非原生Gemini模式)
        self.openai_client = None
        if not self.is_gemini and self.api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except Exception:
                pass

    def build_system_prompt(self, user_query: str) -> str:
        """根据当前问题动态构建提示词"""
        retrieved_mem_str = ""
        historical_qa_str = ""
        profile_str = ""

        if self.memory_manager:
            context = self.memory_manager.retrieve_relevant_context(user_query, top_k_qa=4, top_k_mem=2)

            # 拼接画像与生活细节
            profile = context.get("profile", {})
            if profile:
                items = []
                if profile.get("hometown"):
                    items.append(f"- 家乡/籍贯: {profile['hometown']}")
                if profile.get("occupation"):
                    items.append(f"- 职业与过往工作: {profile['occupation']}")
                if profile.get("birthday_or_age") and profile.get("birthday_or_age") != "不详":
                    items.append(f"- 年龄与生日: {profile['birthday_or_age']}")
                if profile.get("hobbies"):
                    items.append(f"- 兴趣爱好: {', '.join(profile['hobbies'])}")
                if profile.get("favorite_foods"):
                    items.append(f"- 饮食偏好与喜爱的菜: {', '.join(profile['favorite_foods'])}")
                if profile.get("special_habits"):
                    items.append(f"- 生活习惯与作息: {', '.join(profile['special_habits'])}")
                if profile.get("care_topics"):
                    items.append(f"- 常挂念与常问及的事情: {', '.join(profile['care_topics'])}")
                if profile.get("common_nicknames", {}).get("user"):
                    items.append(f"- 对对话者的固定称呼: 直呼全名或专属昵称【{profile['common_nicknames']['user']}】（严禁使用客套生硬的'孩子/朋友'）")
                if profile.get("speaking_quirks"):
                    items.append(f"- 真实口癖与发音习惯: {'; '.join(profile['speaking_quirks'])}")
                if items:
                    profile_str = "### 纪念对象个人生活背景与细节 (由家人补充录入)：\n" + "\n".join(items)

            # 拼接相关情境记忆
            memories = context.get("memories", [])
            if memories:
                retrieved_mem_str = "### 唤起的相关过往生活记忆 (基于当前话题匹配)：\n" + "\n".join(
                    [f"- [{m.get('time_period', '')}] 《{m.get('title')}》: {m.get('content')}" for m in memories]
                )

            # 拼接真实历史对话范例 (Few-shot)
            qas = context.get("historical_qas", [])
            if qas:
                historical_qa_str = "### 历史真实绿色聊天记录参考 (严格模仿以下长短与语气，字数尽量在15字以内)：\n" + "\n".join(
                    [f"对方: {q.get('user')}\n亲友: {q.get('target') or q.get('father')}" for q in qas]
                )

        prompt = self.system_template
        prompt = prompt.replace("{{PROFILE_INFO}}", profile_str)
        prompt = prompt.replace("{{RETRIEVED_MEMORIES}}", retrieved_mem_str)
        prompt = prompt.replace("{{HISTORICAL_DIALOGUE_EXAMPLES}}", historical_qa_str)
        return prompt

    def generate_reply(
        self,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """生成回复"""
        if not self.api_key or "YOUR_API_KEY" in self.api_key:
            return "[提示] 大模型 API 尚未配置。请在 config/config.json 或环境变量中填入您的 API Key 即可激活真实对话。"

        system_prompt = self.build_system_prompt(user_message)

        # 1. 原生 Gemini API 调用分支 (零 SDK 依赖)
        if self.is_gemini:
            return self._call_gemini(system_prompt, user_message, chat_history)

        # 2. OpenAI 兼容协议分支
        return self._call_openai(system_prompt, user_message, chat_history)

    def _call_gemini(
        self,
        system_prompt: str,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """调用 Google Gemini 原生 REST API"""
        model = self.model if "gemini" in self.model else "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"

        contents = []
        if chat_history:
            for turn in chat_history[-6:]:
                role = "user" if turn.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})

        contents.append({"role": "user", "parts": [{"text": user_message}]})

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": float(self.llm_cfg.get("temperature", 0.7)),
                "maxOutputTokens": int(self.llm_cfg.get("max_tokens", 512)),
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_reply = parts[0].get("text", "").strip()
                            return self._post_process_reply(raw_reply)
            return "在外面慢点，注意身体。"
        except Exception as e:
            return f"[Gemini 连接提示: {e}] (请检查网络连接或 API Key 是否有效)"

    def _call_openai(
        self,
        system_prompt: str,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """调用 OpenAI / DeepSeek / Ollama 协议"""
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            for turn in chat_history[-6:]:
                messages.append(turn)
        messages.append({"role": "user", "content": user_message})

        if self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=float(self.llm_cfg.get("temperature", 0.7)),
                    max_tokens=int(self.llm_cfg.get("max_tokens", 512)),
                )
                raw_reply = response.choices[0].message.content.strip()
                return self._post_process_reply(raw_reply)
            except Exception as e:
                return f"[模型连接提示: {e}]"
        else:
            return "孩子，听到了。在外面注意身体，按时吃饭，别太累着自己。"

    def _post_process_reply(self, text: str) -> str:
        """后处理清理草稿标记、思考痕迹与AI腔调"""
        import re
        text = text.strip()
        # 清理常见的草稿/角色标记如 Draft 1*:, Draft 2:, 回复:, 父亲: 等
        text = re.sub(r'^(?:Draft\s*\d+\*?|草稿\s*\d*|回复|回答|父亲|爸爸)\s*[:：]\s*', '', text, flags=re.IGNORECASE)
        # 清理行末字数统计如 (15字) 或 (17
        text = re.sub(r'\s*[\(（]\s*\d+\s*(?:字|chars?)?[\)）]?\s*$', '', text)
        for prefix in ["父亲：", "爸爸：", "回答：", "回复：", "【父亲】"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = text.replace("！", "。")
        return text.strip()
