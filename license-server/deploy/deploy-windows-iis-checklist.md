# Windows IIS + yzwhysxx.cn/license 部署检查清单

> 适用：`https://www.yzwhysxx.cn/license` 路径反代 + NSSM 常驻 Python 授权服务 + 虎皮椒支付。  
> **发布运营台 / 渠道落库**：见同目录 [`发布运营台-最短步骤.md`](./发布运营台-最短步骤.md)。

---

## 一、服务器 `.env` 检查清单（`C:\yizhi\license-server\.env`）

逐项核对，全部打勾后再关 mock、对外发包。

### 1. 基础服务

| 项 | 示例 / 要求 | 自检命令 |
|----|-------------|----------|
| `LICENSE_PORT` | `18888` | `netstat -ano \| findstr :18888` 有 LISTENING |
| `LICENSE_DB` | `license.db`（相对路径，落在 `license-server` 目录） | 文件存在且可写 |
| NSSM 服务 | `YizhiLicense` 状态 **正在运行** | `nssm status YizhiLicense` |
| 本机健康 | 返回 JSON | `curl http://127.0.0.1:18888/health` |

### 2. 密钥（生产必须换掉默认值）

| 项 | 要求 | 注意 |
|----|------|------|
| `LICENSE_JWT_SECRET` | ≥32 位随机串，**与用户包 `MYKNOWLEDGE_LICENSE_JWT_SECRET` 完全一致** | 可打入用户包（仅验签） |
| `LICENSE_ADMIN_KEY` | 随机串，**仅服务器与运维脚本使用** | **绝不**打入用户安装包 |

生成随机串（PowerShell）：

```powershell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
```

### 3. 套餐价格（与购买页一致）

| 项 | 当前线上示例 |
|----|-------------|
| `LICENSE_PRICE_MONTH` | `19` |
| `LICENSE_PRICE_YEAR` | `99` |
| `LICENSE_UNBIND_PER_YEAR` | `1`（自助换机次数/年） |

改价后需 `nssm restart YizhiLicense`，并确认：

```powershell
curl https://www.yzwhysxx.cn/license/license/plans
```

### 4. 虎皮椒（xunhupay）

| 项 | 值 |
|----|-----|
| `XUNHUPAY_APPID` | 虎皮椒后台 AppId |
| `XUNHUPAY_APPSECRET` | 虎皮椒后台 AppSecret |
| `XUNHUPAY_GATEWAY` | 默认 `https://api.xunhupay.com/payment/do.html` |
| `XUNHUPAY_NOTIFY_URL` | **`https://www.yzwhysxx.cn/license/pay/xunhupay/notify`** |
| `XUNHUPAY_RETURN_URL` | 支付成功跳转页（可选，如官网文章链接） |
| `LICENSE_DEV_MOCK_PAY` | 联调阶段 `1`；**正式上线改为 `0`** |

虎皮椒后台需配置 **异步通知 URL** 与 `XUNHUPAY_NOTIFY_URL` **完全一致**（含 `https`、路径、无多余斜杠）。

### 5. 生产切换验收

改 `.env` 并 `nssm restart YizhiLicense` 后：

```powershell
curl https://www.yzwhysxx.cn/license/health
```

| 字段 | mock 联调 | 正式支付 |
|------|-----------|----------|
| `ok` | `true` | `true` |
| `mock_pay` | `true` | **`false`** |

`mock_pay: false` 表示已读虎皮椒 AppId/AppSecret，创建订单会走真实二维码。

---

## 二、IIS `/license` 应用程序

| 项 | 要求 |
|----|------|
| 别名 | `license` |
| 物理路径 | 如 `C:\inetpub\yzwhysxx-license` |
| `web.config` | 反代到 `http://127.0.0.1:18888/{R:1}` |
| 应用程序池 | **无托管代码** + 集成管道 |
| ARR | 服务器节点 **Enable proxy** 已勾选 |
| URL Rewrite | 已安装 |

公网验收：

```powershell
curl https://www.yzwhysxx.cn/license/health
curl https://www.yzwhysxx.cn/license/license/plans
```

---

## 三、用户安装包 `.env`（构建时注入）

在**开发机**执行：

```powershell
cd e:\app\Myknowledge
.\scripts\build-portable.ps1 `
  -LicenseServer "https://www.yzwhysxx.cn/license" `
  -JwtSecret "<与服务器 LICENSE_JWT_SECRET 相同>"
```

用户包应含：

```env
MYKNOWLEDGE_LICENSE_SERVER=https://www.yzwhysxx.cn/license
MYKNOWLEDGE_LICENSE_JWT_SECRET=<同上>
MYKNOWLEDGE_LICENSE_REQUIRED=1
```

**不得包含**：`LICENSE_ADMIN_KEY`、虎皮椒密钥、开发者 LLM Key。

---

## 四、运行 `test_license_flow.py`（逐步）

脚本路径：`Myknowledge/scripts/test_license_flow.py`  
覆盖：健康检查 → 下单 → mark-paid → 激活 → JWT 验签 → heartbeat → 激活码 → 解绑。

### 步骤 1：在开发机打开 PowerShell

```powershell
cd e:\app\Myknowledge
```

### 步骤 2：设置环境变量（从服务器 `.env` 抄真实值）

```powershell
$env:TEST_LICENSE_SERVER = "https://www.yzwhysxx.cn/license"
$env:LICENSE_ADMIN_KEY     = "<服务器 LICENSE_ADMIN_KEY>"
$env:LICENSE_JWT_SECRET    = "<服务器 LICENSE_JWT_SECRET>"
```

> 若 `LICENSE_ADMIN_KEY` 不对，会在 `mark-paid` 步骤报 **403 Forbidden**。

### 步骤 3：运行测试

```powershell
python scripts/test_license_flow.py
```

期望输出：

```text
RUN order_activate…
  OK order_activate
RUN activation_code…
  OK activation_code
RUN unbind…
  OK unbind
OK all license flow tests
```

### 步骤 4：失败排查

| 现象 | 处理 |
|------|------|
| 连接超时 / SSL 错误 | 检查域名、防火墙、IIS 站点 |
| `403 Forbidden`（admin） | `LICENSE_ADMIN_KEY` 与服务器不一致 |
| JWT 验签失败 | `LICENSE_JWT_SECRET` 与服务器不一致 |
| `create-order` 报错 xunhupay | 检查虎皮椒 AppId/Secret；或暂设 `LICENSE_DEV_MOCK_PAY=1` 仅测激活链路 |

### 步骤 5：用 CLI 做单项检查（可选）

```powershell
$env:MYKNOWLEDGE_LICENSE_SERVER = "https://www.yzwhysxx.cn/license"
$env:LICENSE_ADMIN_KEY = "<同上>"

python scripts/license_admin.py health
python scripts/license_admin.py plans
python scripts/license_admin.py create-code year
```

---

## 五、真实支付联调（mock 通过后）

1. 服务器 `.env`：`LICENSE_DEV_MOCK_PAY=0`，填虎皮椒参数，重启 NSSM  
2. 虎皮椒后台通知 URL = `https://www.yzwhysxx.cn/license/pay/xunhupay/notify`  
3. 客户端或 curl 创建订单，**小额真实扫码**  
4. 查单：`GET https://www.yzwhysxx.cn/license/order/{order_id}` → `status: paid`  
5. `POST /license/activate` 或客户端激活页完成激活  

应急（支付通道未通时）：仍可用 `license_admin.py mark-paid <order_id>` 模拟已付。

---

## 六、上线前最终 Checklist

- [ ] `/health` 返回 `mock_pay: false`（若已接虎皮椒）
- [ ] `test_license_flow.py` 三项全 OK
- [ ] 真实小额支付 → 回调 → 激活 走通
- [ ] `license.db` 备份策略（定期复制 `C:\yizhi\license-server\license.db`）
- [ ] 用户包 `build-portable.ps1` 已注入正确 `LICENSE_SERVER` / JWT
- [ ] 干净 Windows VM：安装 → 订阅 → 提问（T1～T8 人工验收）
- [ ] `docs/commercial/` 购买页、FAQ、隐私说明已替换域名与主体

---

## 七、日常运维速查

```powershell
# 重启授权服务
C:\tools\nssm\win64\nssm.exe restart YizhiLicense

# 日志
Get-Content C:\yizhi\license-server\stderr.log -Tail 30

# 导出订单（在含 license.db 的机器上）
python scripts/license_admin.py export-csv --db C:\yizhi\license-server\license.db
```

---

## 八、购买页部署（主站 IIS）

```powershell
mkdir C:\inetpub\wwwroot\yizhi
copy <仓库>\docs\commercial\purchase.html C:\inetpub\wwwroot\yizhi\
copy <仓库>\docs\commercial\faq.html C:\inetpub\wwwroot\yizhi\
```

验收：`https://www.yzwhysxx.cn/yizhi/purchase.html` · `.../yizhi/faq.html`

---

## 九、license.db 备份

```powershell
powershell -File scripts\backup_license_db.ps1 -DbPath C:\yizhi\license-server\license.db
```

注册每日计划任务（在仓库 `scripts/` 拷到服务器后）：

```powershell
powershell -ExecutionPolicy Bypass -File setup_license_backup_task.ps1
```

---

## 十、常见问题（生产已验证）

| 现象 | 处理 |
|------|------|
| create-order 502 / xunhupay network SSL | `.env` 设 `XUNHUPAY_SSL_VERIFY=0`，装 `certifi` |
| 付了款仍 pending | notify 500 → 更新 `main.py`（手动解析表单）+ `python-multipart` |
| 公网 notify 返回 HTML | CDN/WAF 拦截 POST；纯文本 `fail` 才正常 |
| 二维码不显示 | 客户端重启；`mock_pay` 须为 false |

回调验收：

```powershell
curl -X POST "https://www.yzwhysxx.cn/license/pay/xunhupay/notify" -d "test=1"
# 期望：fail
```
