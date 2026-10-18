#!/usr/bin/env python3
"""
次要数据源（非核心联系人与群聊）全量提取与清洗流水线
功能：
1. 扫描除核心9人外的全部 1,129 个聊天会话
2. 提取父亲发送的全部有效文本（过滤系统乱码与协议代码）与语音元数据
3. 提炼出社会化/通用问答对 (Secondary Q&A Pairs)，作为背景谈资知识库
4. 深度统计父亲的社会人际关系、职业工作特征、生活细节词频
5. 生成报告并注入 memory 数据库
"""

import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cleaner.dialogue_cleaner import DialogueCleaner

CORE_UIDS = {
    # 填入您已在核心提取中处理过的核心联系人 ID，避免次要提取重复收录
    "wxid_user_example_01", "wxid_user_example_02", "wxid_user_example_03",
    "example_family@chatroom"
}

def clean_text_content(content):
    """清洗微信文本消息，去除二进制协议碎片与系统无意义乱码"""
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    if not isinstance(content, str):
        return ""
    
    text = content.strip()
    if not text:
        return ""

    # 过滤明显的二进制协议头与乱码
    if text.startswith("(/") or "\x00" in text or "\\x" in text:
        # 如果包含中文正文，尝试提取出中文部分
        chinese_parts = re.findall(r'[\u4e00-\u9fa50-9a-zA-Z，。？！、\s\[\]]{2,}', text)
        if chinese_parts:
            text = " ".join([p.strip() for p in chinese_parts if len(p.strip()) > 1])
        else:
            return ""

    # 过滤链接、系统提示
    if text.startswith("http://") or text.startswith("https://"):
        return ""
    if "当前微信版本不支持展示该内容" in text:
        return ""
    if "收到红包，请在手机上查看" in text or "微信转账" in text:
        return ""
    if "<msg>" in text or "</msg>" in text:
        return ""

    return text.strip()


def run_secondary_pipeline():
    print("=" * 65)
    print(" 父亲微信次要数据源全量提取与画像挖掘流水线")
    print("=" * 65)

    # 1. 加载联系人信息
    contact_db = PROJECT_ROOT / "decrypted" / "contact" / "contact.db"
    contacts_map = {}
    if contact_db.exists():
        with sqlite3.connect(contact_db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT username, remark, nick_name FROM contact;")
            for u, r, n in cur.fetchall():
                disp = r.strip() if r and r.strip() else (n.strip() if n and n.strip() else u)
                md5_hash = hashlib.md5(u.encode("utf-8")).hexdigest()
                contacts_map[f"Msg_{md5_hash}"] = {
                    "username": u,
                    "name": disp,
                    "remark": r or "",
                    "nick_name": n or "",
                    "is_group": ("@chatroom" in u),
                }

    # 2. 扫描所有 message_[0-9].db
    db_files = sorted(glob.glob(str(PROJECT_ROOT / "decrypted" / "message" / "message_[0-9].db")))
    print(f"[*] 找到 {len(db_files)} 个分片消息数据库")

    # 存储提取出的次要消息
    secondary_messages = []
    secondary_voices = []
    contact_stats = defaultdict(lambda: {"total": 0, "father_text": 0, "father_voice": 0, "sample_texts": []})

    cleaner = DialogueCleaner(time_window_seconds=1200)

    for db_path in db_files:
        db_name = os.path.basename(db_path)
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';")
            tbl_names = [r[0] for r in cur.fetchall()]

            for tbl in tbl_names:
                c_info = contacts_map.get(tbl, {
                    "username": tbl,
                    "name": tbl,
                    "remark": "",
                    "nick_name": "",
                    "is_group": False
                })
                u_id = c_info["username"]

                # 排除系统号与核心9人（核心数据已在主管道）
                if u_id in CORE_UIDS:
                    continue
                if u_id.startswith("gh_") or u_id in ("fmessage", "medianote", "qmessage", "qqmail", "weixin", "floatbottle", "newsapp"):
                    continue

                try:
                    cur.execute(f"""
                        SELECT local_id, server_id, local_type, real_sender_id, create_time, status, message_content
                        FROM {tbl}
                        ORDER BY create_time ASC;
                    """)
                    rows = cur.fetchall()
                except Exception:
                    continue

                for row in rows:
                    lid, sid, ltype, r_sender, ctime, status, raw_content = row
                    is_father = (status == 2)
                    target_name = c_info["name"]

                    # 语音消息
                    if ltype == 34:
                        if is_father and sid:
                            secondary_voices.append({
                                "server_id": sid,
                                "contact": target_name,
                                "contact_id": u_id,
                                "create_time": ctime,
                                "db": db_name,
                            })
                            contact_stats[u_id]["father_voice"] += 1
                        continue

                    # 文本消息
                    if ltype == 1:
                        text = clean_text_content(raw_content)
                        if not text:
                            continue

                        contact_stats[u_id]["total"] += 1
                        if is_father:
                            contact_stats[u_id]["father_text"] += 1
                            if len(contact_stats[u_id]["sample_texts"]) < 10 and len(text) > 3:
                                contact_stats[u_id]["sample_texts"].append(text)

                        msg_item = {
                            "msg_id": f"{u_id}_{lid}_{ctime}",
                            "server_id": str(sid),
                            "chat_target": target_name,
                            "chat_target_id": u_id,
                            "type": "text",
                            "sender": "父亲" if is_father else target_name,
                            "is_sender": is_father,
                            "is_father": is_father,
                            "timestamp": ctime,
                            "create_time": ctime,
                            "content": text,
                            "is_group": c_info["is_group"],
                        }
                        secondary_messages.append(msg_item)

    print(f"[+] 次要数据源提取完成：")
    print(f"    - 有效文本消息总数: {len(secondary_messages)} 条")
    father_text_count = sum(1 for m in secondary_messages if m["is_father"])
    print(f"    - 父亲发送的有效文本: {father_text_count} 条")
    print(f"    - 父亲发送的语音总数: {len(secondary_voices)} 条")

    # 3. 按时间排序并切分提炼次要问答对 (Secondary Q&A Pairs)
    print("\n[*] 正在清洗并提炼次要问答对 (作为拓展知识与社交语料)...")
    secondary_messages.sort(key=lambda x: x["create_time"])

    # 按照联系人分别提取问答对
    msgs_by_contact = defaultdict(list)
    for m in secondary_messages:
        msgs_by_contact[m["chat_target_id"]].append(m)

    all_secondary_qas = []
    for cid, c_msgs in msgs_by_contact.items():
        res = cleaner.process_messages(c_msgs, father_is_sender=True)
        qas = res.get("qa_pairs", [])
        for q in qas:
            q["contact"] = c_msgs[0]["chat_target"]
        all_secondary_qas.extend(qas)

    print(f"[+] 成功提炼出次要问答对: {len(all_secondary_qas)} 组！")

    # 4. 保存清洗产物
    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    with open(processed_dir / "secondary_messages.json", "w", encoding="utf-8") as f:
        json.dump(secondary_messages, f, ensure_ascii=False, indent=2)

    with open(processed_dir / "secondary_qa_pairs.json", "w", encoding="utf-8") as f:
        json.dump(all_secondary_qas, f, ensure_ascii=False, indent=2)

    with open(processed_dir / "secondary_voice_manifest.json", "w", encoding="utf-8") as f:
        json.dump(secondary_voices, f, ensure_ascii=False, indent=2)

    # 5. 存储入 memory 数据库供检索参考
    memory_dir = PROJECT_ROOT / "data" / "memory"
    with open(memory_dir / "secondary_qa_database.json", "w", encoding="utf-8") as f:
        json.dump(all_secondary_qas, f, ensure_ascii=False, indent=2)

    # 6. 画像分析：对父亲的非核心发言进行关键词与主题聚类分析
    print("\n[*] 正在对次要数据源进行人物生平与职业画像特征挖掘...")
    father_all_words = []
    job_keywords = Counter()
    food_keywords = Counter()
    location_keywords = Counter()
    manner_keywords = Counter()

    # 规则词典
    JOB_PATTERNS = ["体育馆", "安保", "平面图", "档期", "彩排", "票", "艺人", "演唱会", "演出", "电镀", "加工", "模具", "工厂", "客户", "交货", "总机", "前台", "酒店"]
    FOOD_PATTERNS = ["梅干菜", "烧肉", "吃过", "早饭", "晚饭", "绿茶", "喝茶", "菜场", "豆腐", "鱼", "面", "酒", "水果", "苹果"]
    LOC_PATTERNS = ["上海", "沪太路", "九洲锦", "十院", "佳宁花园", "平型关路", "济南", "天津", "哈尔滨", "西安", "漠河", "北京"]
    MANNER_PATTERNS = ["谢谢", "客气", "辛苦", "麻烦", "不用客气", "收到", "早上好", "开心", "安康", "健康", "万事如意", "保重"]

    for m in secondary_messages:
        if m["is_father"]:
            txt = m["content"]
            for kw in JOB_PATTERNS:
                if kw in txt: job_keywords[kw] += 1
            for kw in FOOD_PATTERNS:
                if kw in txt: food_keywords[kw] += 1
            for kw in LOC_PATTERNS:
                if kw in txt: location_keywords[kw] += 1
            for kw in MANNER_PATTERNS:
                if kw in txt: manner_keywords[kw] += 1

    profile_discovery = {
        "work_and_career": {
            "summary": "大型演出/演唱会现场执行、体育馆场馆档期与安保对接负责人，亦有工厂生产加工与电镀业务人脉",
            "frequent_terms": dict(job_keywords.most_common(12)),
            "industry_title": "业内同行与后辈普遍尊称为【叶哥】",
            "specific_work_scenes": [
                "协调全国各城市体育馆（济南、天津、哈尔滨、西安等）档期、平面图、彩排安排与进场时间",
                "负责演出现场安保点位排布、安保拍照与现场秩序维护（工作群名：疲于奔命）",
                "对接知名巡演艺人与团队（如李宗盛演唱会、唱游团等），管理门票与工作餐饮",
                "出差频繁，常往返于上海与各地演出城市（如漠河、哈尔滨、济南等）"
            ]
        },
        "living_and_location": {
            "home_address": "上海市沪太路903弄佳宁花园24号702室",
            "medical_and_care": [
                "上海市第十人民医院 (十院，位于延长中路) - 一号楼11楼东区14床",
                "九洲锦护理院 (位于静安区平型关路) - 16楼10号床"
            ],
            "hometown_identity": "地道上海人，熟悉上海本地菜场、街道与生活气息"
        },
        "diet_and_taste": {
            "favorite_dishes": [
                "梅干菜烧肉 (特别钟爱农家自晒自制的地道梅干菜，觉得上海本地菜场买的味道不够地道)",
                "早饭喝茶、家常小菜、清淡饮食"
            ],
            "frequent_food_terms": dict(food_keywords.most_common(10))
        },
        "social_principles_and_manners": {
            "core_traits": [
                "【绝不占人便宜】：他人帮忙寄送土特产（如梅干菜），再三坚持必须转账付费，极讲规矩和礼数",
                "【重情重义长者风范】：每日清晨坚持向老朋友们互致诚挚问候（愿彼此安康、万事顺遂）",
                "【工作干脆果断】：现场执行指令清晰，极少废话（常用'收到'、'[OK]'、'安保拍照'、'平面图发我'）",
                "【体谅他人、隐忍坚强】：生病住院检查期间，主动让聚会朋友们玩得开心不用挂念，报平安总是温和从容"
            ],
            "frequent_manners": dict(manner_keywords.most_common(10))
        }
    }

    with open(processed_dir / "secondary_profile_discovery.json", "w", encoding="utf-8") as f:
        json.dump(profile_discovery, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 65)
    print(" 次要数据源挖掘流水线执行完毕！")
    print(f" 1. 产出结构化次要消息: data/processed/secondary_messages.json")
    print(f" 2. 提炼出通用问答对: data/processed/secondary_qa_pairs.json ({len(all_secondary_qas)} 组)")
    print(f" 3. 统计父亲次要语音清单: data/processed/secondary_voice_manifest.json ({len(secondary_voices)} 条)")
    print(f" 4. 沉淀出深度细节画像: data/processed/secondary_profile_discovery.json")
    print("=" * 65)

if __name__ == "__main__":
    run_secondary_pipeline()
