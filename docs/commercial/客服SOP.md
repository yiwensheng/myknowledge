# 易知 · 客服标准操作流程（SOP）

> 面向运营/客服。授权服务：`https://www.yzwhysxx.cn/license`  
> 管理密钥仅保存在服务器 `license-server/.env` 的 `LICENSE_ADMIN_KEY`，勿发给用户。

---

## 0. 前置准备

```powershell
cd e:\app\Myknowledge
$env:MYKNOWLEDGE_LICENSE_SERVER = "https://www.yzwhysxx.cn/license"
$env:LICENSE_ADMIN_KEY = "<服务器 LICENSE_ADMIN_KEY>"
```

常用命令：

```powershell
python scripts/license_admin.py health
python scripts/license_admin.py plans
python scripts/license_admin.py export-csv --db \\服务器路径\license.db
```

---

## 1. 支付成功但未解锁（最高频）

**用户描述**：已扫码扣款，易知仍提示未激活。

| 步骤 | 操作 |
|------|------|
| 1 | 让用户等待 1～2 分钟并重启易知 |
| 2 | 收集：**设备 ID**（关于页）、**支付截图**、**下单时间** |
| 3 | 登录服务器查 `license.db` 或导出 CSV，找对应 `order_id` |
| 4 | 若订单仍为 `pending` 且虎皮椒已扣款 → 虎皮椒后台查回调；应急可 `mark-paid` |
| 5 | 指导用户在激活页点「已有激活码」或重新打开易知等待轮询 |

**应急补单**（mock 联调或回调失败时）：

```powershell
python scripts/license_admin.py mark-paid <order_id>
```

用户重启易知或在激活页等待自动激活。

---

## 2. 换机 / 解绑

**政策**：自助换机 **每年 1 次**；超额或特殊情况人工解绑。

| 场景 | 处理 |
|------|------|
| 用户还有旧机 | 引导「关于 → 自助换机」 |
| 旧机已不可用 | 核实购买凭证后后台解绑 |

```powershell
python scripts/license_admin.py unbind --license-id <license_id>
# 或
python scripts/license_admin.py unbind --device-id <设备ID前32位>
```

解绑后用户在新机重新订阅或输入激活码。

---

## 3. 发放离线激活码（赠送/补单/内测）

```powershell
python scripts/license_admin.py create-code month
python scripts/license_admin.py create-code year
```

将返回的 `code` 发给用户 → 激活页输入 → 激活。

---

## 4. 不会配置 LLM API

1. 打开「设置 → 大模型」填写 API 地址、Key、模型  
2. 「设置 → 能力检测」确认 **大模型 API** 为绿  
3. 说明：**订阅不含 API 费用**，用户自备 Key  
4. 参考 [FAQ.md](FAQ.md)

---

## 5. 能力检测非全绿

1. 「设置 → 能力检测 → **一键修复可选工具**」  
2. 仍红项：多为 Rerank/Embedding 未配置或 API 不支持 → 见 FAQ  
3. 高级用户可在安装目录运行 `python scripts/setup_optional_tools.py`

---

## 6. 退款（需业务规则先行）

建议口径（可在《用户服务协议》定稿）：

- **7 天内、未成功激活**：可全额退  
- 已激活：原则上不退；特殊情况人工判定  

流程：确认订单 → 业务负责人审批 → 支付渠道退款 → 必要时 `unbind` + 作废授权。

---

## 7. 升级 / 安装失败

| 问题 | 处理 |
|------|------|
| 找不到 Python | 必须使用官方便携包/安装包，勿用源码版 |
| 覆盖升级 | 保留 `wiki`、`.env`、`.license` |
| 检查更新 | 「关于 → 检查更新」 |

---

## 8. 模拟工单演练（阶段 5 验收）

新人按 FAQ 独立完成以下 3 单（可用 mock 支付 + mark-paid）：

1. **安装 + 激活码激活**  
2. **支付未解锁 → mark-paid 补单**  
3. **换机 → 自助解绑或后台 unbind**

---

## 9. 升级与故障

| 现象 | 处理 |
|------|------|
| `/health` 不通 | 服务器：`nssm restart YizhiLicense`；查 `stderr.log` |
| 外网 `/license/health` 502 | 查 IIS `/license` 应用程序与 ARR |
| JWT 相关大面积失效 | 检查是否误改 `LICENSE_JWT_SECRET`（改后需用户重激活） |

每周：备份 `license.db`（见 `scripts/backup_license_db.ps1`）。
