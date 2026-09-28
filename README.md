# T1-B REMOTE_TOKEN 轮换 v8 交付包（Tom 复审用）

本仓库是 `Tom_v8_发送包_20260928.zip` 的完整内容（21 个文件，已逐文件展开，便于直接浏览 / 克隆）。

- 全部文件已脱敏：**无真实令牌、无真实 URL**（脱敏扫描 NONE）。
- 这是 **v8** 方案，回应 Tom 2026-09-28 **第六轮**复审（1 条新阻断：capability 创建时间须为「严格正整数时间戳」，拒绝数字后缀 / 小数 / 科学记数法 / 未来时间）。
- v8 仍为**待审核方案**；审核通过 ≠ 生产授权；本轮**未部署、未执行轮换**。凭证事件仍 OPEN；T1-B B 列修复生产批准数仍为 0。

## 先看这两个
- `DELIVERY_MANIFEST_20260928.md` —— 文件清单 + 每条阻断的修订与验证物 + Tom 复跑指引
- `next_rotation_plan_v8_20260928.md` —— v8 方案说明（含本轮 1 条阻断）

## 核心代码与测试
- `rotation_action_actual.gs` —— 拟部署服务端代码（v8，严格正整数时间戳解析 `_parseStrictPositiveInt`）
- `rotate_remote_token_client.py` —— 客户端（v6，本轮服务端改动不要求客户端变更）
- `rotation_logic_test.py` —— Python 逻辑测试（**119/119 PASS，exit 0**）
- `dispatch_sim_test.js` —— Node 分发仿真（**85/85 PASS，exit 0**，用生产真实 RemoteTrigger.gs + 真实 doPost 原文）
- `TEST_OUTPUT_20260928.txt` —— 本机真实执行的完整输出（未删改）

## 操作步骤
- `rotation_runbook_20260928.md` —— 部署 / 轮换 runbook（**§9.6** 为 v8 新增）

## 复跑
```bash
python rotation_logic_test.py   # 期望 119/119，exit 0（缺 deployment_evidence_20260926.json → exit 2）
node dispatch_sim_test.js       # 期望 85/85，exit 0（需 Node 18+）
```

> 注：原始 zip 包本体未包含在本仓库；本仓库即其 21 个组成文件的逐文件展开，内容等价。
