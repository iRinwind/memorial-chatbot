"""
针对重点联系人与群聊的高精度数据提取与清洗脚本
提取目标（示例，实际使用请根据自己导出的联系人列表修改）：
1. 核心联系人 (user_id_1)
2. 家人/好友 (user_id_2)
3. 家庭群聊 (chatroom_id_1)

产出：
- 结构化对话明细：data/processed/target_messages.json
- 提炼出的问答对：data/processed/qa_pairs.json
- 语言习惯统计：data/processed/style_stats.json
- 语音音频库：data/processed/voice_raw/ 和 data/processed/voice_wav/
- 更新记忆库：data/memory/qa_database.json
"""

import datetime
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from collections import Counter

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cleaner.dialogue_cleaner import DialogueCleaner
from modules.memory.memory_manager import MemoryManager

# 目标名单配置（示例：请填入您解密出的真实联系人 ID 或备注名）
TARGET_CONTACTS = {
    "wxid_user_example_01": {"name": "小明", "type": "single"},
    "wxid_user_example_02": {"name": "母亲", "type": "single"},
    "wxid_user_example_03": {"name": "姐姐", "type": "single"},
    "example_family@chatroom": {"name": "温馨一家人", "type": "group"},
}

# 尝试导入 pilk
try:
    import pilk
    HAS_PILK = True
except ImportError:
    HAS_PILK = False


def extract_all():
    print("=" * 60)
    print(" 父亲微信核心数据精准提取与构建流水线")
    print("=" * 60)

    # 1. 加载联系人昵称映射（用于群聊内部发言者识别）
    contact_db_path = PROJECT_ROOT / "decrypted" / "contact" / "contact.db"
    contact_map = {}
    if contact_db_path.exists():
        with sqlite3.connect(contact_db_path) as cconn:
            cur = cconn.cursor()
            cur.execute("SELECT username, remark, nick_name FROM contact;")
            for u, r, n in cur.fetchall():
                display_name = r.strip() if r and r.strip() else (n.strip() if n and n.strip() else u)
                contact_map[u] = display_name

    # 2. 扫描 message_*.db 提取各目标联系人的聊天记录
    db_files = sorted(glob.glob(str(PROJECT_ROOT / "decrypted" / "message" / "message_*.db")))
    all_extracted_messages = []
    # 记录父亲发送的语音消息索引: {server_id: msg_meta}
    father_voice_index = {}

    print(f"[*] 扫描到消息数据库 {len(db_files)} 个")

    for u_id, info in TARGET_CONTACTS.items():
        name = info["name"]
        is_group = (info["type"] == "group")
        md5_hash = hashlib.md5(u_id.encode("utf-8")).hexdigest()
        tbl_name = f"Msg_{md5_hash}"

        contact_msgs = []

        for db_file in db_files:
            try:
                conn = sqlite3.connect(db_file)
                cur = conn.cursor()
                # 检查该表是否存在
                cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tbl_name}';")
                if not cur.fetchone():
                    conn.close()
                    continue

                # 查询所有消息
                query = f"""
                    SELECT local_id, server_id, local_type, real_sender_id, 
                           create_time, status, message_content
                    FROM {tbl_name}
                    ORDER BY create_time ASC;
                """
                cur.execute(query)
                rows = cur.fetchall()

                for row in rows:
                    lid, sid, ltype, r_sender, ctime, status, content = row

                    # status == 2 表示我方（父亲）发送；status == 4 表示对方发送
                    is_father = (status == 2)

                    parsed_content = ""
                    sender_name = "父亲" if is_father else name

                    if ltype == 1:
                        # 文本消息
                        if isinstance(content, str):
                            raw_text = content.strip()
                        elif isinstance(content, bytes):
                            try:
                                raw_text = content.decode("utf-8", errors="ignore").strip()
                            except Exception:
                                raw_text = ""
                        else:
                            raw_text = ""

                        # 处理群聊前缀 (如 "wxid_xxx:\n消息内容")
                        if is_group and not is_father:
                            match = re.match(r"^([a-zA-Z0-9_\-]+):\n([\s\S]*)$", raw_text)
                            if match:
                                sender_uid = match.group(1)
                                sender_name = contact_map.get(sender_uid, name)
                                parsed_content = match.group(2).strip()
                            else:
                                parsed_content = raw_text
                        else:
                            parsed_content = raw_text

                    elif ltype == 34:
                        # 语音消息
                        parsed_content = "[语音消息]"
                        if is_father and sid:
                            father_voice_index[sid] = {
                                "contact": name,
                                "create_time": ctime,
                                "local_id": lid,
                                "server_id": sid,
                            }

                    elif ltype in [3, 47]:
                        parsed_content = "[图片表情]"
                    elif ltype in [43, 62]:
                        parsed_content = "[视频]"
                    else:
                        parsed_content = ""

                    # 规范化消息结构
                    msg_item = {
                        "msg_id": f"{u_id}_{lid}_{ctime}",
                        "server_id": str(sid),
                        "chat_target": name,
                        "chat_target_id": u_id,
                        "is_group": is_group,
                        "sender": sender_name,
                        "is_sender": is_father,  # True 表示父亲发送
                        "type": "text" if ltype == 1 else ("voice" if ltype == 34 else "other"),
                        "timestamp": ctime,
                        "time_str": datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else "",
                        "content": parsed_content,
                    }
                    contact_msgs.append(msg_item)

                conn.close()
            except Exception as e:
                print(f"[警告] 读取 {os.path.basename(db_file)} 中的 {name} 出错: {e}")

        # 排序
        contact_msgs.sort(key=lambda x: x["timestamp"])
        father_count = sum(1 for m in contact_msgs if m["is_sender"])
        print(f"[+] 提取完成 【{name}】：共 {len(contact_msgs)} 条消息（父亲发言 {father_count} 条）")
        all_extracted_messages.extend(contact_msgs)

    # 3. 提取父亲本人的语音消息
    print("\n[*] 正在从 media_0.db 提取父亲亲自发送的语音原音文件...")
    voice_raw_dir = PROJECT_ROOT / "data" / "processed" / "voice_raw"
    voice_wav_dir = PROJECT_ROOT / "data" / "processed" / "voice_wav"
    voice_raw_dir.mkdir(parents=True, exist_ok=True)
    voice_wav_dir.mkdir(parents=True, exist_ok=True)

    media_db_path = PROJECT_ROOT / "decrypted" / "message" / "media_0.db"
    extracted_voices = []

    if media_db_path.exists() and father_voice_index:
        with sqlite3.connect(media_db_path) as mconn:
            mcur = mconn.cursor()
            for sid, meta in father_voice_index.items():
                mcur.execute("SELECT voice_data FROM VoiceInfo WHERE svr_id = ?;", (sid,))
                row = mcur.fetchone()
                if row and row[0]:
                    vdata = row[0]
                    # 去掉前导 0x02 如果存在
                    if len(vdata) > 1 and vdata[0] == 2 and vdata[1:10] == b"#!SILK_V3":
                        silk_data = vdata[1:]
                    else:
                        silk_data = vdata

                    c_name = meta["contact"]
                    t_str = datetime.datetime.fromtimestamp(meta["create_time"]).strftime("%Y%m%d_%H%M%S")
                    silk_filename = f"{t_str}_{c_name}_{sid}.silk"
                    silk_path = voice_raw_dir / silk_filename

                    with open(silk_path, "wb") as f:
                        f.write(silk_data)

                    wav_path = voice_wav_dir / f"{t_str}_{c_name}_{sid}.wav"
                    # 转码为 WAV
                    if HAS_PILK:
                        try:
                            pilk.silk_to_wav(str(silk_path), str(wav_path), rate=24000)
                        except Exception:
                            pass

                    extracted_voices.append({
                        "server_id": str(sid),
                        "contact": c_name,
                        "time": t_str,
                        "silk_path": str(silk_path.relative_to(PROJECT_ROOT)),
                        "wav_path": str(wav_path.relative_to(PROJECT_ROOT)) if wav_path.exists() else None,
                        "size_bytes": len(silk_data),
                    })

    print(f"[+] 成功提取父亲发送的原始语音条数: {len(extracted_voices)} 条")
    if HAS_PILK:
        decoded_count = sum(1 for v in extracted_voices if v["wav_path"])
        print(f"[+] 成功解码为标准 WAV 语音条数: {decoded_count} 条")
    else:
        print("[提示] pilk 未安装或安装中，语音以 SILK 原始流保存在 data/processed/voice_raw/ 中。")

    # 4. 对话清洗与问答对提取 (Q&A Pairs)
    print("\n[*] 正在清洗对话并提炼高品质问答对 (家人/群友提问 -> 父亲回答)...")
    cleaner = DialogueCleaner(time_window_seconds=1800)  # 30分钟切分会话
    processed_result = cleaner.process_messages(all_extracted_messages, father_is_sender=True)

    # 5. 保存结果
    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 保存清洗后的完整消息
    with open(processed_dir / "target_messages.json", "w", encoding="utf-8") as f:
        json.dump(all_extracted_messages, f, ensure_ascii=False, indent=2)

    # 保存问答对
    with open(processed_dir / "qa_pairs.json", "w", encoding="utf-8") as f:
        json.dump(processed_result["qa_pairs"], f, ensure_ascii=False, indent=2)

    # 保存风格统计
    with open(processed_dir / "father_style_stats.json", "w", encoding="utf-8") as f:
        json.dump(processed_result["father_style_stats"], f, ensure_ascii=False, indent=2)

    # 保存语音元信息
    with open(processed_dir / "voice_manifest.json", "w", encoding="utf-8") as f:
        json.dump(extracted_voices, f, ensure_ascii=False, indent=2)

    # 6. 注入记忆库
    print("\n[*] 正在将高频对话与问答注入数字人记忆库...")
    mm = MemoryManager(str(PROJECT_ROOT / "data" / "memory"))
    mm.set_qa_database(processed_result["qa_pairs"])

    # 自动更新画像基础信息
    mm.update_profile({
        "name": "纪念对象 (张长生)",
        "relation_to_user": "长辈/亲友",
        "key_family_contacts": ["小明", "母亲", "姐姐"],
        "core_group": "温馨一家人",
    })

    print("\n" + "=" * 60)
    print(" 恭喜！核心数据提取与数字人记忆库构建全部完成！")
    print(f" - 提取有效总记录: {len(all_extracted_messages)} 条")
    print(f" - 提炼高纯度问答对: {len(processed_result['qa_pairs'])} 组")
    print(f" - 纪念对象专属语音原声: {len(extracted_voices)} 条")
    stats = processed_result.get("style_stats") or processed_result.get("father_style_stats", {})
    print(f" - 文字特征分析:")
    print(f"    * 累计分析发言: {stats.get('total_target_messages') or stats.get('total_father_messages', 0)} 条")
    print(f"    * 平均单条字数: {stats.get('average_length_chars', 0)} 字")
    print(f"    * 最常用短句: {stats.get('frequent_short_replies', [])[:5]}")
    print(f"    * 常用标点符号: {stats.get('punctuation_preferences', {})}")
    print("=" * 60)


if __name__ == "__main__":
    extract_all()

