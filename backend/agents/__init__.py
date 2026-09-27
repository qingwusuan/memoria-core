"""Memoria Core — 多 Agent 化阶段一落地包

结构：
  base.py             -- Agent 基类：统一 LLM 调用入口，独立模型/参数/容错
  responder.py        -- ResponderAgent：主回复（同步、唯一用户可见路径）
  personality.py      -- PersonalityAnalyzerAgent：性格 delta 分析 + 敏感点应用
  memory_extractor.py -- MemoryExtractorAgent：聊天事件提取入库（后台）
  orchestrator.py     -- Orchestrator：同步回复 + 后台事件解耦编排
  util.py             -- 纯函数工具（回复拆分 / 汉字计数）
"""
