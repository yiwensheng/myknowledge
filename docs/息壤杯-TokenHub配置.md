# 如何接入 TokenHub（易知 · 息壤杯）

易知已支持 **OpenAI 兼容**接口，接入 TokenHub = 拿到三样东西写进配置，**不用改代码**。

```text
API Base（含 /v1） + API Key + 模型名
        ↓
MYKNOWLEDGE_LLM_API_BASE / _KEY / _MODEL
        ↓
提问 / 写文章 / 入库分析 走 TokenHub
```

官方协议参考（OpenAI 兼容）：[TokenHub API 说明](https://cloud.tencent.com/document/product/1823/130078)、[快速入门](https://cloud.tencent.com/document/product/1823/130058)。  
**注意**：息壤杯/江苏智云 Store 若单独发了赛事 Base，**以赛事发放为准**，不要想当然用公网默认域名。

---

## 第一步：拿到凭证（先开通，再填易知）

按优先级尝试：

1. **赛事专区**：`https://ai.js.189.cn` 首页 → OPC/息壤杯 → 模型、工具、Token、算力相关入口。  
2. **参赛指南 PDF / 报名成功短信邮件**：常有 TokenHub 开通链接或客服。  
3. **智云 Store Token 套餐**：江苏电信对开发者提供 Token 服务（见智云 Store 公告），咨询办理后要 **API 地址 + Key + 可用模型列表**。  
4. 若赛事明确要求走腾讯云大模型 TokenHub 控制台：在控制台创建 API Key，大陆默认 Base 多为：  
   `https://tokenhub.tencentmaas.com/v1`  
   备用：`https://tokenhub.tencentmaas.cn/v1`  
   用 `GET /v1/models` + Bearer Key 可列出 `model` 名。

你需要抄下来的三行：

| 项 | 示例（勿照抄，以你账号为准） |
|----|------------------------------|
| Base | `https://xxxx/v1` |
| Key | `sk-...` 或平台发放串 |
| Model | 如 `deepseek-v3` / 赛事指定名 / `ep-xxxxxxxx` |

**个人中心没有入口 ≠ 没开通**；模型资源多半在首页专区或需单独申请。暂未拿到 Key 时：用现有 LLM 先做 Demo，正式录屏前再切换。

---

## 第二步：写入易知

### 1）备份

```powershell
cd e:\app\myknowledge
copy .env .env.bak-before-tokenhub
```

### 2）改 `.env`（或 GUI「设置」）

```env
MYKNOWLEDGE_LLM_API_BASE=https://tokenhub.tencentmaas.com/v1
MYKNOWLEDGE_LLM_API_KEY=你的Key
MYKNOWLEDGE_LLM_MODEL=deepseek-v3
```

把三行换成你的真实值。Base **必须能访问** `/chat/completions`（一般以 `/v1` 结尾）。

可选 Embedding（若平台提供）：

```env
MYKNOWLEDGE_EMBEDDING_API_BASE=https://tokenhub.tencentmaas.com/v1
MYKNOWLEDGE_EMBEDDING_API_KEY=你的Key
MYKNOWLEDGE_EMBEDDING_MODEL=<embedding模型名>
```

GUI：打开易知 → **设置** → 填 Base / Key / 模型 → 保存（热加载）。改 `.env` 后若未热加载，重启后端/`启动易知.bat`。

---

## 第三步：先 curl 验通，再开易知

把 `YOUR_KEY`、`MODEL`、`BASE` 换成你的：

```powershell
$BASE = "https://tokenhub.tencentmaas.com/v1"
$KEY  = "YOUR_KEY"
# 列模型
curl.exe -s "$BASE/models" -H "Authorization: Bearer $KEY"
# 试对话
curl.exe -s "$BASE/chat/completions" `
  -H "Authorization: Bearer $KEY" `
  -H "Content-Type: application/json" `
  -d "{\"model\":\"deepseek-v3\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}"
```

- `401`：Key 错或未开通  
- `404`/连不上：Base 或地域不对（换赛事给的地址或 `.cn` 备用域）  
- 有 `choices`：再写入易知

易知内验证：

```powershell
cd e:\app\myknowledge
yws ask "用一句话介绍易知"
```

---

## 第四步：参赛材料截图

| 截图 | 要求 |
|------|------|
| 设置页 | Base + 模型名可见，**Key 打码** |
| 一次提问 | 流式回答成功 |

归档目录建议：`docs/xirang-cup-assets/`。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 门户个人中心没有 TokenHub | 回首页找 OPC/模型/Token；或问赛事客服要 API 文档 |
| Base 填了主机名没 `/v1` | 补上 `/v1` 再试 |
| 模型名不对 | `GET /v1/models` 看返回的 `id`，原样填入 `MYKNOWLEDGE_LLM_MODEL` |
| 易知仍走旧接口 | 确认改的是 `e:\app\myknowledge\.env`，保存后重启；GUI 设置是否覆盖了 `.env` |
| 赛事 Key 未下发 | 用现网模型做 Demo；材料里写「将切换至赛事 TokenHub」，录正式视频前再切 |

---

## 状态勾选

- [ ] 已拿到 Base / Key / Model（赛事或控制台）  
- [ ] curl `/models` 或 `/chat/completions` 成功  
- [ ] 已写入易知 `.env` 或设置页  
- [ ] `yws ask` 成功  
- [ ] 设置页截图已打码存档  
