"""
微信聊天记录解析器
支持多种微信备份来源：
1. 常见导出的 JSON/JSONL/CSV 文件 (来自各类微信备份工具如 PyWxDump, 留痕/WeChatMsg 等)
2. 解密后的 SQLite 数据库 (.db, .sqlite)
"""

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


class WeChatMsgParser:
    """微信聊天记录通用解析器"""

    def __init__(self, raw_data_path: str):
        self.raw_path = Path(raw_data_path)
        if not self.raw_path.exists():
            raise FileNotFoundError(f"未找到原始数据路径: {raw_data_path}")

    def parse(self) -> List[Dict[str, Any]]:
        """根据文件类型自动选择解析方式"""
        if self.raw_path.is_file():
            suffix = self.raw_path.suffix.lower()
            if suffix in [".json", ".jsonl"]:
                return self.parse_json(self.raw_path)
            elif suffix == ".csv":
                return self.parse_csv(self.raw_path)
            elif suffix in [".db", ".sqlite", ".sqlite3"]:
                return self.parse_sqlite(self.raw_path)
            else:
                raise ValueError(f"暂不支持的文件格式: {suffix}")
        elif self.raw_path.is_dir():
            return self.parse_directory(self.raw_path)
        return []

    def parse_json(self, file_path: Path) -> List[Dict[str, Any]]:
        """解析 JSON 或 JSONL 文件"""
        messages = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
            if content.startswith("[") and content.endswith("]"):
                # 标准 JSON 数组
                raw_list = json.loads(content)
                for item in raw_list:
                    normalized = self._normalize_msg(item)
                    if normalized:
                        messages.append(normalized)
            else:
                # 逐行 JSONL 格式
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        normalized = self._normalize_msg(item)
                        if normalized:
                            messages.append(normalized)
                    except json.JSONDecodeError:
                        continue
        return messages

    def parse_csv(self, file_path: Path) -> List[Dict[str, Any]]:
        """解析 CSV 聊天记录"""
        messages = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                normalized = self._normalize_msg(dict(row))
                if normalized:
                    messages.append(normalized)
        return messages

    def parse_sqlite(self, db_path: Path) -> List[Dict[str, Any]]:
        """解析解密后的微信 SQLite 数据库"""
        messages = []
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 探测主要数据表名 (如 MSG, message, Chat_xxx 等)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]

        target_table = None
        for candidate in ["MSG", "message", "chat_message", "Msg"]:
            if candidate in tables:
                target_table = candidate
                break

        if not target_table:
            # 查找以 Chat_ 开头的表
            chat_tables = [t for t in tables if t.startswith("Chat_")]
            if chat_tables:
                target_table = chat_tables[0]

        if not target_table:
            conn.close()
            raise ValueError(f"在数据库中未检测到标准微信消息表，现有表: {tables[:10]}")

        # 获取字段
        cursor.execute(f"PRAGMA table_info({target_table})")
        columns = [col[1] for col in cursor.fetchall()]

        cursor.execute(f"SELECT * FROM {target_table}")
        rows = cursor.fetchall()
        for row in rows:
            raw_dict = dict(zip(columns, row))
            normalized = self._normalize_msg(raw_dict)
            if normalized:
                messages.append(normalized)

        conn.close()
        return messages

    def parse_directory(self, dir_path: Path) -> List[Dict[str, Any]]:
        """扫描目录下所有支持的数据文件并合并"""
        all_messages = []
        for file in dir_path.glob("**/*"):
            if file.suffix.lower() in [".json", ".jsonl", ".csv", ".db", ".sqlite"]:
                try:
                    msgs = WeChatMsgParser(str(file)).parse()
                    all_messages.extend(msgs)
                except Exception as e:
                    print(f"[警告] 解析文件 {file.name} 失败: {e}")
        return all_messages

    def _normalize_msg(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        统一字段格式为标准消息对象：
        {
            "msg_id": str,
            "sender": str,
            "receiver": str,
            "is_sender": bool,  # 是否是聊天对象发出的
            "type": str,       # text, voice, image, video, system, other
            "timestamp": int/str,
            "content": str,
            "audio_path": str  # 若为语音消息，指向音频相对或绝对路径
        }
        """
        # 常见发送方判定字段映射
        is_sender = False
        for key in ["is_sender", "isSend", "IsSender", "issend"]:
            if key in raw:
                val = raw[key]
                is_sender = bool(val == 1 or val is True or str(val).lower() == "true")
                break

        # 消息类型
        msg_type = "text"
        type_val = raw.get("type") or raw.get("msgType") or raw.get("Type") or 1
        if isinstance(type_val, int):
            if type_val == 1:
                msg_type = "text"
            elif type_val == 34:
                msg_type = "voice"
            elif type_val in [3, 47]:
                msg_type = "image"
            elif type_val in [43, 62]:
                msg_type = "video"
            elif type_val in [10000, 10002]:
                msg_type = "system"
            else:
                msg_type = "other"
        else:
            str_type = str(type_val).lower()
            if "voice" in str_type or "语音" in str_type:
                msg_type = "voice"
            elif "image" in str_type or "图片" in str_type:
                msg_type = "image"
            elif "text" in str_type or "文本" in str_type:
                msg_type = "text"
            elif "sys" in str_type or "系统" in str_type:
                msg_type = "system"

        content = str(raw.get("content") or raw.get("strContent") or raw.get("msg") or raw.get("text") or "").strip()
        timestamp = raw.get("timestamp") or raw.get("createTime") or raw.get("CreateTime") or raw.get("time") or 0
        sender = str(raw.get("sender") or raw.get("talker") or raw.get("strTalker") or "")
        receiver = str(raw.get("receiver") or raw.get("to") or "")
        msg_id = str(raw.get("msg_id") or raw.get("localId") or raw.get("msgId") or raw.get("id") or "")
        audio_path = str(raw.get("audio_path") or raw.get("voicePath") or raw.get("path") or "")

        return {
            "msg_id": msg_id,
            "sender": sender,
            "receiver": receiver,
            "is_sender": is_sender,
            "type": msg_type,
            "timestamp": timestamp,
            "content": content,
            "audio_path": audio_path,
        }
