"""
Memoria Core 配置文件
所有路径和 API 密钥从环境变量读取，无默认硬编码密钥。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"
PERSONAS_DIR = DATA_DIR / "personas"
PROMPTS_DIR = ROOT / "prompts"
USER_NICKNAME_FILE = DATA_DIR / "user_nickname.json"
DEFAULT_USER_NICKNAME = "用户"

# 自动加载 .env（如果存在）
env_path = ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# ---------- LLM ----------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")  # deepseek / kimi

# --- DeepSeek ---
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- Kimi (Moonshot) ---
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshot-v1-32k")

# ---------- Embedding ----------
# EMBEDDING_MODEL 为必填项：必须在 .env 中显式配置模型路径，缺失时启动即报错，
# 避免误用本机硬编码路径导致部署环境不一致。
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
if not EMBEDDING_MODEL:
    raise RuntimeError(
        "EMBEDDING_MODEL 未配置：请在项目根目录 .env 中设置 Embedding 模型路径，"
        "例如 EMBEDDING_MODEL=C:/path/to/bge-small-zh-v1.5"
    )
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "512"))  # bge-small-zh-v1.5 输出维度

# ---------- ChromaDB ----------
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "memoria_events")
CHROMA_SIMILARITY_TOP_K = int(os.getenv("CHROMA_SIMILARITY_TOP_K", "10"))

# ---------- 记忆 ----------
DEFAULT_DECAY_PER_DAY = float(os.getenv("DEFAULT_DECAY_PER_DAY", "0.02"))
MIN_IMPORTANCE_TO_KEEP = float(os.getenv("MIN_IMPORTANCE_TO_KEEP", "0.0"))

# ---------- 路径检查 ----------
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
