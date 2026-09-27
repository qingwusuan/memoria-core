"""
LLM 客户端封装 — 支持 DeepSeek / Kimi 切换
根据 config.LLM_PROVIDER 自动路由，chat() 接口不变。
"""
from openai import OpenAI
from backend import config

import sys
import threading
import time as _time

_client = None
_provider_loaded: str | None = None  # 记录上次加载的 provider，切换时重建 client

# Kimi 账号 max organization concurrency=1：同一时刻只允许 1 个 LLM 请求，
# 并发会撞 429，用锁强制串行。为不让后台任务（事件提取/导入分析）占用锁期间
# 的重试 sleep 阻塞主对话，锁按用途拆分两把：
#   _main_lock       —— 主对话链路（主回复 + 主对话内性格分析）串行，顺序语义不变；
#   _background_lock —— 后台任务（事件提取、对话导入分析）串行，与主对话互不阻塞。
_main_lock = threading.Lock()
_background_lock = threading.Lock()
_main_waiters = 0
_background_waiters = 0
LOCK_TIMEOUT_SECONDS = 300.0  # 锁等待超时阈值：正常请求远小于此值，超时说明有请求长期占用


def _acquire_llm_lock(lock: threading.Lock, name: str) -> None:
    """获取 LLM 全局锁，带等待时长/队列长度/超时日志。获取失败抛 TimeoutError。"""
    global _main_waiters, _background_waiters
    if name == "main":
        _main_waiters += 1
    else:
        _background_waiters += 1
    try:
        queue_len = _main_waiters if name == "main" else _background_waiters
        if queue_len > 1:
            print(f"[deepseek] LLM {name} 锁排队中：当前等待线程数 {queue_len - 1}", file=sys.stderr, flush=True)
        wait_start = _time.monotonic()
        acquired = lock.acquire(timeout=LOCK_TIMEOUT_SECONDS)
        waited = _time.monotonic() - wait_start
        if not acquired:
            print(f"[deepseek] LLM {name} 锁等待超时（>{LOCK_TIMEOUT_SECONDS:.0f}s），放弃本次请求", file=sys.stderr, flush=True)
            raise TimeoutError(f"LLM {name} 锁等待超时（>{LOCK_TIMEOUT_SECONDS:.0f}s），可能有请求长期占用 LLM 通道")
        if waited >= 1.0:
            print(f"[deepseek] LLM {name} 锁获取成功，等待 {waited:.2f}s", file=sys.stderr, flush=True)
    finally:
        if name == "main":
            _main_waiters -= 1
        else:
            _background_waiters -= 1


def get_client() -> OpenAI:
    global _client, _provider_loaded
    provider = config.LLM_PROVIDER

    if _client is None or _provider_loaded != provider:
        if provider == "kimi":
            api_key = config.KIMI_API_KEY
            base_url = config.KIMI_BASE_URL
        else:  # deepseek (default)
            api_key = config.LLM_API_KEY
            base_url = config.LLM_BASE_URL

        _client = OpenAI(api_key=api_key, base_url=base_url)
        _provider_loaded = provider

    return _client


def chat(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 1000, background: bool = False) -> str:
    """发送对话请求，返回文本回复。模型根据当前 provider 自动选择。
    429 限流时自动退避重试（最多 3 次）。
    background=True 时走后台任务锁（事件提取等），与主对话锁互不阻塞。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    provider = config.LLM_PROVIDER
    model = config.KIMI_MODEL if provider == "kimi" else config.LLM_MODEL

    # kimi-k2.5 仅支持 temperature=1，强制覆盖
    if provider == "kimi":
        temperature = 1.0

    client = get_client()
    last_err = None
    lock = _background_lock if background else _main_lock
    lock_name = "background" if background else "main"
    _acquire_llm_lock(lock, lock_name)
    try:
        prompt_appended = False
        for attempt in range(5):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content
                # 空内容兜底：模型偶发返回空/空白（deepseek-flash 在低温+背靠背请求下频发），
                # 视为失败自动重试：提高温度 + 仅追加一次提示指令，最多共 5 次机会。
                if content is None or not content.strip():
                    last_err = ValueError("LLM 返回空内容")
                    _time.sleep(2.0 * (attempt + 1))
                    if not prompt_appended:
                        messages.append({"role": "user", "content": "（请继续，直接输出完整内容，不要输出空）"})
                        prompt_appended = True
                    temperature = 1.0 if provider == "kimi" else (1.0 if attempt >= 3 else 0.9)
                    continue
                return content
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    last_err = e
                    _time.sleep(2.5 * (attempt + 1))  # 2.5s / 5s / 7.5s 退避
                    continue
                raise
        raise last_err
    finally:
        lock.release()
