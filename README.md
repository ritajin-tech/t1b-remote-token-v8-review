# T1-B REMOTE_TOKEN 轮换 — v9 复审材料（2026-09-28）

本仓库为给外部审核人（Tom Zhu）的代码复审交付，**公开**、无需账号即可查看。
所有文件已脱敏：**无真实令牌、无真实 URL**（脱敏扫描 NONE）。

## 先看这两个

1. `DELIVERY_MANIFEST_20260928.md` —— 交付清单 + Tom 第七轮 3 项修正的逐条对应 + 文件哈希表
2. `next_rotation_plan_v9_20260928.md` —— 方案 v9 正文（本轮主体）

## 本轮（v9）改了什么

回应 Tom **第七轮**复审的 3 项：

| # | Tom 意见 | 处置 |
|---|---|---|
| 1 | 校验前先 `trim()`，带前后空白的值仍能通过纯数字检查 | **移除 `trim()` / `strip()`**，空白（空格/制表符/换行）一律拒绝；新增 `F7m/F7n/F7o`、`T26m/T26n/T26o` 负向测试 |
| 2 | 清单声明的 `TEST_OUTPUT_20260928.txt` 大小/SHA 与包内实际文件不一致（26,023 / `5b8700…` vs 25,798 / `1d4534…`） | 根因 = git CRLF→LF 换行转换（差值 225 B 恰等于行数，实测影响 7 个文件）。**清单哈希改为按实际分发字节计算并二次自校验** |
| 3 | 平台差异口径仍写「95/96」，应为 macOS 118 / Windows 119 | 已更正；因 v9 新增 9 项检查，本轮实际为 **Windows 128 / macOS 127**、Node **94/94** |

## 关键文件

- `rotation_action_actual.gs` —— 拟部署服务端代码全文 v9
- `rotate_remote_token_client.py` —— 客户端
- `rotation_logic_test.py` —— Python 逻辑测试（Windows **128/128**、macOS 127/127）
- `dispatch_sim_test.js` —— Node 分发仿真（**94/94**，嵌入生产真实 RemoteTrigger.gs + 真实 doPost）
- `_gen_dispatch_sim.py` —— 上项生成器（证明嵌入源码来自真实文件、零手抄）
- `TEST_OUTPUT_20260928.txt` —— 两套测试本机真实执行的完整输出
- `ALL_IN_ONE_20260928.txt` —— 单文件合集（备用）
- `rotation_runbook_20260928.md` —— 操作步骤（**§9.7** 为 v9 新增）

## 复跑

```bash
python rotation_logic_test.py   # 期望 PASS 128/128（Windows）或 127/127（macOS），退出码 0
node dispatch_sim_test.js       # 期望 PASS 94/94，退出码 0（需 Node 18+）
```

## 状态（重要）

- v9 **仍为待审核方案**；审核通过 ≠ 生产授权。
- **修复并复审前不要部署、不要执行轮换。**
- 凭证事件维持 **OPEN**；T1-B B 列修复生产批准数维持 **0**。
- 94/94 分发测试因审核人本机无 Node，**尚未由其独立复现**（已如实标注）。
