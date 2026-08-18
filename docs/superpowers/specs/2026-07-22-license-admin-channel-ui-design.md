# 授权服运营台 + 渠道落库 — 设计说明

日期：2026-07-22  
状态：已确认（方案 B）  
部署：`https://www.yzwhysxx.cn/license`（易知 / 周易共用）

## 目标

1. 订单落库 `channel_code`（客户端已传则写入；空=官网无渠道）
2. Web 运营台（非仅脚本）：总览、订单、渠道对账、运维
3. **产品区分**：`product=yizhi|zhouyi`；总营收 + 分产品营收

## 入口与鉴权

- 页面：`/admin/ui`（公网即 `…/license/admin/ui`）
- 登录：输入 `LICENSE_ADMIN_KEY`，存 `sessionStorage`，请求带 `admin_key`

## 数据

- `orders.channel_code TEXT`（幂等 ADD COLUMN）
- 表 `promoters`：`code PK, name, commission_rate DEFAULT 0.2, note, created_at`
- `POST /license/create-order` 增加可选 `channel_code`

## 页面

| Tab | 能力 |
|-----|------|
| 总览 | 已付合计；易知 / 周易分列；套餐分布；待支付 |
| 订单 | 筛产品/状态/渠道/日期；标已付；CSV |
| 渠道 | 按码汇总笔数/金额/预估分成；维护推广人 |
| 运维 | 解绑、生成激活码 |

顶部全局筛选：全部 | 易知 | 周易。

## 不做

推广人自助门户、自动打款、改已锁定设备渠道。
