"""测试包初始化：在导入 backend 之前做最小打桩。

- `dotenv` 可能没装（CI 只跑单测时），这里给它一个空实现；
- 把仓库根目录加入 sys.path，保证 `import backend` 可用。
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = _dotenv

import os  # noqa: E402

os.environ.setdefault("EMBEDDING_MODEL", "dummy-embedding-for-tests")
