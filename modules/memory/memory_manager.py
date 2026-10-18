"""
家庭记忆管理与检索系统 (Memory Manager)
包含：
1. 静态人物画像 (Profile): 亲友称谓、生平简述、核心喜好
2. 历史情境记忆库 (Episodic Memories): 重要家庭事件、谈资经历
3. 动态召回器 (Retriever): 根据用户当前输入，匹配最相关的过往记忆与历史问答
4. 动态记忆沉淀 (Auto Consolidation): 在对话中识别并吸收新回忆
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request


class MemoryManager:
    """记忆与画像管理库"""

    def __init__(self, memory_dir: Optional[str] = None):
        self.memory_dir = Path(memory_dir) if memory_dir else Path("data/memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.profile_path = self.memory_dir / "profile.json"
        self.memories_path = self.memory_dir / "episodic_memories.json"
        self.qa_store_path = self.memory_dir / "qa_database.json"
        self.secondary_qa_path = self.memory_dir / "secondary_qa_database.json"

        self.profile: Dict[str, Any] = self._load_json(self.profile_path, default={
            "name": "纪念对象 (张长生)",
            "relation_to_user": "长辈与晚辈",
            "birthday_or_age": "不详",
            "hometown": "",
            "occupation": "",
            "hobbies": ["喝茶", "散步", "看新闻", "做饭"],
            "care_topics": ["工作压力", "身体健康", "一日三餐", "保暖", "出行安全"],
            "special_habits": [],
            "favorite_foods": [],
            "common_nicknames": {"user": "小明"},
            "key_family_contacts": ["小明", "母亲", "姐姐"],
            "core_group": "温馨一家人",
        })

        self.episodic_memories: List[Dict[str, Any]] = self._load_json(self.memories_path, default=[])
        self.qa_database: List[Dict[str, str]] = self._load_json(self.qa_store_path, default=[])
        self.secondary_qa_database: List[Dict[str, str]] = self._load_json(self.secondary_qa_path, default=[])

    def _load_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[警告] 加载 {path.name} 失败: {e}")
        return default

    def save_all(self):
        """保存记忆库所有数据"""
        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(self.profile, f, ensure_ascii=False, indent=2)
        with open(self.memories_path, "w", encoding="utf-8") as f:
            json.dump(self.episodic_memories, f, ensure_ascii=False, indent=2)
        with open(self.qa_store_path, "w", encoding="utf-8") as f:
            json.dump(self.qa_database, f, ensure_ascii=False, indent=2)

    def update_profile(self, new_data: Dict[str, Any]):
        """更新人物画像"""
        self.profile.update(new_data)
        self.save_all()

    def add_memory(self, title: str, content: str, time_period: str = "", tags: List[str] = None) -> Dict[str, Any]:
        """手动添加一条情境记忆"""
        max_id = max([m.get("id", 0) for m in self.episodic_memories], default=0)
        entry = {
            "id": max_id + 1,
            "title": title.strip(),
            "content": content.strip(),
            "time_period": time_period.strip(),
            "tags": [t.strip() for t in (tags or []) if t.strip()],
        }
        self.episodic_memories.append(entry)
        self.save_all()
        return entry

    def delete_memory(self, mem_id: int) -> bool:
        """删除一条情境记忆"""
        orig_len = len(self.episodic_memories)
        self.episodic_memories = [m for m in self.episodic_memories if m.get("id") != mem_id]
        if len(self.episodic_memories) < orig_len:
            self.save_all()
            return True
        return False

    def set_qa_database(self, qa_pairs: List[Dict[str, str]]):
        """设置历史问答对参考库"""
        self.qa_database = qa_pairs
        self.save_all()

    STOP_CHARS = set("，。？！、；：“”‘’（）《》 \t\n\r了的得地着过吗吧呢啊呀哦噢哈嗯我在是不是有和你他它她也但去就那这")

    def _compute_similarity(self, query: str, target: str) -> float:
        """过滤停用词后的字符 Jaccard 相似度"""
        if not query or not target:
            return 0.0
        q_chars = set(c for c in query.lower() if c not in self.STOP_CHARS)
        t_chars = set(c for c in target.lower() if c not in self.STOP_CHARS)
        if not q_chars or not t_chars:
            return 0.0
        intersection = q_chars.intersection(t_chars)
        if not intersection:
            return 0.0
        return len(intersection) / math.sqrt(len(q_chars) * len(t_chars))

    def retrieve_relevant_context(self, user_query: str, top_k_qa: int = 3, top_k_mem: int = 3) -> Dict[str, Any]:
        """
        根据用户输入，检索最相关的记忆和历史问答片段
        """
        # 1. 检索情境记忆
        scored_mems = []
        for mem in self.episodic_memories:
            text = f"{mem.get('title', '')} {mem.get('content', '')} {' '.join(mem.get('tags', []))}"
            score = self._compute_similarity(user_query, text)
            # 针对标签直接匹配给予高权重加成
            for tag in mem.get("tags", []):
                if tag and tag.lower() in user_query.lower():
                    score += 0.35
            # 针对标题关键词直接匹配给予加成
            title = mem.get("title", "")
            if title and any(len(part) >= 2 and part in user_query for part in title.split()):
                score += 0.25

            # 阈值：只有真正相关的话题才唤起记忆
            if score >= 0.16:
                scored_mems.append((score, mem))
        scored_mems.sort(key=lambda x: x[0], reverse=True)
        retrieved_mems = [m[1] for m in scored_mems[:top_k_mem]]

        # 2. 检索历史问答对 (核心家庭语料享有 1.3x 优先级加权，次要语料提供丰富生活与工作知识)
        scored_qas = []
        for qa in self.qa_database:
            u_text = qa.get("user", "")
            score = self._compute_similarity(user_query, u_text)
            if score > 0.15:
                scored_qas.append((score * 1.3, qa))
        for qa in self.secondary_qa_database:
            u_text = qa.get("user", "")
            score = self._compute_similarity(user_query, u_text)
            if score > 0.18:
                scored_qas.append((score, qa))
        scored_qas.sort(key=lambda x: x[0], reverse=True)
        retrieved_qas = [q[1] for q in scored_qas[:top_k_qa]]

        return {
            "profile": self.profile,
            "memories": retrieved_mems,
            "historical_qas": retrieved_qas,
        }

    def auto_consolidate_from_conversation(
        self, user_text: str, assistant_reply: str, api_key: str, model: str = "gemini-3.6-flash"
    ) -> Optional[Dict[str, Any]]:
        """
        在对话中检测用户是否讲述了一段新的过往家庭回忆/生活事实。
        如果是，自动提取并永久保存为一条新情境记忆，实现“动态想起来并铭记”！
        """
        # 快速前置规则过滤（只在可能包含回忆的问句/叙述时触发）
        memory_keywords = ["记得", "当年", "小时候", "那时候", "曾经", "以前", "老屋", "老家", "年轻时", "第一次", "那年"]
        if not any(k in user_text for k in memory_keywords):
            return None

        prompt = f"""
分析以下对话中，用户是否提到了关于纪念对象（长辈/亲友）的具体过往家庭回忆、生平经历或生活习惯细节：
用户说：“{user_text}”
长辈答：“{assistant_reply}”

如果用户在讲述一段真实、具体的家庭过往故事或回忆（例如“当年送考”、“某年买车”、“在老房子种树”），请提取为一条紧凑的情境记忆 JSON。
如果只是普通日常闲聊、问候、问现在的事，请仅回复空 JSON: {{}}。

提取格式（严格 JSON）：
{{
  "title": "简短记忆标题(8字内)",
  "content": "具体的记忆要点，保留核心细节",
  "time_period": "发生的大致年代或时期(如'2005年'或'小时候'，不知可留空)",
  "tags": ["标签1", "标签2"]
}}
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 512,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    cand = data.get("candidates", [])
                    if cand:
                        text = cand[0]["content"]["parts"][0]["text"].strip()
                        # 清理 markdown 标记 (如有)
                        if text.startswith("```"):
                            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                        parsed = json.loads(text)
                        if parsed.get("title") and parsed.get("content"):
                            cand_title = parsed["title"].strip()
                            cand_content = parsed["content"].strip()
                            # 查重：检查是否已有相同标题、相同内容或高度重合的记忆
                            for m in self.episodic_memories:
                                if m.get("title") == cand_title or m.get("content") == cand_content:
                                    return None
                                if self._compute_similarity(cand_content, m.get("content", "")) > 0.35:
                                    return None
                                if self._compute_similarity(cand_title, m.get("title", "")) > 0.6:
                                    return None
                            saved = self.add_memory(
                                title=parsed["title"],
                                content=parsed["content"],
                                time_period=parsed.get("time_period", ""),
                                tags=parsed.get("tags", []),
                            )
                            print(f"[+] 动态唤醒并沉淀新家庭记忆: 《{saved['title']}》 - {saved['content']}")
                            return saved
        except Exception as e:
            # 失败静默处理，不影响主聊天流
            pass
        return None
