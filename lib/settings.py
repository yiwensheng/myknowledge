"""Visual settings: read/write Myknowledge .env and hot-reload."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from .config import env_file_path, load_dotenv

SECRET_KEYS = frozenset(
    {
        "MYKNOWLEDGE_LLM_API_KEY",
        "MYKNOWLEDGE_TTS_API_KEY",
        "MYKNOWLEDGE_LICENSE_JWT_SECRET",
        "MYKNOWLEDGE_LICENSE_ADMIN_KEY",
        "MYKNOWLEDGE_EMBEDDING_API_KEY",
        "MYKNOWLEDGE_ANYTHINGLLM_API_KEY",
    }
)

# 设置页不回显真实值，留空表示不修改；用户可输入自己的配置覆盖
MASK_VALUE_IN_UI_KEYS = frozenset(
    {
        "MYKNOWLEDGE_LLM_API_BASE",
        "MYKNOWLEDGE_LLM_MODEL",
    }
)

FIELD_HELP: dict[str, str] = {
    "MYKNOWLEDGE_LLM_API_BASE": (
        "大模型服务的接口根地址，通常以 /v1 结尾，例如 https://api.openai.com/v1。"
        "已保存过地址时输入框留空表示不修改；填写新地址会覆盖旧值。"
    ),
    "MYKNOWLEDGE_LLM_API_KEY": (
        "调用大模型所需的密钥。已配置时显示为星号，留空表示不修改；填写新 Key 会覆盖。"
    ),
    "MYKNOWLEDGE_LLM_MODEL": (
        "要调用的模型名称，例如 gpt-4o-mini、deepseek-chat、qwen-plus 等，以你的服务商文档为准。"
        "已保存过模型时留空表示不修改。"
    ),
    "MYKNOWLEDGE_LLM_TEMPERATURE_ASK": (
        "控制「提问」回答的随机程度。范围 0～1，最小 0、最大 1。"
        "数值越小越严谨、越贴近资料；越大越发散、越有创意但可能偏离事实。"
        "建议 0.10～0.20，默认 0.15。日常问答保持偏低即可。"
    ),
    "MYKNOWLEDGE_LLM_TEMPERATURE_PRODUCE": (
        "控制「写文章」时的表达灵活度。范围 0～1。"
        "略低于提问温度会显得刻板；略高则行文更自然。"
        "建议 0.25～0.40，默认 0.35。"
    ),
    "MYKNOWLEDGE_LLM_MAX_TOKENS_PRODUCE": (
        "单次写文章允许生成的最大长度（token 数）。范围 512～32768。"
        "数值越大可写越长，但更耗 API 额度、耗时更长。"
        "一般短文 4096 够用，长文建议 8192，默认 8192。"
    ),
    "MYKNOWLEDGE_ASK_REMEMBER": "开启后，连续追问会带上前几轮对话，便于上下文衔接。关闭则每问独立。",
    "MYKNOWLEDGE_AUTO_ARCHIVE_QA": "开启后，质量较好的问答会自动写入知识库，方便日后检索。",
    "MYKNOWLEDGE_FORTUNE": "开启后显示「今日知签 / 库运势」与八日签册（趣味提醒，非操作规范）。",
    "MYKNOWLEDGE_PRODUCE_RITUAL": "开启后，写文章定稿前可勾选「今日可归档」清单；不拦截定稿，默认关闭。",
    "MYKNOWLEDGE_MEMORY_TURNS": (
        "追问时注入最近几轮对话。范围 0～50；0 表示注入全部历史（可能较长）。"
        "建议 4～8，默认 6。过大可能占满上下文、增加费用。"
    ),
    "MYKNOWLEDGE_MEMORY_QA": (
        "除最近对话外，再检索几条相关的历史问答注入上下文。范围 0～20，默认 3。"
        "越大越可能找到旧话题，但也更占 token。"
    ),
    "MYKNOWLEDGE_RAG_MODE": (
        "知识库检索方式：混合（关键词+向量，推荐）、仅关键词、仅向量、或外部 AnythingLLM。"
        "一般保持「混合」即可。"
    ),
    "MYKNOWLEDGE_RAG_TOP_ASK": (
        "提问时从知识库取多少段资料。范围 1～20，默认 6。"
        "越大资料越多、回答可能更全，但噪声与 token 消耗也增加。"
    ),
    "MYKNOWLEDGE_RAG_TOP_PRODUCE": (
        "写文章时检索片段数。范围 1～20，默认 8。长文可适当增大。"
    ),
    "MYKNOWLEDGE_RAG_HYBRID_KEYWORD": (
        "混合检索中关键词（BM25）的权重。范围 0～1，默认 0.35。"
        "与向量权重之和会自动归一化；关键词高时更匹配精确用词。"
    ),
    "MYKNOWLEDGE_RAG_HYBRID_VECTOR": (
        "混合检索中语义向量的权重。范围 0～1，默认 0.65。"
        "向量高时更理解同义表述；与关键词权重此消彼长。"
    ),
    "MYKNOWLEDGE_RAG_CHUNK_SIZE": (
        "把笔记切成多长的片段做索引。范围 200～2000，默认 520 字。"
        "过小片段零散，过大可能混入无关句；一般无需改动。"
    ),
    "MYKNOWLEDGE_RAG_CHUNK_OVERLAP": (
        "相邻片段重叠字数，避免句意被截断。范围 0～400，默认 80。"
        "略增重叠可提高召回，但索引体积会变大。"
    ),
    "MYKNOWLEDGE_EMBEDDING_MODEL": (
        "向量化用的 Embedding 模型名，须与你的 API 服务商支持列表一致。"
        "默认 text-embedding-3-small；换模型后建议重建索引。"
    ),
    "MYKNOWLEDGE_FTS5": "开启后建立关键词索引，支持 BM25 混合检索。关闭则仅依赖向量（若已配置）。",
    "MYKNOWLEDGE_RAG_RRF": "RRF 融合排序：把关键词与向量两路结果更稳健地合并，建议保持开启。",
    "MYKNOWLEDGE_RAG_COARSE_K": (
        "粗排阶段保留的候选片段数。范围 5～50，默认 20。"
        "越大越不易漏召回，但 Rerank 阶段更慢。"
    ),
    "MYKNOWLEDGE_RAG_CONTEXTUAL": "为每个片段生成简短上下文再嵌入，检索更准，但入库与索引更慢。",
    "MYKNOWLEDGE_RERANK": "粗排后用 Rerank 模型重排序，提高相关度；需配置 Rerank API。",
    "MYKNOWLEDGE_RERANK_URL": "Rerank 服务地址；留空时可尝试与 Embedding 同 base。",
    "MYKNOWLEDGE_GRAPH_EXPAND": "沿 Wiki 双链扩展相关笔记片段，适合笔记互链多的库。",
    "MYKNOWLEDGE_RAG_AGENT": "检索置信度低时自动换说法再搜一轮，更慢但更稳；日常可关。",
    "MYKNOWLEDGE_RAG_PARENT_CHILD": (
        "父-子分块：用较短子块检索、较长父块喂给模型，召回更准、上下文更完整。"
        "开启或关闭后建议重建索引。"
    ),
    "MYKNOWLEDGE_RAG_CHILD_SIZE": (
        "子块长度（仅父-子模式）。范围约 120～父块大小，默认约为分块大小的一半。"
    ),
    "MYKNOWLEDGE_RAG_CONFLICT_PROMPT": (
        "提问时若多段资料冲突，强制模型列出矛盾双方，禁止和稀泥。"
    ),
    "MYKNOWLEDGE_RAG_HYDE": (
        "HyDE：先让模型写一小段假想笔记再检索，语义召回可能更好，但多一次调用、更慢；默认关。"
    ),
    "MYKNOWLEDGE_CONTRARIAN": (
        "矛盾检测：入库分析会写「核心假设」；在「记忆与进化」可一键扫描冲突并生成对照稿（不自动合并）。"
    ),
    "MYKNOWLEDGE_STYLE_ENABLED": "从现有笔记学习你的写作语气，用于「写文章」。",
    "MYKNOWLEDGE_STYLE_LLM_DISTILL": "用大模型提炼风格要点（更准，多一次 API 调用）。",
    "MYKNOWLEDGE_STYLE_SAMPLE_PAGES": "采样多少篇笔记学风格。范围 3～40，默认 18。",
    "MYKNOWLEDGE_NO_AI_SLOP": "写文章/改稿时自动注入「去 AI 味」措辞约束（no-ai-slop），默认开启。",
    "MYKNOWLEDGE_HUMAN_WRITING": "写文章/改稿时自动注入「活人感」材料关与硬禁辞章（human-writing），默认开启。随安装包分发，不依赖 Cursor。",
    "MYKNOWLEDGE_DZS": (
        "提问/写文章/推演时注入 DZS 认知催化（五阶段自适应循环与三维压力测试），默认开启。"
        "仍只许用检索片段；可关。随安装包分发，不依赖 Cursor。"
    ),
    "MYKNOWLEDGE_BASB": (
        "写文章时注入 BASB/第二大脑原则（思想群岛、中间成果包、渐进摘要），默认开启；蒸馏 Meta 亦对齐。"
        "可关。随安装包分发。"
    ),
    "MYKNOWLEDGE_DE_AI_WRITING": (
        "写文章/改稿时注入去 AI 味增强包（Humanizer-zh / 说人话 / de-AI 硬门槛蒸馏），默认开启。"
        "与 no-ai-slop、human-writing 叠加。可关。"
    ),
    "MYKNOWLEDGE_INGEST_ANALYZE": "导入资料时用 LLM 做摘要与标签，便于检索。",
    "MYKNOWLEDGE_INGEST_BATCH_ANALYZE": "批量上传时也做 LLM 分析；量大时更慢更费。",
    "MYKNOWLEDGE_INGEST_WORKERS": "并行入库线程数。0=自动；范围 0～8。机器慢时可设为 1～2。",
    "MYKNOWLEDGE_LINKED_DIRS_AUTO_INDEX": "外联文件夹有变更时自动更新 RAG 索引。",
    "MYKNOWLEDGE_LINKED_DIRS_POLL": "扫描外联目录的间隔（秒）。范围 15～3600，默认 60。",
    "MYKNOWLEDGE_DOCUBROWSER_ENABLED": "启用 DocuBrowser 文档全文检索增强。",
    "MYKNOWLEDGE_DOCUBROWSER_AUGMENT": "提问/写作时叠加 DocuBrowser 检索结果。",
    "MYKNOWLEDGE_DOCUBROWSER_AUTO_RESCAN": "导入新文件后自动重建 DocuBrowser 索引。",
    "MYKNOWLEDGE_DOCUBROWSER_PORT": "DocuBrowser 本地端口。范围 1024～65535；修改后需重启易知。",
    "MYKNOWLEDGE_TTS_PROVIDER": "播客配音引擎。留空「自动」则跟随 LLM 端点类型。",
    "MYKNOWLEDGE_TTS_API_KEY": "TTS 专用 Key；留空则尝试复用 LLM Key。",
    "MYKNOWLEDGE_TTS_API_BASE": "TTS 服务地址；多数情况留空即可。",
    "MYKNOWLEDGE_TTS_VOICE_HOST": "播客主持人音色，可点「试听」预览。",
    "MYKNOWLEDGE_TTS_VOICE_GUEST": "播客嘉宾音色，可点「试听」预览。",
    "MYKNOWLEDGE_TTS_SPEED": "语速倍数。范围 0.5～2.0，1.0 为正常；过大可能听不清。",
    "MYKNOWLEDGE_LICENSE_REQUIRED": "商业版可开启：未激活时限制功能。个人使用保持关闭。",
    "MYKNOWLEDGE_LICENSE_SERVER": "授权验证服务器地址。",
    "MYKNOWLEDGE_LICENSE_JWT_SECRET": "授权 JWT 密钥，留空则不修改。",
    "MYKNOWLEDGE_LOOP_LEVEL": (
        "自动整理知识库的积极程度。范围 1～3，默认 1。"
        "数字越大整理越频繁、改动越多；保守用户保持 1。"
    ),
}

SETTING_GROUPS: list[dict[str, Any]] = [
    {
        "id": "llm",
        "label": "大模型",
        "fields": [
            {"key": "MYKNOWLEDGE_LLM_API_BASE", "label": "API 地址", "type": "text", "placeholder": "https://你的服务/v1"},
            {"key": "MYKNOWLEDGE_LLM_API_KEY", "label": "API Key", "type": "password", "placeholder": "留空则不修改"},
            {"key": "MYKNOWLEDGE_LLM_MODEL", "label": "模型", "type": "text", "placeholder": "例如 gpt-4o-mini"},
            {"key": "MYKNOWLEDGE_LLM_TEMPERATURE_ASK", "label": "提问温度", "type": "number", "min": 0, "max": 1, "step": 0.05},
            {"key": "MYKNOWLEDGE_LLM_TEMPERATURE_PRODUCE", "label": "写文章温度", "type": "number", "min": 0, "max": 1, "step": 0.05},
            {"key": "MYKNOWLEDGE_LLM_MAX_TOKENS_PRODUCE", "label": "写文章最大 tokens", "type": "number", "min": 512, "max": 32768, "step": 256},
        ],
    },
    {
        "id": "memory",
        "label": "对话与记忆",
        "fields": [
            {"key": "MYKNOWLEDGE_ASK_REMEMBER", "label": "记住连续对话", "type": "bool"},
            {"key": "MYKNOWLEDGE_AUTO_ARCHIVE_QA", "label": "优质问答自动归档", "type": "bool"},
            {"key": "MYKNOWLEDGE_FORTUNE", "label": "今日知签 / 库运势", "type": "bool", "hint": "趣味提醒；可关"},
            {"key": "MYKNOWLEDGE_PRODUCE_RITUAL", "label": "定稿前归档清单", "type": "bool", "hint": "仪式提醒，不拦截"},
            {"key": "MYKNOWLEDGE_MEMORY_TURNS", "label": "追问注入最近 N 轮", "type": "number", "min": 0, "max": 50, "step": 1, "hint": "0=全部"},
            {"key": "MYKNOWLEDGE_MEMORY_QA", "label": "相关历史问答条数", "type": "number", "min": 0, "max": 20, "step": 1},
        ],
    },
    {
        "id": "rag",
        "label": "检索 RAG",
        "fields": [
            {"key": "MYKNOWLEDGE_RAG_MODE", "label": "检索模式", "type": "select", "options": [
                {"value": "hybrid", "label": "混合（推荐）"},
                {"value": "keyword", "label": "仅关键词"},
                {"value": "vector", "label": "仅向量"},
                {"value": "external", "label": "仅 AnythingLLM"},
            ]},
            {"key": "MYKNOWLEDGE_RAG_TOP_ASK", "label": "提问检索片段数", "type": "number", "min": 1, "max": 20, "step": 1},
            {"key": "MYKNOWLEDGE_RAG_TOP_PRODUCE", "label": "写文章检索片段数", "type": "number", "min": 1, "max": 20, "step": 1},
            {"key": "MYKNOWLEDGE_RAG_HYBRID_KEYWORD", "label": "混合-关键词权重", "type": "number", "min": 0, "max": 1, "step": 0.05},
            {"key": "MYKNOWLEDGE_RAG_HYBRID_VECTOR", "label": "混合-向量权重", "type": "number", "min": 0, "max": 1, "step": 0.05},
            {"key": "MYKNOWLEDGE_RAG_CHUNK_SIZE", "label": "分块大小", "type": "number", "min": 200, "max": 2000, "step": 20},
            {"key": "MYKNOWLEDGE_RAG_CHUNK_OVERLAP", "label": "分块重叠", "type": "number", "min": 0, "max": 400, "step": 10},
            {"key": "MYKNOWLEDGE_EMBEDDING_MODEL", "label": "Embedding 模型", "type": "text"},
            {"key": "MYKNOWLEDGE_FTS5", "label": "FTS5 关键词索引", "type": "bool", "hint": "BM25 混合检索"},
            {"key": "MYKNOWLEDGE_RAG_RRF", "label": "RRF 融合排序", "type": "bool"},
            {"key": "MYKNOWLEDGE_RAG_COARSE_K", "label": "粗排候选数", "type": "number", "min": 5, "max": 50, "step": 1},
            {"key": "MYKNOWLEDGE_RAG_CONTEXTUAL", "label": "Contextual 分块嵌入", "type": "bool"},
            {"key": "MYKNOWLEDGE_RERANK", "label": "启用 Rerank API", "type": "bool"},
            {"key": "MYKNOWLEDGE_RERANK_URL", "label": "Rerank API 地址", "type": "text"},
            {"key": "MYKNOWLEDGE_GRAPH_EXPAND", "label": "Wiki 链接图扩展", "type": "bool"},
            {"key": "MYKNOWLEDGE_RAG_AGENT", "label": "受限检索 Agent", "type": "bool", "hint": "低置信时换 query 再检"},
            {"key": "MYKNOWLEDGE_RAG_PARENT_CHILD", "label": "父-子分块", "type": "bool", "hint": "改后建议重建索引"},
            {"key": "MYKNOWLEDGE_RAG_CHILD_SIZE", "label": "子块大小", "type": "number", "min": 120, "max": 1000, "step": 20},
            {"key": "MYKNOWLEDGE_RAG_CONFLICT_PROMPT", "label": "冲突提示（提问）", "type": "bool"},
            {"key": "MYKNOWLEDGE_RAG_HYDE", "label": "HyDE 假想文档检索", "type": "bool", "hint": "多一次 LLM，更慢"},
        ],
    },
    {
        "id": "style",
        "label": "写作风格学习",
        "fields": [
            {"key": "MYKNOWLEDGE_STYLE_ENABLED", "label": "从知识库学习语气", "type": "bool"},
            {"key": "MYKNOWLEDGE_STYLE_LLM_DISTILL", "label": "LLM 提炼风格要点", "type": "bool"},
            {"key": "MYKNOWLEDGE_STYLE_SAMPLE_PAGES", "label": "采样笔记数", "type": "number", "min": 3, "max": 40, "step": 1},
            {
                "key": "MYKNOWLEDGE_NO_AI_SLOP",
                "label": "写文章去 AI 味",
                "type": "bool",
                "hint": "自动注入套话禁用规则，默认开",
            },
            {
                "key": "MYKNOWLEDGE_HUMAN_WRITING",
                "label": "写文章活人感约束",
                "type": "bool",
                "hint": "材料关与硬禁辞章，默认开；安装版自带",
            },
            {
                "key": "MYKNOWLEDGE_DZS",
                "label": "DZS 认知催化",
                "type": "bool",
                "hint": "提问/写文章/推演注入压力测试与自适应深度，默认开",
            },
            {
                "key": "MYKNOWLEDGE_BASB",
                "label": "BASB 知识复用",
                "type": "bool",
                "hint": "写文章思想群岛与中间包原则，默认开",
            },
            {
                "key": "MYKNOWLEDGE_DE_AI_WRITING",
                "label": "去 AI 味增强包",
                "type": "bool",
                "hint": "Humanizer-zh/说人话/de-AI 蒸馏，默认开",
            },
        ],
    },
    {
        "id": "ingest",
        "label": "导入与入库",
        "fields": [
            {"key": "MYKNOWLEDGE_INGEST_ANALYZE", "label": "入库 LLM 分析提炼", "type": "bool"},
            {"key": "MYKNOWLEDGE_INGEST_BATCH_ANALYZE", "label": "批量上传也做 LLM 分析", "type": "bool"},
            {"key": "MYKNOWLEDGE_INGEST_WORKERS", "label": "并行 worker 数", "type": "number", "min": 0, "max": 8, "step": 1, "hint": "0=自动"},
            {"key": "MYKNOWLEDGE_LINKED_DIRS_AUTO_INDEX", "label": "外联目录变更自动更新 RAG", "type": "bool"},
            {"key": "MYKNOWLEDGE_LINKED_DIRS_POLL", "label": "外联目录扫描间隔（秒）", "type": "number", "min": 15, "max": 3600, "step": 15},
            {"key": "MYKNOWLEDGE_CONTRARIAN", "label": "矛盾检测（核心假设）", "type": "bool", "hint": "记忆面板可扫描冲突"},
        ],
    },
    {
        "id": "docubrowser",
        "label": "文档检索增强",
        "fields": [
            {"key": "MYKNOWLEDGE_DOCUBROWSER_ENABLED", "label": "启用 DocuBrowser", "type": "bool"},
            {"key": "MYKNOWLEDGE_DOCUBROWSER_AUGMENT", "label": "检索时增强", "type": "bool"},
            {"key": "MYKNOWLEDGE_DOCUBROWSER_AUTO_RESCAN", "label": "导入后自动索引", "type": "bool"},
            {"key": "MYKNOWLEDGE_DOCUBROWSER_PORT", "label": "端口", "type": "number", "min": 1024, "max": 65535, "step": 1, "hint": "改端口需重启易知"},
        ],
    },
    {
        "id": "tts",
        "label": "播客 TTS",
        "fields": [
            {
                "key": "MYKNOWLEDGE_TTS_PROVIDER",
                "label": "TTS 提供商",
                "type": "select",
                "options": [
                    {"value": "", "label": "自动（跟随 LLM 端点）"},
                    {"value": "openai-tts", "label": "OpenAI 兼容"},
                    {"value": "glm-tts", "label": "智谱 GLM TTS"},
                    {"value": "qwen-tts", "label": "通义 Qwen TTS"},
                    {"value": "minimax-tts", "label": "MiniMax"},
                ],
            },
            {"key": "MYKNOWLEDGE_TTS_API_KEY", "label": "TTS API Key", "type": "password", "placeholder": "留空则复用 LLM Key"},
            {"key": "MYKNOWLEDGE_TTS_API_BASE", "label": "TTS API 地址", "type": "text", "placeholder": "留空则按提供商默认；OpenAI 兼容可留空复用 LLM 地址"},
            {"key": "MYKNOWLEDGE_TTS_VOICE_HOST", "label": "主持人音色", "type": "tts_voice"},
            {"key": "MYKNOWLEDGE_TTS_VOICE_GUEST", "label": "嘉宾音色", "type": "tts_voice"},
            {"key": "MYKNOWLEDGE_TTS_SPEED", "label": "语速", "type": "number", "min": 0.5, "max": 2, "step": 0.1},
        ],
    },
    {
        "id": "license",
        "label": "订阅授权",
        "fields": [
            {"key": "MYKNOWLEDGE_LICENSE_REQUIRED", "label": "启用订阅校验", "type": "bool"},
            {"key": "MYKNOWLEDGE_LICENSE_SERVER", "label": "授权服务地址", "type": "text", "placeholder": "http://127.0.0.1:18888"},
            {"key": "MYKNOWLEDGE_LICENSE_JWT_SECRET", "label": "JWT 密钥", "type": "password", "placeholder": "留空则不修改"},
        ],
    },
    {
        "id": "other",
        "label": "其它",
        "fields": [
            {"key": "MYKNOWLEDGE_LOOP_LEVEL", "label": "自动整理级别", "type": "number", "min": 1, "max": 3, "step": 1},
        ],
    },
]

_DEFAULTS: dict[str, str] = {
    "MYKNOWLEDGE_LLM_API_BASE": "",
    "MYKNOWLEDGE_LLM_MODEL": "",
    "MYKNOWLEDGE_LLM_TEMPERATURE_ASK": "0.15",
    "MYKNOWLEDGE_LLM_TEMPERATURE_PRODUCE": "0.35",
    "MYKNOWLEDGE_LLM_MAX_TOKENS_PRODUCE": "8192",
    "MYKNOWLEDGE_ASK_REMEMBER": "1",
    "MYKNOWLEDGE_AUTO_ARCHIVE_QA": "1",
    "MYKNOWLEDGE_FORTUNE": "1",
    "MYKNOWLEDGE_PRODUCE_RITUAL": "0",
    "MYKNOWLEDGE_MEMORY_TURNS": "6",
    "MYKNOWLEDGE_MEMORY_QA": "3",
    "MYKNOWLEDGE_RAG_MODE": "hybrid",
    "MYKNOWLEDGE_RAG_TOP_ASK": "6",
    "MYKNOWLEDGE_RAG_TOP_PRODUCE": "8",
    "MYKNOWLEDGE_RAG_HYBRID_KEYWORD": "0.35",
    "MYKNOWLEDGE_RAG_HYBRID_VECTOR": "0.65",
    "MYKNOWLEDGE_RAG_CHUNK_SIZE": "520",
    "MYKNOWLEDGE_RAG_CHUNK_OVERLAP": "80",
    "MYKNOWLEDGE_EMBEDDING_MODEL": "text-embedding-3-small",
    "MYKNOWLEDGE_FTS5": "1",
    "MYKNOWLEDGE_RAG_RRF": "1",
    "MYKNOWLEDGE_RAG_RRF_K": "60",
    "MYKNOWLEDGE_RAG_COARSE_K": "20",
    "MYKNOWLEDGE_RAG_CONTEXTUAL": "1",
    "MYKNOWLEDGE_RERANK": "1",
    "MYKNOWLEDGE_GRAPH_EXPAND": "1",
    "MYKNOWLEDGE_GRAPH_MAX_HOPS": "2",
    "MYKNOWLEDGE_RAG_AGENT": "0",
    "MYKNOWLEDGE_RAG_PARENT_CHILD": "1",
    "MYKNOWLEDGE_RAG_CHILD_SIZE": "260",
    "MYKNOWLEDGE_RAG_CONFLICT_PROMPT": "1",
    "MYKNOWLEDGE_RAG_HYDE": "0",
    "MYKNOWLEDGE_CONTRARIAN": "0",
    "MYKNOWLEDGE_STYLE_ENABLED": "1",
    "MYKNOWLEDGE_STYLE_LLM_DISTILL": "1",
    "MYKNOWLEDGE_STYLE_SAMPLE_PAGES": "18",
    "MYKNOWLEDGE_NO_AI_SLOP": "1",
    "MYKNOWLEDGE_HUMAN_WRITING": "1",
    "MYKNOWLEDGE_DZS": "1",
    "MYKNOWLEDGE_BASB": "1",
    "MYKNOWLEDGE_DE_AI_WRITING": "1",
    "MYKNOWLEDGE_INGEST_ANALYZE": "1",
    "MYKNOWLEDGE_INGEST_BATCH_ANALYZE": "0",
    "MYKNOWLEDGE_INGEST_WORKERS": "0",
    "MYKNOWLEDGE_LINKED_DIRS_AUTO_INDEX": "1",
    "MYKNOWLEDGE_LINKED_DIRS_POLL": "60",
    "MYKNOWLEDGE_DOCUBROWSER_ENABLED": "1",
    "MYKNOWLEDGE_DOCUBROWSER_AUGMENT": "1",
    "MYKNOWLEDGE_DOCUBROWSER_AUTO_RESCAN": "1",
    "MYKNOWLEDGE_DOCUBROWSER_PORT": "18766",
    "MYKNOWLEDGE_TTS_PROVIDER": "",
    "MYKNOWLEDGE_TTS_VOICE_HOST": "tongtong",
    "MYKNOWLEDGE_TTS_VOICE_GUEST": "xiaochen",
    "MYKNOWLEDGE_TTS_SPEED": "1.0",
    "MYKNOWLEDGE_LICENSE_REQUIRED": "0",
    "MYKNOWLEDGE_LOOP_LEVEL": "1",
}

_LLM_GROUP_ID = "llm"
_LLM_SETTING_KEYS = frozenset(
    f["key"] for g in SETTING_GROUPS if g.get("id") == _LLM_GROUP_ID for f in g.get("fields") or []
)


def _llm_settings_hidden() -> bool:
    """Portable / bundled builds: LLM is preconfigured in .env, hide from Settings UI."""
    load_dotenv()
    flag = os.environ.get("MYKNOWLEDGE_HIDE_LLM_SETTINGS", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    return os.environ.get("YIZHI_PORTABLE", "").strip() == "1"


def _parse_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    env_path = env_file_path()
    if not env_path.is_file():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if "#" in val and not val.startswith('"'):
            val = val.split("#", 1)[0].strip()
        if key:
            out[key] = val
    return out


def _mask_secret(key: str, val: str) -> str:
    if key in SECRET_KEYS and val:
        return "********"
    return val


def _ui_value_for_field(key: str, ftype: str, raw: str) -> tuple[Any, bool | None]:
    """Return (display_value, configured_or_none). configured only for MASK_VALUE_IN_UI_KEYS."""
    if key in MASK_VALUE_IN_UI_KEYS:
        configured = bool(str(raw).strip())
        return "", configured
    if ftype == "password":
        return _mask_secret(key, str(raw)), None
    return str(raw), None


def _enrich_tts_voice_fields(groups: list[dict[str, Any]], provider: str) -> None:
    from .tts import voice_options_for_provider

    for g in groups:
        if g.get("id") != "tts":
            continue
        g["tts_provider"] = provider
        for entry in g.get("fields") or []:
            if entry.get("type") != "tts_voice":
                continue
            cur = str(entry.get("value") or "")
            entry["options"] = voice_options_for_provider(provider, current=cur)


def get_settings_payload() -> dict[str, Any]:
    load_dotenv()
    from .tts import tts_config

    file_vals = _parse_env_file()
    tts_provider = str(tts_config().get("provider") or "openai-tts")
    groups = []
    hide_llm = _llm_settings_hidden()
    for g in SETTING_GROUPS:
        if hide_llm and g.get("id") == _LLM_GROUP_ID:
            continue
        fields_out = []
        for f in g["fields"]:
            key = f["key"]
            raw = os.environ.get(key, file_vals.get(key, _DEFAULTS.get(key, "")))
            display_val, configured = _ui_value_for_field(key, f["type"], str(raw))
            entry = {**f, "value": display_val}
            if f["type"] == "bool":
                entry["value"] = raw.strip().lower() in ("1", "true", "yes")
            if configured is not None:
                entry["configured"] = configured
                if configured and f["type"] == "text":
                    entry["placeholder"] = "已配置，留空则不修改"
            if key in FIELD_HELP:
                entry["help"] = FIELD_HELP[key]
            fields_out.append(entry)
        groups.append({"id": g["id"], "label": g["label"], "fields": fields_out})
    _enrich_tts_voice_fields(groups, tts_provider)
    note = "保存后立即生效（改端口需重启易知）。API 地址/模型/密钥留空表示不修改已保存的值。"
    if hide_llm:
        note = "大模型已由安装包预配置，无需在此填写。其余项保存后立即生效（改端口需重启易知）。"
    return {
        "env_path": str(env_file_path()),
        "groups": groups,
        "tts_provider": tts_provider,
        "hide_llm_settings": hide_llm,
        "note": note,
    }


def _bool_to_env(v: Any) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    s = str(v).strip().lower()
    return "1" if s in ("1", "true", "yes", "on") else "0"


def _normalize_field_value(field: dict[str, Any], value: Any) -> str | None:
    """Return None to skip updating this key (password unchanged)."""
    key = field["key"]
    ftype = field["type"]
    if ftype == "password":
        s = str(value or "").strip()
        if not s or s == "********":
            return None
        return s
    if key in MASK_VALUE_IN_UI_KEYS and ftype == "text":
        s = str(value or "").strip()
        if not s:
            return None
        return s
    if ftype == "bool":
        return _bool_to_env(value)
    if ftype == "number":
        s = str(value).strip()
        if not s:
            return _DEFAULTS.get(key, "0")
        return s
    return str(value).strip()


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Merge values into .env and reload process environment."""
    field_by_key: dict[str, dict[str, Any]] = {}
    for g in SETTING_GROUPS:
        for f in g["fields"]:
            field_by_key[f["key"]] = f

    updates: dict[str, str | None] = {}
    hide_llm = _llm_settings_hidden()
    for key, val in values.items():
        if hide_llm and key in _LLM_SETTING_KEYS:
            continue
        if key not in field_by_key:
            continue
        updates[key] = _normalize_field_value(field_by_key[key], val)

    _write_env_updates(updates)
    apply_env_to_process()
    try:
        from .prompts import invalidate_persona_cache

        invalidate_persona_cache()
    except Exception:
        pass
    return get_settings_payload()


def _write_env_updates(updates: dict[str, str | None]) -> None:
    env_path = env_file_path()
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    touched: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = line.partition("=")[0].strip()
        if key not in updates:
            new_lines.append(line)
            continue
        val = updates[key]
        touched.add(key)
        if val is None:
            new_lines.append(line)
        else:
            new_lines.append(f"{key}={val}")

    for key, val in updates.items():
        if key in touched or val is None:
            continue
        new_lines.append(f"{key}={val}")

    if not env_path.is_file() and not new_lines:
        new_lines = ["# Myknowledge settings", ""]

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def apply_env_to_process() -> None:
    """Force reload all MYKNOWLEDGE_* keys from .env into os.environ."""
    env_path = env_file_path()
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if "#" in val and not val.startswith('"'):
            val = val.split("#", 1)[0].strip()
        if not key:
            continue
        if key.startswith("MYKNOWLEDGE_") or key in ("WIKI_ROOT", "MYKNOWLEDGE_ROOT"):
            os.environ[key] = val


def settings_schema() -> list[dict[str, Any]]:
    return deepcopy(SETTING_GROUPS)
