"""pytest 全局配置：把仓库根目录加入 import 路径，并提供最小可用的环境变量。

只做测试所需的最小设置，不读取真实密钥。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EMBEDDING_MODEL", "dummy-embedding-for-tests")
