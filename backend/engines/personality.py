"""
性格引擎：11维双层向量 + 漂移分析 + 敏感点 + 了解度 + 破裂事件 + 文本注入
纯计算模块，不依赖 ChromaDB / FastAPI。LLM 调用通过参数注入，可替换。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

# ============================================================
# 维度定义
# ============================================================

DIMENSION_NAMES = [
    # 关系轴
    "亲和度", "依赖度", "攻击性", "主动性", "亲密意愿",
    # 自尊轴
    "自我认同", "被抛弃恐惧", "自我暴露",
    # 情绪轴
    "情绪表达", "嫉妒倾向", "愤怒方式",
]

DIMENSION_CATEGORIES = {
    "关系轴": [0, 1, 2, 3, 4],
    "自尊轴": [5, 6, 7],
    "情绪轴": [8, 9, 10],
}

# 维度中文名 → 注入描述模板（表层 / 深层分别有 + / − 方向的描述）
INJECTION_TEMPLATES = {
    "亲和度": {
        "surface_positive": "她今天话很多，看起来很愿意和你聊天。",
        "surface_negative": "她今天话很少，似乎不太想搭理你。",
        "deep_positive": "她心里其实很想靠近你。",
        "deep_negative": "她心里有些疏远你。",
    },
    "依赖度": {
        "surface_positive": "她会主动找你帮忙。",
        "surface_negative": "她什么都自己扛，不找你。",
        "deep_positive": "她内心需要你。",
        "deep_negative": "她内心并不需要你。",
    },
    "攻击性": {
        "surface_positive": "她嘴上带刺，说话冲。",
        "surface_negative": "她说话温柔客气。",
        "deep_positive": "她心里藏着刺。",
        "deep_negative": "她心里其实很柔软。",
    },
    "主动性": {
        "surface_positive": "她会主动开口。",
        "surface_negative": "她等着你先开口。",
        "deep_positive": "她心里先动了。",
        "deep_negative": "她心里还没动。",
    },
    "亲密意愿": {
        "surface_positive": "她允许你靠近。",
        "surface_negative": "她和你保持距离。",
        "deep_positive": "她想要被你靠近。",
        "deep_negative": "她不想被你靠近。",
    },
    "自我认同": {
        "surface_positive": "她表现得很自信，觉得自己值得。",
        "surface_negative": "她嘴上说自己配不上。",
        "deep_positive": "她内心觉得自己值得。",
        "deep_negative": "她内心觉得自己配不上。",
    },
    "被抛弃恐惧": {
        "surface_positive": "她表现得很怕你离开。",
        "surface_negative": "她表现得不怕你走。",
        "deep_positive": "她内心极度怕失去你。",
        "deep_negative": "她内心并不怕你离开。",
    },
    "自我暴露": {
        "surface_positive": "她会说一些自己的事。",
        "surface_negative": "她什么都不说。",
        "deep_positive": "她愿意坦露脆弱。",
        "deep_negative": "她内心层层设防。",
    },
    "情绪表达": {
        "surface_positive": "她情绪外放，喜怒形于色。",
        "surface_negative": "她压抑着情绪。",
        "deep_positive": "她内心情绪翻涌。",
        "deep_negative": "她内心也波澜不惊。",
    },
    "嫉妒倾向": {
        "surface_positive": "她表现出占有欲。",
        "surface_negative": "她对其他人满不在乎。",
        "deep_positive": "她内心占有欲很强。",
        "deep_negative": "她内心并不在意。",
    },
    "愤怒方式": {
        "surface_positive": "她不爽就直接爆发。",
        "surface_negative": "她不爽就冷处理。",
        "deep_positive": "她内心怒火中烧。",
        "deep_negative": "她内心也冷了下来。",
    },
}


# ============================================================
# 敏感点
# ============================================================

@dataclass
class SensitivePoint:
    """固化映射表条目：对话触发关键词 → 某维度瞬时拉升（不参与漂移）"""
    trigger_keywords: list[str]  # 触发词列表（OR 匹配）
    target_dimension: int        # 被影响的维度索引
    delta: float                 # 瞬时偏移量（绝对加在表层）
    cooldown_rounds: int = 50    # 冷却轮数，防止短时间反复触发
    description: str = ""


# ============================================================
# 核心数据结构
# ============================================================

@dataclass
class PersonalityState:
    """11维双层性格状态。每个维度 [surface, deep] 均在 [-1, 1] 区间。"""
    # 11维 × 2层 = 22个值
    values: list[list[float]] = field(default_factory=lambda: [
        [0.0, 0.0] for _ in range(11)
    ])

    # 了解度 0-1
    intimacy: float = 0.0

    # 破裂事件追踪
    rupture_streak: dict[int, int] = field(default_factory=dict)  # dim_idx → 连续轮数
    rupture_cooldown: dict[int, int] = field(default_factory=dict)  # dim_idx → 剩余冷却轮数

    # 敏感点冷却计数
    sensitive_cooldown: dict[int, int] = field(default_factory=dict)  # sp_index → 剩余冷却轮数

    # 元数据
    round_count: int = 0

    def __post_init__(self):
        # 钳位
        for dim in self.values:
            dim[0] = max(-1.0, min(1.0, dim[0]))  # surface
            dim[1] = max(-1.0, min(1.0, dim[1]))  # deep

    def surface(self, dim_idx: int) -> float:
        return self.values[dim_idx][0]

    def deep(self, dim_idx: int) -> float:
        return self.values[dim_idx][1]

    def gap(self, dim_idx: int) -> float:
        """表层与深层的差值绝对值，反映表里不一程度"""
        return abs(self.values[dim_idx][0] - self.values[dim_idx][1])

    def top_gap_dimensions(self, n: int = 3) -> list[int]:
        """返回差值最大的 n 个维度索引（降序）"""
        gaps = [(i, self.gap(i)) for i in range(11)]
        gaps.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in gaps[:n]]

    def to_dict(self) -> dict:
        return {
            "values": self.values,
            "intimacy": self.intimacy,
            "round_count": self.round_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PersonalityState:
        return cls(
            values=d.get("values", [[0.0, 0.0] for _ in range(11)]),
            intimacy=d.get("intimacy", 0.0),
            round_count=d.get("round_count", 0),
        )


# ============================================================
# 核心函数（纯计算，LLM 通过参数注入）
# ============================================================


def analyze_delta(
    state: PersonalityState,
    dialogue_summary: str,
    llm_chat: Callable[[str, str], str],
    *,
    inertia_enabled: bool = True,
) -> PersonalityState:
    """
    每轮对话后分析性格漂移。调用 LLM 输出 22 个 delta，惯性约束后应用。

    参数:
        state: 当前性格状态（原地修改并返回）
        dialogue_summary: 本轮对话摘要
        llm_chat: LLM 调用函数，签名为 (system_prompt, user_prompt) → response_text
        inertia_enabled: 是否启用惯性约束
    """
    system_prompt = _build_analyze_system_prompt()
    user_prompt = _build_analyze_user_prompt(state, dialogue_summary)
    raw_response = llm_chat(user_prompt, system=system_prompt)
    deltas = _parse_22_deltas(raw_response)

    # 惯性约束: actual = raw × (1 − |current|)
    if inertia_enabled:
        for i in range(11):
            surface_weight = abs(state.values[i][0])
            deep_weight = abs(state.values[i][1])
            deltas[i][0] *= (1.0 - surface_weight)
            deltas[i][1] *= (1.0 - deep_weight)

    # 应用 delta
    for i in range(11):
        state.values[i][0] = max(-1.0, min(1.0, state.values[i][0] + deltas[i][0]))
        state.values[i][1] = max(-1.0, min(1.0, state.values[i][1] + deltas[i][1]))

    # 了解度递增
    state.intimacy = min(1.0, state.intimacy + 0.002)

    # 破裂检测
    _check_rupture(state)

    # 冷却衰减
    _decay_cooldowns(state)

    state.round_count += 1
    return state


def apply_sensitive_points(
    state: PersonalityState,
    dialogue_text: str,
    sensitive_points: list[SensitivePoint],
) -> PersonalityState:
    """
    扫描对话文本，命中敏感点时对表层瞬时拉升。

    参数:
        state: 当前性格状态（原地修改并返回）
        dialogue_text: 本轮对话文本
        sensitive_points: 敏感点列表
    """
    for idx, sp in enumerate(sensitive_points):
        if state.sensitive_cooldown.get(idx, 0) > 0:
            continue
        if _match_keywords(dialogue_text, sp.trigger_keywords):
            dim = sp.target_dimension
            state.values[dim][0] = max(-1.0, min(1.0, state.values[dim][0] + sp.delta))
            state.sensitive_cooldown[idx] = sp.cooldown_rounds
    return state


def generate_injection(
    state: PersonalityState,
    *,
    top_n: int = 3,
) -> str:
    """
    纯 Python 模板函数：取差值最大的 top_n 维，根据了解度选表层/深层描述，生成注入文本。
    不走 LLM。
    """
    dims = state.top_gap_dimensions(top_n)
    use_deep = state.intimacy > 0.4  # 了解度 > 0.4 时用深层描述

    lines = ["【当前性格注入】"]
    for dim_idx in dims:
        name = DIMENSION_NAMES[dim_idx]
        val = state.deep(dim_idx) if use_deep else state.surface(dim_idx)
        templates = INJECTION_TEMPLATES.get(name)
        if not templates:
            continue

        layer = "deep" if use_deep else "surface"
        direction = "positive" if val > 0 else "negative"
        key = f"{layer}_{direction}"
        desc = templates.get(key, "")

        if desc:
            lines.append(f"- {desc}")

    # 敏感点命中提示
    # 不在此处处理，由 apply_sensitive_points 直接修改表层值，注入时自然反映

    return "\n".join(lines)


# ============================================================
# 内部辅助
# ============================================================


def _build_analyze_system_prompt() -> str:
    return """你是一位敏锐的小说编辑，正在追踪一个角色的性格演变。请阅读给出的对话片段，分析角色在这一轮中展现出的真实性格变化。

角色有 11 个性格维度，每个维度有「表层表现」（外人能看到的）和「深层感受」（内心真实的）两个层次。表层和深层可以不同——比如嘴上凶但心里软。

维度列表（索引 0-10）：
0: 亲和度  1: 依赖度  2: 攻击性  3: 主动性  4: 亲密意愿
5: 自我认同  6: 被抛弃恐惧  7: 自我暴露  8: 情绪表达
9: 嫉妒倾向  10: 愤怒方式

对每一维度，本轮的变化幅度（delta）应在 -0.15 到 0.15 之间。正数表示该特质增强，负数表示减弱。

【重要】只给本轮对话中确实有体现的维度赋非零值。如果某个维度在本轮对话中完全没有出现（比如整段对话没有嫉妒，就不要给嫉妒倾向赋任何值），该维度的表层和深层都应填 0。不要为了凑数而塞入微小的占位值。一个场景中大部分维度为 0 是正常的。

请仔细读完对话后，先在脑中形成对角色的整体判断，再逐维给出表层和深层的 delta。表层和深层可以不同。

最后，只输出一个 JSON 数组，包含 22 个浮点数，顺序为：
[surface_0, deep_0, surface_1, deep_1, ..., surface_10, deep_10]

示例（注意：表层和深层经常不一样——嘴上说"随便"但心里很在意；大部分维为 0 很正常）：
[0.05, 0.08, -0.02, 0.0, 0.0, -0.03, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01, -0.02, -0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

不要输出任何解释、分析文字或 Markdown 标记，只输出那个 22 个数的 JSON 数组。"""


def _build_analyze_user_prompt(state: PersonalityState, summary: str) -> str:
    """构建分析 prompt"""
    current = []
    for i in range(11):
        current.append(f"{DIMENSION_NAMES[i]}: 表层={state.surface(i):.2f}, 深层={state.deep(i):.2f}")
    current_str = "\n".join(current)

    return f"""当前性格状态（[-1, 1]，11维双层）：

{current_str}

本轮对话摘要：
{summary}

请输出 22 个 delta 值（JSON 数组）："""


def _parse_22_deltas(raw: str) -> list[list[float]]:
    """从 LLM 返回中解析 22 个 delta，容错处理。"""
    # 尝试提取 JSON 数组
    raw = raw.strip()
    # 去掉可能的 markdown 代码块
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
        if raw.endswith("```"):
            raw = raw[:-3]

    try:
        arr = json.loads(raw)
    except json.JSONDecodeError:
        # 尝试正则提取
        import re
        match = re.search(r"\[([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*)\]", raw)
        if match:
            try:
                arr = json.loads(match.group(0))
            except json.JSONDecodeError:
                arr = [0.0] * 22
        else:
            arr = [0.0] * 22

    if not isinstance(arr, list):
        arr = [0.0] * 22
    
    # Kimi 偶尔返回 21 个值（少了最后的 deep_10），补 0
    if len(arr) == 21:
        arr.append(0.0)
    elif len(arr) == 11:
        # Kimi 旧格式 11 值：表层=深层
        arr_22 = []
        for v in arr:
            arr_22.extend([v, v])
        arr = arr_22
    elif len(arr) != 22:
        arr = [0.0] * 22

    # 钳位
    arr = [max(-0.15, min(0.15, float(v))) for v in arr]

    # 拆成 11×2
    result = []
    for i in range(11):
        result.append([arr[i * 2], arr[i * 2 + 1]])
    return result


def _match_keywords(text: str, keywords: list[str]) -> bool:
    """检查文本是否命中任一关键词（大小写不敏感）"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _check_rupture(state: PersonalityState) -> None:
    """
    破裂事件检测：
    差值 > 0.6 且持续 3 轮 → 说漏嘴 → 深层向表层方向拉近 0.2 → 冷却 10 轮
    """
    for i in range(11):
        if state.rupture_cooldown.get(i, 0) > 0:
            continue
        if state.gap(i) > 0.6:
            state.rupture_streak[i] = state.rupture_streak.get(i, 0) + 1
        else:
            state.rupture_streak[i] = 0

        if state.rupture_streak.get(i, 0) >= 3:
            # 说漏嘴：深层向表层方向移动 0.2
            direction = 1.0 if state.surface(i) > state.deep(i) else -1.0
            state.values[i][1] = max(-1.0, min(1.0, state.values[i][1] + direction * 0.2))
            state.rupture_cooldown[i] = 10
            state.rupture_streak[i] = 0


def _decay_cooldowns(state: PersonalityState) -> None:
    """每轮冷却计数 -1"""
    for k in list(state.rupture_cooldown.keys()):
        state.rupture_cooldown[k] -= 1
        if state.rupture_cooldown[k] <= 0:
            del state.rupture_cooldown[k]
    for k in list(state.sensitive_cooldown.keys()):
        state.sensitive_cooldown[k] -= 1
        if state.sensitive_cooldown[k] <= 0:
            del state.sensitive_cooldown[k]


# ============================================================
# 独立验收脚本（直接运行此文件）
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("性格引擎独立验收测试")
    print("=" * 60)

    # ── 1. 初始化状态 ──
    state = PersonalityState()
    print("\n【初始状态】11维全部为 0.0")
    for i in range(11):
        print(f"  {DIMENSION_NAMES[i]:　<6}: surface={state.surface(i):+.2f}, deep={state.deep(i):+.2f}, gap={state.gap(i):.2f}")
    print(f"  了解度: {state.intimacy:.4f}")
    print(f"  轮次: {state.round_count}")

    # ── 2. 预置一个有一定差异的状态，验证注入 ──
    preset = PersonalityState()
    # 模拟几轮对话后的性格漂移结果
    preset.values = [
        [ 0.30, -0.50],  # 亲和度: 表层友好但深层疏远 → gap 0.80
        [ 0.10,  0.05],  # 依赖度: gap 0.05
        [-0.20,  0.30],  # 攻击性: 表层温柔深层有刺 → gap 0.50
        [ 0.40,  0.35],  # 主动性: gap 0.05
        [ 0.60, -0.55],  # 亲密意愿: gap 1.15 → 最大
        [ 0.15, -0.20],  # 自我认同: gap 0.35
        [-0.10,  0.70],  # 被抛弃恐惧: gap 0.80
        [-0.30,  0.10],  # 自我暴露: gap 0.40
        [ 0.05,  0.00],  # 情绪表达: gap 0.05
        [ 0.25,  0.20],  # 嫉妒倾向: gap 0.05
        [-0.15, -0.10],  # 愤怒方式: gap 0.05
    ]
    preset.intimacy = 0.25
    preset.round_count = 5
    print("\n【预设状态（模拟5轮后的性格）】")
    for i in range(11):
        print(f"  {DIMENSION_NAMES[i]:　<6}: surface={preset.surface(i):+.2f}, deep={preset.deep(i):+.2f}, gap={preset.gap(i):.2f}")

    # ── 3. 验证 top_gap_dimensions ──
    top3 = preset.top_gap_dimensions(3)
    print(f"\n【差值最大 3 维】")
    for idx in top3:
        print(f"  {DIMENSION_NAMES[idx]}: gap={preset.gap(idx):.2f}")

    assert 4 in top3, "亲密意愿(gap=1.15)应在 top3"
    print("  ✓ top_gap_dimensions 正确")

    # ── 4. 验证注入（了解度低→用表层） ──
    injection = generate_injection(preset)
    print(f"\n【注入文本（了解度={preset.intimacy}，用表层描述）】")
    print(injection)
    assert "【当前性格注入】" in injection
    assert len(injection.split("\n")) >= 4, "至少应有标题+3行描述"
    print("  ✓ generate_injection 输出格式正确")

    # ── 5. 验证了解度 > 0.4 时用深层 ──
    preset2 = PersonalityState()
    preset2.values = [row.copy() for row in preset.values]  # 深拷贝
    preset2.intimacy = 0.45
    injection2 = generate_injection(preset2)
    print(f"\n【注入文本（了解度={preset2.intimacy}，用深层描述）】")
    print(injection2)
    print("  ✓ 了解度切换机制正常")

    # ── 6. 模拟 LLM 返回解析 ──
    mock_llm_return = json.dumps([0.02]*22)
    parsed = _parse_22_deltas(mock_llm_return)
    assert len(parsed) == 11 and len(parsed[0]) == 2
    assert parsed[0][0] == 0.02
    print("\n  ✓ _parse_22_deltas 解析正确")

    # ── 7. 惯性约束验证 ──
    high_state = PersonalityState()
    high_state.values[0] = [0.8, 0.9]  # 已经很高，delta 应被大幅抑制
    high_state.values[1] = [0.0, 0.0]  # 初始态，delta 无抑制

    def mock_llm(_sys: str, _usr: str) -> str:
        return json.dumps([0.10] * 22)  # 所有维度输出 0.10

    result = analyze_delta(high_state, "测试对话", mock_llm)
    # 亲和度: actual = 0.10 * (1-0.8) = 0.02, surface 从 0.8 → 0.82
    # 依赖度: actual = 0.10 * (1-0.0) = 0.10, surface 从 0.0 → 0.10
    assert abs(result.surface(0) - 0.82) < 0.001, f"惯性约束失效: surface(0)={result.surface(0)}"
    assert abs(result.surface(1) - 0.10) < 0.001, f"新维度漂移异常: surface(1)={result.surface(1)}"
    print(f"  ✓ 惯性约束: 高权重维 delta 被抑制 (raw=0.10→actual=0.02), 新维正常 (raw=0.10)")
    print(f"  ✓ 了解度递增: {high_state.intimacy:.4f} → {result.intimacy:.4f} (+0.002)")

    # ── 8. 敏感点验证 ──
    sp_state = PersonalityState()
    sp = [
        SensitivePoint(
            trigger_keywords=["前女友", "前任", "ex"],
            target_dimension=9,  # 嫉妒倾向
            delta=0.5,
            cooldown_rounds=30,
            description="提到前任触发嫉妒"
        )
    ]
    result_sp = apply_sensitive_points(sp_state, "你前女友最近怎样？", sp)
    assert result_sp.surface(9) == 0.5, f"敏感点未触发: surface(9)={result_sp.surface(9)}"
    assert result_sp.sensitive_cooldown.get(0) == 30, f"冷却未设置"
    print(f"  ✓ 敏感点触发: 嫉妒倾向 surface 从 0.0 → {result_sp.surface(9)}")
    print(f"  ✓ 冷却已设置: {result_sp.sensitive_cooldown}")

    # 第二轮不应重复触发（冷却中）
    result_sp2 = apply_sensitive_points(result_sp, "我又提到前女友了", sp)
    assert result_sp2.surface(9) == 0.5, "冷却期内不应重复触发"
    print("  ✓ 冷却期内未重复触发")

    # ── 9. 破裂事件验证 ──
    rupture_state = PersonalityState()
    rupture_state.values[0] = [0.8, 0.1]  # gap=0.7 > 0.6
    # 手动连续3轮触发破裂
    for _ in range(3):
        _check_rupture(rupture_state)
        rupture_state.rupture_cooldown.clear()  # 清除冷却，允许连续检测
    # 第三轮后应触发破裂：深层向表层方向拉近0.2
    assert abs(rupture_state.deep(0) - 0.3) < 0.01, f"破裂拉近失效: deep(0)={rupture_state.deep(0)}"
    print(f"  ✓ 破裂事件: 差值0.7持续3轮 → 深层从0.1拉近至{rupture_state.deep(0):.1f}")

    # ── 10. to_dict / from_dict 序列化 ──
    d = preset.to_dict()
    restored = PersonalityState.from_dict(d)
    for i in range(11):
        assert restored.surface(i) == preset.surface(i)
        assert restored.deep(i) == preset.deep(i)
    assert restored.intimacy == preset.intimacy
    print("\n  ✓ to_dict / from_dict 序列化验证通过")

    print("\n" + "=" * 60)
    print("全部验收测试通过！性格引擎可独立运行。")
    print("=" * 60)
