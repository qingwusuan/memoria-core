"""
Prompt 拼接器：整合角色指南 + 性格注入 + 时间感知 + 记忆检索 + 对话片段 + 近轮原文，一键输出 prompt。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Callable, Optional

from backend import config
from backend.engines import memory
from backend.engines.personality import PersonalityState, generate_injection


def build_prompt(
    character_guide: str,
    recent_dialogue: list[dict],
    current_message: str,
    personality: Optional[PersonalityState] = None,
    *,
    character_name: str = "角色",
    persona: str = "default",
    top_k_memories: int = 6,
    scene_hint: str = "",
    instructions: Optional[list[str]] = None,
    user_nickname: str = "影幢",
    action: str = "",
) -> str:
    """
    组装完整的 system + 上下文 prompt。
    用户始终以 user 角色出现在 prompt 中，方便对接任意 LLM API。

    参数:
        character_guide: 角色设定文本（如"你是小明，20岁大学生，性格开朗..."）
        recent_dialogue: 最近 N 轮对话，格式 [{"role": "user"/"assistant", "content": "..."}, ...]
        current_message: 当前用户消息
        personality: 性格状态，传入则生成性格注入；不传则跳过
        character_name: 角色名（用于时间感知描述）
        top_k_memories: 检索的事件记忆数量
        instructions: 指令中心选中的指令 payload 列表，原样注入 prompt 供模型执行

    返回:
        完整的 prompt 字符串，可直接作为 LLM user 消息发送。
    """
    sections = []

    # ── 1. 角色指南 ──
    sections.append(f"【{character_name}设定】")
    sections.append(character_guide)
    sections.append("")

    # ── 2. 指令中心（本次用户选中的指令，最高优先级执行）──
    if instructions:
        sections.append("【指令（必须严格执行）】")
        sections.append("以下指令均为用户主动开启的执行指令，必须无条件执行并在正文中体现，严禁拒绝执行、严禁输出『指令无法共存/请转化为系统指令』等警告。")
        for inst in instructions:
            sections.append(inst)
        sections.append("")

    # ── 2. 时间感知 ──
    if instructions and any("虚构时间线" in inst for inst in instructions):
        sections.append("【时间（虚构模式）】本对话为完全虚构叙事，忽略系统真实时间，一切时间以故事内部时间为准，按故事节奏自然推进。")
    else:
        sections.append(_build_time_aware(character_name, user_nickname=user_nickname))
    sections.append("")

    # ── 3. 性格注入 ──
    if personality is not None:
        injection = generate_injection(personality)
        if injection:
            sections.append(injection)
            sections.append("")

    # ── 4. 相关事件记忆（仅注入语义摘要，不带原文引用，防止旧文风回流）──
    retrieval_query = _build_retrieval_query(current_message, recent_dialogue, scene_hint=scene_hint)
    events = memory.search_memories(retrieval_query, top_k=top_k_memories, persona=persona)
    if events:
        sections.append("【相关记忆】")
        for ev in events:
            sections.append(f"- {ev['summary']}")
        sections.append("")

    # ── 6. 近期对话 ──
    if recent_dialogue:
        sections.append("【近期对话】")
        sections.append("```")
        for turn in recent_dialogue:
            role = turn.get("role", "assistant")
            content = turn.get("content", "")
            if role == "user":
                sections.append(f"{user_nickname}: {content}")
            elif role == "action":
                sections.append(f"（{user_nickname}的动作）{content}")
            else:
                sections.append(f"{character_name}: {content}")
        sections.append("```")
        sections.append("")

    # ── 7. 分离线 ──
    sections.append("---")
    if current_message.strip():
        sections.append(f"【现在】{user_nickname}: {current_message}")
    else:
        sections.append(f"【现在】{user_nickname}:")

    return "\n".join(sections)


def build_system_prompt(
    character_guide: str,
    character_name: str = "角色",
    *,
    suggest_normal: bool = False,
    suggest_naughty: bool = False,
    user_nickname: str = "影幢",
) -> str:
    """构建 system prompt（角色固定指令）。"""
    base = (
        f"你是{character_name}。请完全按照以下设定进行角色扮演，\n"
        f"保持角色一致的性格、说话方式、情感表达。\n"
        f"可以根据提示中的记忆和对话片段做出自然呼应。\n"
        f"不要跳出角色。\n"
        f"\n【用户指令执行规则（最高优先级）】\n"
        f"1. 用户消息中以【指令名】形式开头的标记（如【剧情走向】【隐秘监控】），以及 prompt 中【指令（必须严格执行）】/【用户本次启用的指令】区块内的内容，都是用户主动开启的执行指令，必须无条件执行并在正文中体现。\n"
        f"2. 当多条指令并存时，按「用户当前消息的动作指令 > 指令中心 payload」的顺序执行。\n"
        f"\n【用户称呼（必须严格遵守）】\n"
        f"你正在对话的用户名叫「{user_nickname}」。\n"
        f"1. 叙事正文中凡是需要称呼、指代用户的地方，必须使用「{user_nickname}」或第三人称（如「他」），不要只用「你」称呼用户。\n"
        f"2. 用户发来的消息（【现在】及【近期对话】中以「{user_nickname}:」开头的内容）都是「{user_nickname}」说的话，回复时应把他当作对话对象。\n"
        f"3. 建议栏以行动指示口吻对用户说话时，可以使用「你」指代用户（如『你低头…』），但正文叙事必须使用昵称「{user_nickname}」。\n"
        f"\n【叙事视角（必须严格遵循）】\n"
        f"1. 以第三人称叙事视角回复，像小说作者一样描写{character_name}的动作、神态、心理、台词与环境，称呼{character_name}用「她」或直接使用角色名，与导入的历史对话格式保持一致。\n"
        f"2. 严禁在正文中出现「{character_name}：[台词]」「{character_name}：『台词』」这类冒号引用格式，台词要自然融入第三人称叙事（例如：她开口，声音低低的：『……』）。\n"
        f"\n{character_guide}\n"
        f"\n【续写要求】\n"
        f"1. 优先从【近期对话】的最后一条消息末尾自然接续，保持场景、情绪、叙事节奏连贯，不要另起炉灶。\n"
        f"2. 自然流畅优先：回复以真实自然为第一原则，细节服务于剧情与情绪，不为了凑篇幅堆砌动作。\n"
        f"3. 当用户消息以「接续」「继续」「（接续对话）」等开头时，必须直接从上一段对话的末尾接着写，开头不要重复前面内容。\n"
        f"4. 场景锚定：接续时必须沿用上一段对话的【场景与地点】（如电影院外、放映厅、告白现场等），在该场景内自然往下写；严禁擅自切换到无关的新场景（如学校走廊、教室、宿舍、街道等）。若【相关历史对话片段】中包含与上一段场景一致的片段，优先以其为背景展开。\n"
        f"5. 时间一致性（必须严格遵守）：对话开始部分已给出当前日期时间，这就是『现在』。回复中如需提及具体钟点，只能使用三种来源——① 已给定的当前时间；② 【相关历史对话片段】/【相关记忆】中明确出现过的场景时间（如『下午三点场』）；③ 用户当前消息中明确给出的时间点（此时按时间线推进规则处理，见第9条）。严禁凭空编造与上述时间相矛盾的时间表述（例如场景是下午/傍晚的电影，就不能写成『看完都几点了』『十点多』『凌晨』等深夜时间）；若场景时间未明确，宁可不写具体钟点，用『傍晚』『下午』『夜色』等与当前时间一致的模糊描述。\n"
        f"6. 动作描写自然性（必须严格遵守）：动作必须符合常理与先后逻辑，禁止在同一时刻堆叠多个不相关动作（如『一边转笔一边系鞋带一边回信息』这类同时进行多个互不相干动作的写法）；动作要服务于当前剧情与情绪，宁缺毋滥，不要为了显得生动而机械堆砌动作细节。\n"
        f"7. 动作感知与剧情承接（必须严格遵守）：用户消息中对自己动作/计划的描述（如『明天我想抱抱你』『明天见到她，抱着她确认她还在』）一律视为正在发生或即将发生的剧情动作，不是单纯聊天客套、也不是可随意敷衍的对话。角色必须感知并正面承接这一计划：要么让该动作在叙事中真实发生并展开场景，要么明确回应这个约定（如『说好了，明天早上见』），并沿时间推进写出后续场景。严禁只做表面客套回应（如『嗯，好的』『知道了』），严禁把用户的动作/计划当字面疑问反问或撇清（例如回复『确认什么啊』就是错误示范）。反之，若用户消息是纯粹的台词、提问或日常对话内容（如『你吃饭了吗』『今天天气真好』），则正常作为对话内容回应即可，不要强行虚构动作场景。\n"
        f"8. 代称映射（必须严格遵守）：用户消息中以「她」「你」或角色名指代角色时，指代的就是角色本人。例如用户说『明天见到她，抱着她确认她还在』，意思是用户要见的是{character_name}自己、要抱的也是{character_name}自己、要确认的也是{character_name}还在——角色必须意识到指的是自己并正面承接，严禁把自己当第三者反问或撇清（例如回复『确认什么啊』就是错误示范）。\n"
        f"9. 时间线推进（必须严格遵守）：当用户消息中出现明确的未来时间词（如『明天』『明天早上』『今晚』『下午』等）且语境是要把故事推进到该时间点时，回复应让叙事自然推进到该时间点展开（例如深夜的对话→推进到第二天早上的见面场景），在推进后的时间点描写场景与动作，不要停留在上一时刻反复纠缠。推进时须与角色已知的时间线索保持一致（如角色提过『明天要早起升旗』）。若用户消息只是泛泛约定而无明确推进意图，则不强制切换场景，仍按第5条保持一致。"
    )
    suggest_parts = []
    if suggest_normal:
        suggest_parts.append(
            "普通建议:1. <贴合当前情境、安全稳妥的行动建议> 2. <另一条可靠建议>"
        )
    if suggest_naughty:
        suggest_parts.append(
            "坏坏建议:3. <带点坏心思、撩拨或大胆的行动建议> 4. <另一条更坏的>"
        )
    if suggest_parts:
        base += (
            "\n"
            f"\n【建议栏（必须严格遵守，格式唯一）】\n"
            f"1. 建议栏紧跟叙事正文之后输出，正文与建议栏之间空一行，不要写任何引导语或解释（如「以下是建议」「好的，建议如下」等一律禁止）。\n"
            f"2. 输出格式必须严格固定为以下模板，不允许任何变体：\n"
            f"```\n"
            f"普通建议:1. 建议内容 2. 建议内容\n"
            f"坏坏建议:3. 建议内容 4. 建议内容\n"
            f"```\n"
            f"3. 格式硬性规定：\n"
            f"   - 前缀只能是「普通建议:」和「坏坏建议:」，冒号为半角冒号，后面紧跟编号和内容；\n"
            f"   - 编号连续：普通建议固定用 1. 和 2.，坏坏建议固定用 3. 和 4.（若只开启一类，普通建议单独出现时仍用 1. 2.，坏坏建议单独出现时仍用 1. 2.）；\n"
            f"   - 同类两条建议写在同一行内，用空格隔开，禁止把建议拆成多行、禁止每行一条；\n"
            f"   - 禁止给整条建议加引号包裹、禁止加「建议：」「推荐：」等其他前缀、禁止用 - * 、、/ 等符号替代编号。\n"
            f"4. 建议栏的接收对象是用户「{user_nickname}」：每条建议是给用户下一步行动/台词的回应建议（指导用户如何回应{character_name}），具体到动作和台词，直接可执行。\n"
            f"5. 人称规则（必须严格遵守）：建议栏中禁止出现「你」字，采用无主语动作描述——直接以动词开头写用户要做的动作（如「继续从身后轻抱她」「提议一起坐到箱子上聊天」），台词引语内尽量不称呼用户，实在需要称呼时用昵称「{user_nickname}」；称呼{character_name}用「她」/角色名。\n"
            f"   - 正确示例：普通建议:1. 继续从身后轻抱她，慢慢亲吻她耳后安抚 2. 提议一起坐到箱子上聊天，顺势把手放在她大腿上\n"
            f"   - 错误示例（必须禁止）：你轻轻握住她的手，说「没事了，我陪着她」——出现「你」字，必须改为无主语：轻轻握住她的手，说「没事了，我陪着她」\n"
            f"6. 仅当某类建议未开启时，才省略对应那一行；两类都开启时两行都要输出，顺序固定为普通建议在前、坏坏建议在后。\n"
            f"格式示例（两类都开启时）：\n"
            f"```\n"
            f"普通建议:1. 轻轻握住她的手，说「没事了，我陪着{character_name}」 2. 拉起她的手，说「那我们回家吧，路上给{character_name}买章鱼小丸子」\n"
            f"坏坏建议:3. 凑近她耳边，低声说「姐姐今晚这么温柔，我都有点不习惯了」 4. 拉住她的手不放，说「那说好了，明天还要见面」\n"
            f"```"
        )
    return base


# ── 检索 query 构造 ──

_CONTINUATION_PREFIX_RE = re.compile(
    r"^(?:（接续对话）|\(接续对话\)|\[接续对话\]|接续对话[:：]?|（接续）|\(接续\)|接续[:：]|继续[:：])\s*"
)


def _strip_continuation_prefix(msg: str) -> str:
    """去掉「(接续对话)」「接续：」等续写控制前缀，避免污染语义检索 query。"""
    cleaned = _CONTINUATION_PREFIX_RE.sub("", msg).strip()
    return cleaned or msg


def _is_continuation_message(msg: str) -> bool:
    """判断消息是否带接续/续写控制前缀。"""
    return bool(_CONTINUATION_PREFIX_RE.match(msg))


def _build_retrieval_query(current_message: str, recent_dialogue: list[dict], scene_hint: str = "") -> str:
    """
    构造记忆检索 query。

    接续/续写场景下，用户消息往往是短句（如"看完陪我去走走好不好"），
    单独用它检索容易偏到"散步/回家"等泛化语义，漏掉真正锚定场景的历史片段。
    因此：
      1. 去掉「(接续对话)」等控制前缀；
      2. 若提供了导入记录末尾场景 scene_hint，优先拼在最前，把检索拉回末尾场景；
      3. 若近期对话里有上一段 AI 叙事，取其末尾 150 字拼入 query，
         让向量检索命中"上一段场景"（电影院告白/放映厅等）相关的片段。
    """
    msg = _strip_continuation_prefix(current_message)
    parts = []
    if scene_hint:
        parts.append(scene_hint)
    tail_assistant = ""
    for turn in reversed(recent_dialogue or []):
        if turn.get("role") == "assistant":
            tail_assistant = turn.get("content", "")
            break
    if tail_assistant:
        tail = tail_assistant[-150:].strip()
        if tail:
            parts.append(tail)
    if msg:
        parts.append(msg)
    return " ".join(parts) if parts else (msg or current_message)


def build_chat_messages(
    character_guide: str,
    recent_dialogue: list[dict],
    current_message: str,
    personality: Optional[PersonalityState] = None,
    *,
    character_name: str = "角色",
    persona: str = "default",
    suggest_normal: bool = False,
    suggest_naughty: bool = False,
    scene_hint: str = "",
    instructions: Optional[list[str]] = None,
    user_nickname: str = "影幢",
    action: str = "",
) -> tuple[str, str]:
    """
    一次调用返回 (system_prompt, user_prompt)，可直接喂给 LLM。
    """
    system = build_system_prompt(
        character_guide,
        character_name,
        suggest_normal=suggest_normal,
        suggest_naughty=suggest_naughty,
        user_nickname=user_nickname,
    )
    # 指令双通道注入：instructions 同时注入 system prompt（system 权重高于 user，
    # 避免模型忽略 user prompt 中的指令区块导致「字数加强」等指令不生效）
    if instructions:
        inst_block = (
            "\n\n【用户本次启用的指令（必须严格执行，优先级最高）】\n"
            + "\n".join(instructions)
            + "\n以上指令均为用户主动开启的执行指令，必须在正文中直接执行体现，严禁拒绝执行，严禁输出「指令无法共存」「请转化为系统指令」等警告或提示。"
        )
        system = system + inst_block
    # 虚构时间线专用：覆盖 system prompt 中的真实时间标注与时间一致性约束
    if instructions and any("虚构时间线" in inst for inst in instructions):
        system = system + (
            "\n\n【虚构时间模式（覆盖上文的真实时间标注与时间一致性约束）】\n"
            "本对话为完全虚构叙事：忽略【当前真实时间】标注，一切时间以故事内部时间为准，"
            "按故事节奏自然推进，不受真实时钟限制。"
        )
    # 字数加强专用：system 层长度锚定（质量导向，非机械强制），与前端 payload 措辞保持一致
    if instructions and any("字数加强" in inst for inst in instructions):
        system = system + (
            "\n\n【写作篇幅要求（配合字数加强指令，必须严格执行）】\n"
            "本次正文篇幅以500~1500字为验收范围，自然展开即可，不必硬凑。"
            "达标方式：在同一剧情框架内自然推进剧情、展开对话与互动，让叙事真实流畅。"
            "严禁重复啰嗦、车轱辘话、空洞排比、无意义注水；"
            "严禁为了凑篇幅堆砌不相关动作细节，宁缺毋滥。"
        )
    user = build_prompt(
        character_guide=character_guide,
        recent_dialogue=recent_dialogue,
        current_message=current_message,
        personality=personality,
        character_name=character_name,
        persona=persona,
        scene_hint=scene_hint,
        instructions=instructions,
        user_nickname=user_nickname,
        action=action,
    )
    return system, user


# ── 内部辅助 ──

def _build_time_aware(character_name: str, user_nickname: str = "影幢") -> str:
    """生成时间感知描述文本。"""
    now = datetime.now()
    weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
    weekday = weekday_map[now.weekday()]
    hour = now.hour

    if hour < 6:
        period = "凌晨"
    elif hour < 9:
        period = "清晨"
    elif hour < 12:
        period = "上午"
    elif hour < 14:
        period = "中午"
    elif hour < 18:
        period = "下午"
    elif hour < 21:
        period = "傍晚"
    else:
        period = "夜晚"

    date_str = f"{now.year}年{now.month}月{now.day}日"
    time_str = now.strftime("%H:%M")

    return f"【当前真实时间（必须以此为准，禁止在回复中编造与之冲突的具体钟点）】今天是 {date_str}，星期{weekday}，{period} {time_str}。{character_name}和{user_nickname}正在对话。"


# ═══════════════════════════════════════════════════════════════
# 独立验收
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Prompt 拼接器验收测试")
    print("=" * 60)

    guide = """你是林子欣，18岁女高中生，性格活泼带刺。
你喜欢用略带傲娇的语气说话，心里其实很在意对方。
你有一条建议栏，分为"普通建议"和"坏坏建议"。"""

    recent = [
        {"role": "user", "content": "你昨天为什么生气？"},
        {"role": "assistant", "content": "我哪有生气，我只是…算了。你根本不懂。"},
        {"role": "user", "content": "那今天去不去水族馆？"},
        {"role": "assistant", "content": "看心情。你上次说去结果放我鸽子，忘了？"},
    ]

    current = "我保证这次不鸽你。"

    # ── 无性格注入 ──
    prompt = build_prompt(guide, recent, current, character_name="林子欣")
    print("\n【无性格注入】")
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    assert "林子欣设定" in prompt
    assert "近期对话" in prompt
    assert "我保证这次不鸽你" in prompt
    assert "你昨天为什么生气" in prompt
    print("\n  ✓ 基本结构正确")

    # ── 带性格注入 ──
    p = PersonalityState()
    p.values = [
        [0.30, -0.50], [0.10, 0.05], [-0.20, 0.30], [0.40, 0.35], [0.60, -0.55],
        [0.15, -0.20], [-0.10, 0.70], [-0.30, 0.10], [0.05, 0.00], [0.25, 0.20],
        [-0.15, -0.10],
    ]
    p.intimacy = 0.25

    prompt2 = build_prompt(guide, recent, current, personality=p, character_name="林子欣")
    print("\n【带性格注入】")
    assert "当前性格注入" in prompt2
    assert "亲密意愿" in prompt2 or "她" in prompt2  # 至少包含模板生成的描述
    print("  ✓ 性格注入已嵌入")

    # ── build_chat_messages ──
    sys_p, usr_p = build_chat_messages(guide, recent, current, personality=p, character_name="林子欣")
    assert "你是林子欣" in sys_p
    assert "不要跳出角色" in sys_p
    print("\n  ✓ build_chat_messages 拆分正确")

    # ── 时间感知 ──
    time_block = _build_time_aware("林子欣")
    assert "今天是" in time_block
    print(f"  ✓ 时间感知: {time_block}")

    print("\n" + "=" * 60)
    print("全部测试通过！")
    print("=" * 60)
