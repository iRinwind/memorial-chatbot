"""
微信对话清洗与结构化提取器
1. 清除系统消息、XML、卡片链接、转账、拍一拍等噪音
2. 按照时间窗口将会话切分为上下文 Session
3. 提取标准问答对 (家人消息 -> 父亲回复)，用于少样本提示与微调
4. 统计父亲的聊天习惯特征（平均字数、高频词、标点偏好）
"""

import re
from typing import Any, Dict, List, Tuple
from collections import Counter


class DialogueCleaner:
    """对话清洗与问答对提炼器"""

    # 常见系统与通知消息特征
    SYSTEM_PATTERNS = [
        r"^<.*?>",  # XML 消息
        r"\[微信转账\]",
        r"\[微信红包\]",
        r"收到红包，请在手机上查看",
        r"拍了拍我",
        r"邀请.*加入了群聊",
        r"加入了群聊",
        r"撤回了一条消息",
        r"通话时长",
        r"当前版本不支持展示该内容",
    ]

    def __init__(self, time_window_seconds: int = 1800):
        """
        time_window_seconds: 会话切分时间窗口 (默认 30 分钟)
        """
        self.time_window = time_window_seconds

    def clean_text(self, text: str) -> str:
        """清洗单条文本"""
        if not text:
            return ""

        # 检查是否命中系统噪音正则
        for pattern in self.SYSTEM_PATTERNS:
            if re.search(pattern, text):
                return ""

        # 清除常见的网页/卡片冗余标签
        cleaned = re.sub(r"<[^>]+>", "", text)
        cleaned = cleaned.strip()
        return cleaned

    def process_messages(
        self, messages: List[Dict[str, Any]], father_is_sender: bool = True
    ) -> Dict[str, Any]:
        """
        处理原始消息列表：
        - 过滤清洗
        - 分割 Session
        - 提取问答对
        - 生成风格统计
        """
        cleaned_msgs = []
        for msg in messages:
            if msg.get("type") == "text":
                c = self.clean_text(msg.get("content", ""))
                if c:
                    msg_copy = dict(msg)
                    msg_copy["content"] = c
                    cleaned_msgs.append(msg_copy)
            elif msg.get("type") == "voice":
                cleaned_msgs.append(dict(msg))

        # 按时间排序 (如果存在时间戳)
        try:
            cleaned_msgs.sort(key=lambda x: int(x.get("timestamp") or 0))
        except Exception:
            pass

        sessions = self._split_sessions(cleaned_msgs)
        qa_pairs = self._extract_qa_pairs(sessions, father_is_sender)
        stats = self._analyze_father_style(cleaned_msgs, father_is_sender)

        return {
            "total_messages": len(cleaned_msgs),
            "total_sessions": len(sessions),
            "qa_pairs": qa_pairs,
            "sessions": sessions,
            "father_style_stats": stats,
        }

    def _split_sessions(self, messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """按时间间隔切分会话"""
        if not messages:
            return []

        sessions = []
        current_session = [messages[0]]

        for i in range(1, len(messages)):
            prev = messages[i - 1]
            curr = messages[i]

            try:
                t_prev = int(prev.get("timestamp") or 0)
                t_curr = int(curr.get("timestamp") or 0)
                time_diff = abs(t_curr - t_prev)
            except Exception:
                time_diff = 0

            if time_diff > self.time_window:
                sessions.append(current_session)
                current_session = [curr]
            else:
                current_session.append(curr)

        if current_session:
            sessions.append(current_session)

        return sessions

    def _extract_qa_pairs(
        self, sessions: List[List[Dict[str, Any]]], father_is_sender: bool
    ) -> List[Dict[str, str]]:
        """提取标准的 (对方询问 -> 父亲回答) 问答对"""
        qa_pairs = []

        for session in sessions:
            i = 0
            while i < len(session):
                msg = session[i]
                # 如果是对方发来的消息
                if msg.get("is_sender") != father_is_sender:
                    user_texts = [msg.get("content", "")]
                    # 合并连续发送的消息
                    while i + 1 < len(session) and session[i + 1].get("is_sender") != father_is_sender:
                        i += 1
                        c = session[i].get("content", "")
                        if c:
                            user_texts.append(c)

                    # 寻找父亲紧随其后的回复
                    father_texts = []
                    while i + 1 < len(session) and session[i + 1].get("is_sender") == father_is_sender:
                        i += 1
                        c = session[i].get("content", "")
                        if c:
                            father_texts.append(c)

                    if user_texts and father_texts:
                        qa_pairs.append({
                            "user": " ".join([t for t in user_texts if t]),
                            "father": " ".join([t for t in father_texts if t]),
                            "timestamp": str(session[i].get("timestamp", "")),
                        })
                i += 1

        return qa_pairs

    def _analyze_father_style(
        self, messages: List[Dict[str, Any]], father_is_sender: bool
    ) -> Dict[str, Any]:
        """统计分析父亲的发言习惯"""
        father_texts = [
            m.get("content", "")
            for m in messages
            if m.get("is_sender") == father_is_sender and m.get("type") == "text"
        ]

        if not father_texts:
            return {"message_count": 0}

        lengths = [len(t) for t in father_texts]
        avg_len = sum(lengths) / len(lengths)

        # 统计常用标点
        punctuation_counts = Counter()
        for t in father_texts:
            for char in t:
                if char in "。，！？…~、.!?":
                    punctuation_counts[char] += 1

        # 统计高频字词 (简单基于字符切分)
        short_phrases = Counter(
            [t for t in father_texts if len(t) <= 6]
        ).most_common(10)

        return {
            "total_father_messages": len(father_texts),
            "average_length_chars": round(avg_len, 1),
            "frequent_short_replies": short_phrases,
            "punctuation_preferences": dict(punctuation_counts.most_common(5)),
        }

