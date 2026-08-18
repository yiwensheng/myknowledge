# 易知授权服务

独立部署在云主机，**不要**打包进用户安装目录。

## 快速启动

```powershell
cd e:\app\Myknowledge\license-server
copy .env.example .env
# 编辑 .env：LICENSE_JWT_SECRET、LICENSE_ADMIN_KEY、虎皮椒参数
pip install -r requirements.txt
python -m app.main
```

默认端口 `18888`。健康检查：`GET /health`

## 客户端配置

用户易知 `.env` 中设置（与服务器 **JWT 密钥必须一致**）：

```env
MYKNOWLEDGE_LICENSE_SERVER=https://你的域名
MYKNOWLEDGE_LICENSE_JWT_SECRET=与 LICENSE_JWT_SECRET 相同
MYKNOWLEDGE_LICENSE_REQUIRED=1
```

开发自用可不配 `MYKNOWLEDGE_LICENSE_SERVER`，或设 `MYKNOWLEDGE_LICENSE_REQUIRED=0`。

## 生产环境要点（Windows Server）

| 项 | 说明 |
|----|------|
| `LICENSE_DEV_MOCK_PAY=0` | 正式支付 |
| `XUNHUPAY_SSL_VERIFY=0` | 若出网经代理/VPN 导致 `CERTIFICATE_VERIFY_FAILED` |
| `python-multipart` | `pip install -r requirements.txt` 必装，否则 notify 500 |
| 回调验收 | `curl -X POST https://域名/license/pay/xunhupay/notify -d test=1` → 纯文本 `fail` |

诊断脚本：`scripts/test_xunhupay_connect.py`

## 支付流程

1. 客户端 `POST /license/create-order` → 返回 `qr_url`、`order_id`
2. 用户微信/支付宝扫码
3. 虎皮椒回调 `POST /pay/xunhupay/notify`
4. 客户端轮询 `GET /license/order/{id}`，支付成功后 `POST /license/activate`

无虎皮椒配置时 `LICENSE_DEV_MOCK_PAY=1`，二维码为 mock，用管理接口标记已付。

## 管理接口

| 接口 | 说明 |
|------|------|
| **`GET /admin/ui`** | **Web 运营台**（推荐）：总览 / 订单 / 渠道对账 / 运维；易知与周易分列营收 |
| `POST /admin/mark-paid` | 手动标记订单已付（联调） |
| `POST /admin/unbind` | 解绑设备，允许换机激活 |
| `POST /admin/create-code` | 生成离线激活码 |
| `GET /admin/stats` | 统计（含 `revenue_total.by_product`） |
| `GET /admin/orders` | 订单列表（product / status / channel_code / 日期） |
| `GET /admin/channels` | 按渠道汇总已付与预估分成 |
| `GET` / `POST /admin/promoters` | 推广人档案（码、姓名、分成比例） |

Body 均含 `admin_key`（对应 `LICENSE_ADMIN_KEY`）；GET 管理接口用 query 传 `admin_key`。

生产入口：`https://www.yzwhysxx.cn/license/admin/ui`  

下单可选 `channel_code`（如 `P_ZHANGWENBO`），写入 `orders.channel_code`；空=官网无渠道。

### 解绑示例

```powershell
curl -X POST https://license.example.com/admin/unbind `
  -H "Content-Type: application/json" `
  -d "{\"admin_key\":\"你的密钥\",\"device_id\":\"用户设备哈希前32位\"}"
```

### 生成激活码

```powershell
curl -X POST https://license.example.com/admin/create-code `
  -H "Content-Type: application/json" `
  -d "{\"admin_key\":\"你的密钥\",\"plan\":\"year\"}"
```

将返回的 `code` 发给用户，在激活页输入即可。

## 单机绑定

- 下单/激活时绑定 `device_id`（客户端硬件指纹 SHA256 前 32 位）
- 其他设备无法使用同一授权
- 换机：管理员 `unbind`，或用户 `POST /license/self-unbind`（默认每年 1 次）

### 自助换机

客户端已激活用户可调用 `POST /api/license/self-unbind`（需联网），解绑后在新机重新订阅或输入激活码。

## 离线宽限

客户端上次联网 heartbeat 成功后 **7 天内**可离线使用；超期需联网校验。

## 数据文件

SQLite：`license.db`（与 `.env` 中 `LICENSE_DB` 一致），部署时注意备份。

统计与导出：`python ../scripts/license_admin.py stats --db license.db`；详见 `docs/commercial/授权统计与报表.md`。

## 生产部署

见 `deploy/` 目录：

- `deploy-windows-iis-checklist.md` — **Windows Server + IIS `/license` 反代 + 虎皮椒 + 联调清单**
- `nginx.conf.example` — HTTPS 反向代理（Linux）
- `yizhi-license.service` — systemd 单元
- `deploy-linux.sh` — 初始化说明

验收：`curl -s https://license.你的域名/health`（或 `https://你的域名/license/health`）
