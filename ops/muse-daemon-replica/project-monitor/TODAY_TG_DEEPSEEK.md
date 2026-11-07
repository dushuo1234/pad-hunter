# 今日清单电报 → DeepSeek / 扫描

adu 2026-10-28：推送到电报群的内容交给 DeepSeek（队友「扫描」），Ori 不跑例程直推。

## 群
- title: bot123123
- chat_id: -1004456992195
- bot: @aduahhbot（token: secrets/telegram_bot_token，勿外泄）
- config: secrets/telegram_today_chat.json

## 规则
1. 只推「今日项目清单」digest（`today_projects_tg_push.py`，同日同 hash 去重）
2. CA 只推「固定CA」：在今日清单内 **且** 代币（`is_token`/`kind=token`）**且**（① 部署者/关联钱包部署 **或** ② 官推发出）。站点刮取 / 纯高置信候选 / 仅曾推过电报 → 待确认，**不要** `push_ca`
3. 其它 Pad Hunter CA / 柳叶刀 / 全局信号 **禁止**
4. 出口：`telegram_today_only.push_ca`（硬闸：today handles + token + 固定CA；`force` 仅测试）

## 命令
```bash
cd /workspace/project-monitor
python3 today_projects_tg_push.py          # digest，有变才发
python3 today_projects_tg_push.py --force  # 强制
# CA：from telegram_today_only import push_ca
```

## 调度建议
- 接在 today_projects sync/playbook 之后（清单变了再 digest）
- T-20 高置信/官推 CA：扫描用 DeepSeek 粗判后调 push_ca（勿绕过 today gate）

## 炼油优先级（adu 2026-10-28）
- 优先确认并推送「代币 CA」（仍须今日清单内 + 高置信/官推/已开盘）
- NFT CA 次要
- 假币 / 未核验继续挡

## 炼油（adu via 阿杜项目分析 2026-10-28）
- 优先冲代币 → 只推/只抬 **代币合约 CA**；NFT 降权，不进高置信电报出口。
- `push_ca` 前请确认 is_token / kind=token（可用 ca_gate.verify_address）。

## 固定 CA（adu via 阿杜项目分析 2026-10-28 16:12）
推电报的 CA 必须是「固定CA」：
1. 部署者或关联钱包部署，或
2. 官推发出
站点刮取 / 纯高置信 / 仅曾推过电报 → 仍「待确认」，不要当固定推。
Fishesrh `0x098e…` 两边未过 → candidate。
