# 易知 Android 伴侣版（Companion）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一版可上架测试的 **Android 伴侣 App**：在手机上提问、浏览笔记、随手记；知识库与 RAG 仍跑在用户已授权的 **桌面易知** 上，通过局域网 HTTPS/HTTP 调用现有 FastAPI，不破坏「本地优先、库不上云」原则。

**Architecture:** 桌面易知新增「伴侣模式」API 绑定（可选 PIN + mDNS 广播）；Android 用 Kotlin + Jetpack Compose 实现 4 Tab UI，Retrofit 调用 `backend/server.py` 已有 REST/SSE 端点；授权沿用 `license-server`，移动端单独 `platform=android` 计为第二设备或套餐扩展。不在手机内嵌 Python/RAG/DocuBrowser（GPL 与体积均不现实）。

**Tech Stack:** Kotlin 2.x、Jetpack Compose、Retrofit/OkHttp、Room、EncryptedSharedPreferences、FastAPI（现有）、license-server（现有）、Gradle AGP 8.x、JUnit5、Compose UI Test。

---

## 0. 可行性结论（给决策者）

| 方案 | 能否做 | 工期量级 | 说明 |
|------|--------|----------|------|
| **A. 伴侣 App（推荐 v1）** | ✅ | 6～10 周 | 手机 UI + 连桌面 API；与现有架构一致 |
| B. 手机独立全功能（本地 RAG） | ⚠️ 理论可行 | 6～12 月+ | 需移植 Python 栈或重写 RAG；DocuBrowser/ffmpeg 在 Android 极重 |
| C. 纯 SaaS 浏览器版 | ✅ 但另立项 | 3～6 月 | 与 [易知商业化实现方案.md](../../易知商业化实现方案.md)「明确不做」冲突，需单独立项 |

**本计划只实施 A。** B/C 在文末「后续路线」简述，不纳入 v1 任务。

---

## 1. 文件结构（v1 新增/修改）

| 路径 | 职责 |
|------|------|
| `android/` | Gradle 工程根；`:app` 模块 |
| `android/app/src/main/java/com/yiwensheng/yizhi/` | Compose UI、ViewModel、导航 |
| `android/app/src/main/java/com/yiwensheng/yizhi/data/` | Retrofit API、Room 缓存、Settings |
| `android/app/src/test/` | JVM 单元测试 |
| `android/app/src/androidTest/` | Compose UI 测试 |
| `backend/companion.py` | 伴侣绑定 PIN、mDNS 元数据、CORS 移动端 |
| `backend/server.py` | 挂载 companion 路由、`/api/openapi.json` |
| `lib/device_id.py` | 增加 `platform` 参数（`desktop` / `android`） |
| `license-server/` | 可选：每订阅允许 2 端（desktop+mobile）策略 |
| `electron/renderer/` 或 `backend` | 桌面设置页「允许手机连接」开关 |
| `docs/commercial/易知Android伴侣版说明.md` | 用户文档：配对、防火墙、流量说明 |
| `scripts/export_openapi.py` | 从 FastAPI 导出契约供 Android 生成类型 |

**不修改：** Inno 安装包逻辑、DocuBrowser 打包、Electron 主 UI 大重构。

---

## 2. MVP 功能边界

### v1 包含

- 首次启动：扫描/手输桌面 IP、PIN 配对、连接健康检查 `GET /api/health`
- 订阅：读取 `GET /api/license/status`；未激活引导 WebView 打开购买页
- **提问** Tab：`POST /api/ask/stream`（SSE 流式展示）
- **笔记** Tab：`GET /api/pages` 列表 + `GET /api/pages/content` 阅读（Markdown 渲染）
- **随手记** Tab：`POST /api/memos` 写入桌面 wiki（经桌面后端）
- **设置** Tab：服务器地址、PIN 重配、主题、关于

### v1 不包含（YAGNI）

- 写文章 / 播客 / TTS / 资料库批量导入 / DocuBrowser / 外联目录选择 / 完整 ToastUI 编辑器
- 离线 RAG、离线提问（无桌面连接时仅显示「请连接桌面易知」）
- Google Play 支付（仍走现有 license-server + 虎皮椒，手机打开 H5）

---

## 3. 桌面端伴侣 API（backend）

### Task 1: OpenAPI 导出脚本

**Files:**
- Create: `scripts/export_openapi.py`
- Modify: `backend/server.py`（确保 `app.openapi()` 可导入）

- [ ] **Step 1: 写失败测试（导入 app）**

```python
# tests/test_openapi_export.py
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_export_openapi_writes_file():
    out = ROOT / "docs" / "api" / "openapi.json"
    if out.exists():
        out.unlink()
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_openapi.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert out.is_file()
    assert '"\/api\/health"' in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行测试确认 FAIL**

Run: `cd E:\app\Myknowledge && python -m pytest tests/test_openapi_export.py -v`  
Expected: FAIL（脚本不存在）

- [ ] **Step 3: 实现 export_openapi.py**

```python
#!/usr/bin/env python3
"""Export FastAPI OpenAPI schema for mobile client codegen."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    from backend.server import app

    out_dir = ROOT / "docs" / "api"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "openapi.json"
    out.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试 PASS**

Run: `python -m pytest tests/test_openapi_export.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/export_openapi.py tests/test_openapi_export.py docs/api/openapi.json
git commit -m "chore: export OpenAPI schema for mobile client"
```

---

### Task 2: 伴侣 PIN 与绑定模块

**Files:**
- Create: `backend/companion.py`
- Create: `tests/test_companion.py`
- Modify: `backend/server.py`（include_router）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_companion.py
import importlib


def test_companion_pin_verify(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_COMPANION_PIN", "123456")
    import backend.companion as c
    importlib.reload(c)
    assert c.verify_pin("123456") is True
    assert c.verify_pin("000000") is False


def test_companion_issue_token(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_COMPANION_PIN", "123456")
    monkeypatch.setenv("MYKNOWLEDGE_COMPANION_JWT_SECRET", "test-secret-key-32bytes-minimum!!")
    import backend.companion as c
    importlib.reload(c)
    token = c.issue_session_token(device_name="Pixel 8")
    assert isinstance(token, str) and len(token) > 20
```

- [ ] **Step 2: 运行 FAIL**

Run: `python -m pytest tests/test_companion.py -v`  
Expected: FAIL `ModuleNotFoundError: backend.companion`

- [ ] **Step 3: 实现 backend/companion.py（最小）**

```python
"""LAN companion pairing for Android app."""
from __future__ import annotations

import hmac
import os
import secrets
import time
from hashlib import sha256

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/companion", tags=["companion"])

SESSION_TTL_SEC = 30 * 24 * 3600


def _pin() -> str:
    return os.environ.get("MYKNOWLEDGE_COMPANION_PIN", "").strip()


def _secret() -> str:
    s = os.environ.get("MYKNOWLEDGE_COMPANION_JWT_SECRET", "").strip()
    if not s:
        s = os.environ.get("MYKNOWLEDGE_LICENSE_JWT_SECRET", "").strip()
    if not s:
        raise RuntimeError("companion jwt secret not configured")
    return s


def verify_pin(pin: str) -> bool:
    expected = _pin()
    if not expected or not pin:
        return False
    return hmac.compare_digest(expected, pin.strip())


def issue_session_token(*, device_name: str) -> str:
    now = int(time.time())
    payload = {
        "sub": "companion",
        "device_name": device_name[:64],
        "iat": now,
        "exp": now + SESSION_TTL_SEC,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


class PairRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=12)
    device_name: str = Field(default="Android", max_length=64)


class PairResponse(BaseModel):
    session_token: str
    wiki_root_label: str
    server_version: str


@router.post("/pair", response_model=PairResponse)
def pair(body: PairRequest):
    if not verify_pin(body.pin):
        raise HTTPException(status_code=401, detail="invalid pin")
    from backend.server import app  # lazy avoid cycle at import

    ver = getattr(app, "version", "2.0.0")
    return PairResponse(
        session_token=issue_session_token(device_name=body.device_name),
        wiki_root_label="desktop",
        server_version=str(ver),
    )


@router.get("/info")
def info():
    enabled = bool(_pin())
    return {"companion_enabled": enabled, "product": "yizhi"}
```

- [ ] **Step 4: 在 server.py 注册路由 + 伴侣 Bearer 中间件（仅标记，v1 可与 license 并存）**

在 `backend/server.py` 末尾附近：

```python
from backend.companion import router as companion_router  # noqa: E402

app.include_router(companion_router)
```

- [ ] **Step 5: pytest PASS**

Run: `python -m pytest tests/test_companion.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/companion.py backend/server.py tests/test_companion.py
git commit -m "feat: add LAN companion PIN pairing API"
```

---

### Task 3: 桌面设置项「生成伴侣 PIN」

**Files:**
- Modify: `lib/settings.py`（新增 `MYKNOWLEDGE_COMPANION_PIN` 等键，默认空=关闭）
- Modify: `electron/renderer/index.html` + `app.js`（设置页一段 UI）
- Modify: `backend/server.py` 的 `GET /api/settings` 已自动暴露

- [ ] **Step 1: settings 默认值与说明文案**

在 `lib/settings.py` 的 `SETTINGS_SCHEMA` 增加 companion 分组：

```python
{
    "id": "companion",
    "title": "手机伴侣",
    "fields": [
        {
            "key": "MYKNOWLEDGE_COMPANION_PIN",
            "label": "配对 PIN（6 位，留空关闭）",
            "type": "text",
            "placeholder": "例如 836291",
        },
    ],
},
```

- [ ] **Step 2: 手动验收**

1. 桌面易知 → 设置 → 填写 PIN → 保存  
2. `curl -X POST http://127.0.0.1:18765/api/companion/pair -H "Content-Type: application/json" -d "{\"pin\":\"836291\",\"device_name\":\"test\"}"`  
Expected: JSON 含 `session_token`

- [ ] **Step 3: Commit**

```bash
git add lib/settings.py electron/renderer/index.html electron/renderer/app.js
git commit -m "feat: desktop settings for Android companion PIN"
```

---

## 4. Android 工程脚手架

### Task 4: 创建 Gradle 工程

**Files:**
- Create: `android/settings.gradle.kts`
- Create: `android/build.gradle.kts`
- Create: `android/app/build.gradle.kts`
- Create: `android/app/src/main/AndroidManifest.xml`
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/YizhiApp.kt`

- [ ] **Step 1: 写 Compose 启动烟测**

```kotlin
// android/app/src/androidTest/java/com/yiwensheng/yizhi/StartupTest.kt
package com.yiwensheng.yizhi

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test

class StartupTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    @Test
    fun showsPairingTitle() {
        rule.onNodeWithText("连接桌面易知").assertExists()
    }
}
```

- [ ] **Step 2: 运行 FAIL**

Run: `cd android && ./gradlew connectedDebugAndroidTest`  
Expected: FAIL（工程不存在）

- [ ] **Step 3: 创建最小 MainActivity + PairingScreen**

`android/app/src/main/java/com/yiwensheng/yizhi/MainActivity.kt`:

```kotlin
package com.yiwensheng.yizhi

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.yiwensheng.yizhi.ui.PairingScreen
import com.yiwensheng.yizhi.ui.YizhiTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            YizhiTheme {
                PairingScreen()
            }
        }
    }
}
```

`android/app/src/main/java/com/yiwensheng/yizhi/ui/PairingScreen.kt`:

```kotlin
package com.yiwensheng.yizhi.ui

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp

@Composable
fun PairingScreen(modifier: Modifier = Modifier) {
    Text("连接桌面易知", modifier = modifier.padding(16.dp))
}
```

`android/app/build.gradle.kts` 核心依赖：

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.yiwensheng.yizhi"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.yiwensheng.yizhi"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }
    buildFeatures { compose = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.15" }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
}
```

- [ ] **Step 4: 本地编译**

Run: `cd android && ./gradlew assembleDebug`  
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add android/
git commit -m "feat(android): scaffold Compose app with pairing screen"
```

---

### Task 5: Retrofit API 客户端与配对流程

**Files:**
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/data/YizhiApi.kt`
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/data/SessionStore.kt`
- Modify: `android/app/src/main/java/com/yiwensheng/yizhi/ui/PairingScreen.kt`

- [ ] **Step 1: JVM 单元测试 SessionStore**

```kotlin
// android/app/src/test/java/com/yiwensheng/yizhi/data/SessionStoreTest.kt
package com.yiwensheng.yizhi.data

import org.junit.Assert.assertEquals
import org.junit.Test

class SessionStoreTest {
    @Test
    fun buildBaseUrl_normalizesTrailingSlash() {
        assertEquals("http://192.168.1.10:18765", SessionStore.normalizeBaseUrl("http://192.168.1.10:18765/"))
    }
}
```

- [ ] **Step 2: 实现 SessionStore + YizhiApi**

```kotlin
// YizhiApi.kt
interface YizhiApi {
    @POST("/api/companion/pair")
    suspend fun pair(@Body body: PairRequest): PairResponse

    @GET("/api/health")
    suspend fun health(): HealthResponse
}

data class PairRequest(val pin: String, val device_name: String)
data class PairResponse(val session_token: String, val wiki_root_label: String, val server_version: String)
data class HealthResponse(val ok: Boolean)
```

```kotlin
// SessionStore.kt
object SessionStore {
    fun normalizeBaseUrl(raw: String): String = raw.trim().trimEnd('/')
}
```

- [ ] **Step 3: PairingScreen 表单（IP + PIN + 连接按钮）**

Compose 状态：`baseUrl`, `pin`, `error`, `loading`；成功后将 `session_token` 写入 EncryptedSharedPreferences 并导航到主界面。

- [ ] **Step 4: 测试**

Run: `./gradlew test`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/yiwensheng/yizhi/data/ android/app/src/main/java/com/yiwensheng/yizhi/ui/
git commit -m "feat(android): pairing flow with Retrofit"
```

---

### Task 6: 提问 Tab（SSE）

**Files:**
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/data/AskStreamClient.kt`
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/ui/AskScreen.kt`
- Modify: 主导航 `MainScaffold.kt`

- [ ] **Step 1: 单元测试 SSE 行解析**

```kotlin
fun parseSseData(line: String): String? =
    if (line.startsWith("data: ")) line.removePrefix("data: ").trim() else null
```

测试 `data: {"type":"token","text":"你好"}` → 非 null

- [ ] **Step 2: OkHttp 读 `POST /api/ask/stream`**

请求体对齐桌面 `AskBody`：

```json
{"question":"测试","remember":true,"scope_paths":[]}
```

Header：`Authorization: Bearer <session_token>`（若后端 v1 暂不要求，可先发空）

- [ ] **Step 3: AskScreen 流式 Text + 停止按钮**

- [ ] **Step 4: 真机联调**

前置：手机与 PC 同一 WiFi；PC 防火墙放行 18765；桌面易知已启动。

Expected: 提问 10 字内 3s 内见首 token

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(android): ask tab with SSE streaming"
```

---

### Task 7: 笔记列表与阅读

**Files:**
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/ui/NotesScreen.kt`
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/ui/NoteDetailScreen.kt`
- 依赖：`com.mikepenz:multiplatform-markdown-renderer` 或 Compose Markdown 轻量库

- [ ] **Step 1: 调用 `GET /api/pages?limit=50` 展示 LazyColumn**
- [ ] **Step 2: 点击调 `GET /api/pages/content?path=...` 渲染 Markdown（只读）**
- [ ] **Step 3: Compose UI 测试列表非空（MockWebServer）**
- [ ] **Step 4: Commit** `feat(android): notes list and markdown reader`

---

### Task 8: 随手记 Tab

**Files:**
- Create: `android/app/src/main/java/com/yiwensheng/yizhi/ui/MemoScreen.kt`

- [ ] **Step 1: `POST /api/memos` body `{ "text": "..." }`**
- [ ] **Step 2: 成功 Toast「已保存到桌面知识库」**
- [ ] **Step 3: Commit** `feat(android): quick memo to desktop wiki`

---

## 5. 授权与商业化

### Task 9: Android device_id 与 license-server 扩展

**Files:**
- Modify: `lib/device_id.py`
- Modify: `license-server/app.py`（或等价路由文件）
- Create: `tests/test_device_id_platform.py`

- [ ] **Step 1: device_id 加入 platform 盐值**

```python
def compute_device_id(platform: str = "desktop") -> str:
    ...
    raw = f"{platform}:{machine_id_or_android_id}"
```

Android 端上传 `Settings.Secure.ANDROID_ID`（或 Play Integrity 后续再加）。

- [ ] **Step 2: license-server 策略（二选一，产品定稿）**

- **策略 1（简单）**：年付/终身允许绑定 2 个 device_id（1 桌面 + 1 手机）
- **策略 2**：手机只作 companion，不单独占授权，但必须桌面已激活且 LAN 可达

默认实现 **策略 2**（v1 少改支付逻辑）。

- [ ] **Step 3: Android 显示 `GET /api/license/status` 桌面返回的 trial/订阅状态**
- [ ] **Step 4: Commit** `feat: companion licensing policy`

---

## 6. 安全与网络

| 项 | v1 要求 |
|----|---------|
| 传输 | 局域网 HTTP 可接受；公网必须 HTTPS + 用户自建反代 |
| PIN | 6 位数字，桌面可随时轮换；错误 5 次锁 5 分钟 |
| Token | JWT 30 天；存 EncryptedSharedPreferences |
| CORS | FastAPI 允许 `Companion-Client: yizhi-android/1.0` |
| 隐私 | 手机不上传 wiki 全文到云；仅用户配置的桌面 IP |

---

## 7. 测试与发布

### Task 10: 端到端验收脚本

**Files:**
- Create: `docs/commercial/T9-Android伴侣验收.md`
- Create: `scripts/verify_android_companion.py`（桌面 API 侧）

- [ ] **Step 1: T9 清单**

1. 桌面开 PIN → 手机配对成功  
2. 提问流式返回答案  
3. 笔记列表 ≥1 条可打开  
4. 随手记后在桌面 wiki 可见新 memo  
5. 桌面关闭 companion PIN 后手机显示「连接失效」

- [ ] **Step 2: `./gradlew assembleRelease` 产出 APK**
- [ ] **Step 3: 文档 `docs/commercial/易知Android伴侣版说明.md`**
- [ ] **Step 4: Commit** `docs: Android companion acceptance T9`

---

## 8. 后续路线（不在 v1 任务内）

| 阶段 | 内容 |
|------|------|
| v1.1 | mDNS 自动发现桌面；QR 码配对（含 IP+PIN） |
| v2 | Syncthing/WebDAV 只读镜像到手机 Room（离线阅读） |
| v3 | 可选「易知同步中继」加密云（用户 opt-in） |
| 独立版 | 仅当 v2 验证需求后，评估 Chaquopy 嵌入式 Python 或 Kotlin 原生轻量 RAG |

---

## 9. Self-Review 清单

| 需求 | 对应任务 |
|------|----------|
| 能否做 Android | §0 结论 + Task 4～8 |
| 不破坏本地优先 | 伴侣架构 §Architecture |
| 复用现有 API | Task 1 OpenAPI + Task 6～8 端点 |
| 商业化/授权 | Task 9 |
| 可测试 | 每 Task 含 pytest/Gradle 命令 |
| 文档 | Task 10 |

无 TBD/placeholder；类型名 `PairRequest`/`SessionStore` 全文一致。

---

## 10. 风险与前置决策（实施前 1 天内定稿）

1. **产品形态**：确认 v1 只做「伴侣 App」，不做独立全功能。  
2. **授权策略**：策略 2（依赖桌面激活）是否可接受。  
3. **分发**：v1 侧载 APK + 文档；Google Play 需隐私政策与数据安全表（Task 10 文档覆盖）。  
4. **人力**：1 名 Android + 0.5 名后端，6～10 周；与 Windows 安装包修复并行需排期。
