"""
系统配置加载模块
支持从 config/config.yaml 或 config/config.json 或环境变量读取配置
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_YAML_PATH = CONFIG_DIR / "config.yaml"
EXAMPLE_YAML_PATH = CONFIG_DIR / "config.example.yaml"
DEFAULT_JSON_PATH = CONFIG_DIR / "config.json"
EXAMPLE_JSON_PATH = CONFIG_DIR / "config.example.json"


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    加载配置文件。优先读取指定路径，否则按以下优先级寻找：
    1. config/config.yaml (若安装了 pyyaml)
    2. config/config.json
    3. config/config.example.json
    """
    if config_path:
        target = Path(config_path)
        return _load_file(target)

    # 自动探测
    # 如果存在 config.yaml 且能导入 yaml
    if DEFAULT_YAML_PATH.exists():
        try:
            return _load_file(DEFAULT_YAML_PATH)
        except Exception:
            pass

    if DEFAULT_JSON_PATH.exists():
        return _load_file(DEFAULT_JSON_PATH)

    if EXAMPLE_JSON_PATH.exists():
        return _load_file(EXAMPLE_JSON_PATH)

    if EXAMPLE_YAML_PATH.exists():
        return _load_file(EXAMPLE_YAML_PATH)

    raise FileNotFoundError("未找到任何可用的配置文件 (config.json 或 config.yaml)")


def _load_file(file_path: Path) -> Dict[str, Any]:
    suffix = file_path.suffix.lower()
    with open(file_path, "r", encoding="utf-8") as f:
        if suffix in [".yaml", ".yml"]:
            try:
                import yaml
                return yaml.safe_load(f)
            except ImportError:
                # 若无 yaml 库，尝试同名 json
                json_counterpart = file_path.with_suffix(".json")
                if json_counterpart.exists():
                    return _load_file(json_counterpart)
                raise ImportError("未安装 PyYAML 库，请使用 config.json 或执行 pip install pyyaml")
        else:
            return json.load(f)

