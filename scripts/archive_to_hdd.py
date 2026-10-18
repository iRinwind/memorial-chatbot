#!/usr/bin/env python3
"""
训练产物提取与冗余数据归档脚本
功能：
1. 自动从 GPT-SoVITS 训练目录中检索最新的 father_voice_clean 权重文件 (.pth 和 .ckpt)
2. 提取并更新至本项目的 data/models/weights/ 目录
3. 将整个庞大的 GPT-SoVITS 整合包与训练缓存安全移动至 F 盘 (12TB HDD) 归档
4. 释放高速 SSD (E 盘) 的全部空间
"""

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HDD_ARCHIVE_ROOT = Path("F:/Archive/GPT-SoVITS")


def archive_and_clean(sovits_install_dir: Path):
    print("=" * 65)
    print(" GPT-SoVITS 模型提取与 HDD 归档助手")
    print("=" * 65)

    if not sovits_install_dir.exists():
        print(f"[错误] 未找到 GPT-SoVITS 目录: {sovits_install_dir}")
        return

    # 1. 查找权重 (兼容 v1 和 v2 权重目录)
    pth_files = sorted(list(sovits_install_dir.glob("SoVITS_weights*/father_voice_clean*.pth")), key=os.path.getmtime)
    ckpt_files = sorted(list(sovits_install_dir.glob("GPT_weights*/father_voice_clean*.ckpt")), key=os.path.getmtime)

    dest_models_dir = PROJECT_ROOT / "data" / "models" / "weights"
    dest_models_dir.mkdir(parents=True, exist_ok=True)

    if pth_files and ckpt_files:
        best_pth = pth_files[-1]
        best_ckpt = ckpt_files[-1]

        print(f"[*] 发现训练最新 SoVITS 声学权重: {best_pth.name}")
        shutil.copy2(best_pth, dest_models_dir / best_pth.name)

        print(f"[*] 发现训练最新 GPT 自回归权重: {best_ckpt.name}")
        shutil.copy2(best_ckpt, dest_models_dir / best_ckpt.name)

        print(f"[+] 核心权重已成功同步到项目: {dest_models_dir}")
    else:
        print("[!] 未在当前整合包中检索到 father_voice_clean 命名的权重，请确认是否已完成训练")
        return

    # 2. 迁移整合包至 F 盘
    print(f"\n[*] 正在将训练环境与冗余缓存迁移至 HDD (F 盘: {HDD_ARCHIVE_ROOT})...")
    HDD_ARCHIVE_ROOT.parent.mkdir(parents=True, exist_ok=True)

    target_dest = HDD_ARCHIVE_ROOT / sovits_install_dir.name
    if target_dest.exists():
        shutil.rmtree(target_dest)

    shutil.move(str(sovits_install_dir), str(target_dest))

    print(f"[+] 归档完成！整合包已移动至: {target_dest}")
    print(f"[+] E 盘高速 SSD 空间已全部释放！")


if __name__ == "__main__":
    default_dir = Path("E:/VibeProjects/GPT-SoVITS-v2-240821")
    if len(sys.argv) > 1:
        default_dir = Path(sys.argv[1])
    archive_and_clean(default_dir)
