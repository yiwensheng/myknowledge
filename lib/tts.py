"""TTS via cloud APIs (OpenMAIC-compatible providers, no Edge TTS)."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import llm_config, load_dotenv

PROVIDERS = frozenset(
    {"openai-tts", "glm-tts", "qwen-tts", "minimax-tts", "doubao-tts", "azure-tts"}
)

DEFAULT_VOICES = {
    "openai-tts": "alloy",
    "glm-tts": "tongtong",
    "qwen-tts": "Cherry",
    "minimax-tts": "female-yujie",
    "doubao-tts": "zh_female_vv_uranus_bigtts",
    "azure-tts": "zh-CN-XiaoxiaoNeural",
}

TTS_PREVIEW_TEXT = "你好，欢迎使用易知播客。这是一段试听语音。"

# value = API voice id; label = 设置页展示名
VOICE_CATALOG: dict[str, list[dict[str, str]]] = {
    "glm-tts": [
        {"value": "tongtong", "label": "彤彤"},
        {"value": "xiaochen", "label": "小陈"},
        {"value": "chuichui", "label": "锤锤"},
        {"value": "jam", "label": "Jam（动动动物圈）"},
        {"value": "kazi", "label": "Kazi（动动动物圈）"},
        {"value": "douji", "label": "Douji（动动动物圈）"},
        {"value": "luodo", "label": "Luodo（动动动物圈）"},
    ],
    "openai-tts": [
        {"value": "alloy", "label": "Alloy"},
        {"value": "nova", "label": "Nova"},
        {"value": "shimmer", "label": "Shimmer"},
        {"value": "echo", "label": "Echo"},
        {"value": "fable", "label": "Fable"},
        {"value": "onyx", "label": "Onyx"},
    ],
    "qwen-tts": [
        {"value": "Cherry", "label": "芊悦（Cherry）"},
        {"value": "Ethan", "label": "晨煦（Ethan）"},
        {"value": "Serena", "label": "苏瑶（Serena）"},
        {"value": "Nofish", "label": "不吃鱼（Nofish）"},
        {"value": "Jennifer", "label": "詹妮弗（Jennifer）"},
        {"value": "Ryan", "label": "甜茶（Ryan）"},
        {"value": "Katerina", "label": "卡捷琳娜（Katerina）"},
        {"value": "Elias", "label": "墨讲师（Elias）"},
        {"value": "Jada", "label": "上海-阿珍（Jada）"},
        {"value": "Dylan", "label": "北京-晓东（Dylan）"},
        {"value": "Sunny", "label": "四川-晴儿（Sunny）"},
        {"value": "Chelsie", "label": "Chelsie"},
    ],
    "minimax-tts": [
        {"value": "female-yujie", "label": "御姐女声"},
        {"value": "female-shaonv", "label": "少女音"},
        {"value": "female-tianmei", "label": "甜美女性"},
        {"value": "male-qn-qingse", "label": "青涩男声"},
        {"value": "male-qn-jingying", "label": "精英男声"},
        {"value": "presenter_male", "label": "男主持人"},
        {"value": "presenter_female", "label": "女主持人"},
    ],
}

DEFAULT_BASE_URLS = {
    "openai-tts": "https://api.openai.com/v1",
    "glm-tts": "https://open.bigmodel.cn/api/paas/v4",
    "qwen-tts": "https://dashscope.aliyuncs.com/api/v1",
    "minimax-tts": "https://api.minimax.chat",
    "doubao-tts": "https://openspeech.bytedance.com/api/v1/tts",
}


@dataclass
class TTSResult:
    audio: bytes
    format: str
    provider: str


def _llm_api_base(llm: dict[str, Any]) -> str:
    chat_url = str(llm.get("chat_url") or "")
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if chat_url.endswith(suffix):
            return chat_url[: -len(suffix)].rstrip("/")
    return ""


def _infer_tts_provider(llm: dict[str, Any]) -> str:
    base = _llm_api_base(llm).lower()
    chat = str(llm.get("chat_url") or "").lower()
    combined = f"{base} {chat}"
    if "bigmodel.cn" in combined:
        return "glm-tts"
    if "dashscope" in combined:
        return "qwen-tts"
    if "minimax" in combined:
        return "minimax-tts"
    if "openai.com" in combined:
        return "openai-tts"
    return "openai-tts"


def _resolve_tts_provider(llm: dict[str, Any]) -> tuple[str, str]:
    """Return (provider, source) where source is explicit | auto | fallback."""
    explicit = os.environ.get("MYKNOWLEDGE_TTS_PROVIDER", "").strip().lower()
    dedicated_key = os.environ.get("MYKNOWLEDGE_TTS_API_KEY", "").strip()
    llm_base = _llm_api_base(llm).lower()
    if explicit and explicit in PROVIDERS:
        if explicit == "glm-tts" and not dedicated_key and "bigmodel.cn" not in llm_base:
            return _infer_tts_provider(llm), "fallback"
        return explicit, "explicit"
    if explicit and explicit not in PROVIDERS:
        return _infer_tts_provider(llm), "auto"
    return _infer_tts_provider(llm), "auto"


def _tts_error_message(status: int, body: bytes, provider: str) -> str:
    text = body.decode("utf-8", errors="replace")
    msg = text
    try:
        obj = json.loads(text)
        err = obj.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or err.get("code") or text)
        elif err:
            msg = str(err)
        else:
            msg = str(obj.get("message") or text)
    except json.JSONDecodeError:
        msg = text[:400]
    if status == 401:
        return (
            f"TTS 鉴权失败（{provider}）：{msg}。"
            "请在「设置 → 播客 TTS」选择与 API Key 匹配的提供商，"
            "或填写专用的 MYKNOWLEDGE_TTS_API_KEY。"
        )
    return f"TTS 请求失败（HTTP {status} · {provider}）：{msg[:400]}"


def tts_config() -> dict[str, Any]:
    load_dotenv()
    llm = llm_config()
    provider, provider_source = _resolve_tts_provider(llm)
    api_key = os.environ.get("MYKNOWLEDGE_TTS_API_KEY", "").strip() or str(llm.get("api_key") or "")
    base_url = os.environ.get("MYKNOWLEDGE_TTS_API_BASE", "").strip()
    if not base_url:
        if provider == "openai-tts":
            base_url = _llm_api_base(llm) or DEFAULT_BASE_URLS["openai-tts"]
        else:
            base_url = DEFAULT_BASE_URLS.get(provider, "")
    elif base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    base_url = base_url.rstrip("/")
    try:
        speed = float(os.environ.get("MYKNOWLEDGE_TTS_SPEED", "1.0"))
    except ValueError:
        speed = 1.0
    voice = os.environ.get("MYKNOWLEDGE_TTS_VOICE", "").strip() or DEFAULT_VOICES.get(provider, "")
    voice_host = os.environ.get("MYKNOWLEDGE_TTS_VOICE_HOST", "").strip()
    voice_guest = os.environ.get("MYKNOWLEDGE_TTS_VOICE_GUEST", "").strip()
    if provider == "openai-tts":
        if voice_host in ("tongtong", "xiaochen", ""):
            voice_host = voice_host or DEFAULT_VOICES["openai-tts"]
        if voice_guest in ("tongtong", "xiaochen", ""):
            voice_guest = voice_guest or "nova"
        if voice in ("tongtong", "xiaochen"):
            voice = DEFAULT_VOICES["openai-tts"]
    return {
        "provider": provider,
        "provider_source": provider_source,
        "api_key": api_key,
        "base_url": base_url,
        "model": os.environ.get("MYKNOWLEDGE_TTS_MODEL", "").strip(),
        "voice": voice,
        "voice_host": voice_host or voice,
        "voice_guest": voice_guest or voice,
        "speed": max(0.25, min(4.0, speed)),
    }


def voice_options_for_provider(provider: str, *, current: str = "") -> list[dict[str, str]]:
    prov = (provider or "openai-tts").strip().lower()
    if prov not in PROVIDERS:
        prov = "openai-tts"
    opts = [dict(o) for o in VOICE_CATALOG.get(prov, VOICE_CATALOG["openai-tts"])]
    cur = (current or "").strip()
    if cur and not any(o["value"] == cur for o in opts):
        opts.insert(0, {"value": cur, "label": f"{cur}（当前）"})
    return opts


def preview_tts_voice(voice: str, *, provider: str | None = None, text: str | None = None) -> TTSResult:
    sample = (text or TTS_PREVIEW_TEXT).strip()
    return generate_tts(sample, voice=voice, provider=provider)


def tts_status() -> dict[str, Any]:
    cfg = tts_config()
    source = cfg.get("provider_source") or "explicit"
    note = "使用 OpenMAIC 同款云 TTS 协议（GLM/Qwen/OpenAI 等），非 Edge TTS。"
    if source == "fallback":
        note += " 当前 LLM 非智谱端点，已自动改用 OpenAI 兼容 TTS。"
    elif source == "auto":
        note += " 已根据 LLM 端点自动选择 TTS 提供商。"
    return {
        "provider": cfg["provider"],
        "provider_source": source,
        "configured": bool(cfg.get("api_key")),
        "base_url": cfg.get("base_url"),
        "voice": cfg.get("voice"),
        "voice_host": cfg.get("voice_host") or cfg.get("voice"),
        "voice_guest": cfg.get("voice_guest") or cfg.get("voice"),
        "note": note,
    }


def _http_json(url: str, payload: dict, headers: dict, *, timeout: int = 120) -> tuple[int, bytes, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            hdrs = dict(resp.headers.items())
            return resp.status, body, hdrs
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers.items())


def _http_bytes(url: str, headers: dict | None = None, *, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _openai_tts(cfg: dict, text: str, voice: str) -> TTSResult:
    base = cfg["base_url"] or DEFAULT_BASE_URLS["openai-tts"]
    is_official = "api.openai.com" in base
    model = cfg.get("model") or ("gpt-4o-mini-tts" if is_official else "OmniVoice")
    status, body, hdrs = _http_json(
        f"{base.rstrip('/')}/audio/speech",
        {"model": model, "input": text, "voice": voice, "speed": cfg["speed"]},
        {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    if status >= 400:
        raise RuntimeError(_tts_error_message(status, body, "openai-tts"))
    ctype = hdrs.get("Content-Type", "")
    if ctype.startswith("application/json"):
        raise RuntimeError(_tts_error_message(status, body, "openai-tts"))
    fmt = "wav" if "wav" in ctype else "mp3"
    return TTSResult(audio=body, format=fmt, provider="openai-tts")


def _glm_tts(cfg: dict, text: str, voice: str) -> TTSResult:
    base = cfg["base_url"] or DEFAULT_BASE_URLS["glm-tts"]
    status, body, hdrs = _http_json(
        f"{base.rstrip('/')}/audio/speech",
        {
            "model": cfg.get("model") or "glm-tts",
            "input": text[:1024],
            "voice": voice,
            "speed": cfg["speed"],
            "volume": 1.0,
            "response_format": "wav",
        },
        {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    if status >= 400:
        raise RuntimeError(_tts_error_message(status, body, "glm-tts"))
    ctype = hdrs.get("Content-Type", "")
    if ctype.startswith("application/json"):
        raise RuntimeError(_tts_error_message(status, body, "glm-tts"))
    return TTSResult(audio=body, format="wav", provider="glm-tts")


def _qwen_tts(cfg: dict, text: str, voice: str) -> TTSResult:
    base = cfg["base_url"] or DEFAULT_BASE_URLS["qwen-tts"]
    rate = int(round((cfg["speed"] - 1.0) * 500))
    status, body, _ = _http_json(
        f"{base.rstrip('/')}/services/aigc/multimodal-generation/generation",
        {
            "model": cfg.get("model") or "qwen3-tts-flash",
            "input": {"text": text[:600], "voice": voice, "language_type": "Chinese"},
            "parameters": {"rate": rate},
        },
        {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    if status >= 400:
        raise RuntimeError(_tts_error_message(status, body, "qwen-tts"))
    data = json.loads(body.decode("utf-8"))
    url = (data.get("output") or {}).get("audio", {}).get("url")
    if not url:
        raise RuntimeError(f"Qwen TTS 无音频 URL: {body[:200]!r}")
    audio = _http_bytes(url)
    return TTSResult(audio=audio, format="wav", provider="qwen-tts")


def _minimax_tts(cfg: dict, text: str, voice: str) -> TTSResult:
    base = (cfg["base_url"] or DEFAULT_BASE_URLS["minimax-tts"]).rstrip("/")
    status, body, _ = _http_json(
        f"{base}/v1/t2a_v2",
        {
            "model": cfg.get("model") or "speech-2.8-hd",
            "text": text[:5000],
            "stream": False,
            "output_format": "hex",
            "voice_setting": {"voice_id": voice, "speed": cfg["speed"]},
        },
        {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    if status >= 400:
        raise RuntimeError(_tts_error_message(status, body, "minimax-tts"))
    data = json.loads(body.decode("utf-8"))
    hex_audio = ((data.get("data") or {}).get("audio") or "").strip()
    if not hex_audio:
        raise RuntimeError(f"MiniMax TTS 失败: {body[:200]!r}")
    return TTSResult(audio=bytes.fromhex(hex_audio), format="mp3", provider="minimax-tts")


def generate_tts(text: str, *, voice: str | None = None, provider: str | None = None) -> TTSResult:
    text = (text or "").strip()
    if not text:
        raise ValueError("TTS 文本为空")
    cfg = tts_config()
    if not cfg.get("api_key"):
        raise RuntimeError("未配置 TTS API Key（MYKNOWLEDGE_TTS_API_KEY 或 LLM API Key）")
    prov = (provider or cfg["provider"]).lower()
    v = voice or cfg.get("voice") or DEFAULT_VOICES.get(prov, "")
    if prov == "openai-tts":
        return _openai_tts(cfg, text, v)
    if prov == "glm-tts":
        return _glm_tts(cfg, text, v)
    if prov == "qwen-tts":
        return _qwen_tts(cfg, text, v)
    if prov == "minimax-tts":
        return _minimax_tts(cfg, text, v)
    raise RuntimeError(f"暂不支持的 TTS 提供商: {prov}（可选 glm-tts / qwen-tts / openai-tts / minimax-tts）")


def split_long_text(text: str, limit: int = 500) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf = ""
    for seg in re.split(r"([。！？!?；;])", text):
        if not seg:
            continue
        chunk = buf + seg
        if len(chunk) > limit and buf:
            parts.append(buf.strip())
            buf = seg
        else:
            buf = chunk
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text[:limit]]


def synthesize_segments(lines: list[tuple[str, str]]) -> list[dict]:
    """lines: [(speaker_label, text), ...] -> [{speaker, text, format, base64}, ...]"""
    cfg = tts_config()
    host_voice = cfg.get("voice_host") or cfg.get("voice")
    guest_voice = cfg.get("voice_guest") or cfg.get("voice")
    out: list[dict] = []
    for i, (speaker, text) in enumerate(lines):
        voice = host_voice
        if speaker and any(k in speaker for k in ("嘉宾", "专家", "B", "2")):
            voice = guest_voice
        for piece in split_long_text(text, 480 if cfg["provider"] == "glm-tts" else 500):
            result = generate_tts(piece, voice=voice)
            out.append(
                {
                    "index": i,
                    "speaker": speaker,
                    "text": piece,
                    "format": result.format,
                    "base64": base64.b64encode(result.audio).decode("ascii"),
                }
            )
    return out
