# REMOTE_TOKEN 轮换方案 v7（2026-09-28，回应 Tom 第五轮复审 1 条阻断）

> 本包直接附全部文件本体；全部文件零真实令牌、零真实 URL。
> 校验：`certutil -hashfile <文件> SHA256`（Windows）或 `sha256sum <文件>`，与 `DELIVERY_MANIFEST_20260928.md` 逐一对表。

## 0. Tom 第五轮 1 条阻断 → 修订

| # | Tom 意见（第五轮，复审 v6） | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | `tsRotateRemoteToken` 仅在 `if (created)` 成立时校验 TTL；若 capability 哈希+owner 都在、但创建时间**缺失 / 为 0 / 非数字 / 无法解析**，`created` 为 0/NaN ⇒ TTL 检查被**完全跳过**，一个延迟到达的请求仍可能通过 nonce 校验完成轮换 | 改为 **fail-closed 双条件**：`if (!(created > 0) || (_nowMs() - created) > ROTATION_CAP_TTL_MS)` ⇒ 拒绝、**不改令牌**，并清理 capability 三键；只有 `created` 是**正整数且未过期**才允许消费 | 服务端 **F7d/F7e/F7f**（真实 gs，缺失/`0`/`abc` → 拒绝、令牌未改、已清理）+ **F7g**（有效+未过期→允许，正向对照）；Python **T26d/T26e/T26f**（负向）+ **T26g**（正向对照） |

**前几轮已修且本轮保持**：处理函数 `return JSON.stringify` 契约；`inflight` 在途标记 + 两次稳定观测终判；写前暂存 escrow；字段对齐 `token`；部署断言读真实枚举产物（缺输入 exit 2）；令牌门严格 mock；去恒真断言；退出码 0/1/2；取消无条件 `force`（owner + TTL + 在途互斥）；**v6 三处实质改动（owner 必须存在且严格匹配 / 消费时 TTL 强制校验 / ACL 读回失败关闭）全部保留并通过本轮回归**。

## 1. 为什么 95/95 与 96/96 的 1 项差异仍来自平台专用用例

本轮 Python 套件从 96/96 增到 **107/107**（新增 T26d/T26e/T26f 负向 + T26g 正向对照，外加若干既有用例微调），但 Tom 看到的 macOS **95/95** 与 Windows **96/96** 之间依旧差 1 项，原因**与 v6 完全相同**，并非本轮引入：

- Windows 运行输出 **96/96**：含 `T22d2 Windows：读回 ACL 核验仅剩本用户`（仅在 `os.name == 'nt'` 时执行，验证 `icacls` 读回 ACL 主体列表仅剩本用户）。
- macOS 运行输出 **95/95**：该用例被平台守卫跳过（macOS 无 `icacls`，无法做 ACL 读回），其余 95 项逐一对齐通过。

即多出那 1 项就是 `T22d2`（ACL 读回核验），非测试口径不一致。若希望 macOS 也能覆盖 ACL 读回逻辑，可改为纯字符串解析层的单元测试（与平台无关）——本包已在 `T24/T24b/T24c` 用 monkeypatch 覆盖 `_nt_acl_principals` 的失败/空/rc=0 三态，跨平台可跑。

## 2. 测试（两套，均可在任意空目录独立跑；exit 0 = 全通过）

- `python rotation_logic_test.py` → **107/107 PASS，exit 0**（缺 `deployment_evidence_20260926.json` → exit 2 且不输出裁决）
- `node dispatch_sim_test.js` → **71/71 PASS，exit 0**（用**生产真实** RemoteTrigger.gs + 真实 doPost + 拟部署处理函数原文仿真；含 F6/F6b/F7/F7b/F7c/F7d/F7e/F7f/F7g）

完整原始输出见包内 `TEST_OUTPUT_20260928.txt`（本机真实执行、未删改）。

## 3. 诚实说明（沿用往轮口径，本轮回首即声明）

- 以上 107/107 与 71/71 均为**仿真与静态断言**：分发层用生产分发器真实源码，服务端状态为按其真实行为复刻的 mock / 真实函数体，非 GAS 运行时。
- Node 分发测试此前因 Tom 本机无 Node 未由他独立复现；本轮 71/71 仍为他**未复现项**，已如实标注。如需要，可改为纯 Python 复刻一份分发层仿真供其本机复跑。
- **v7 仍为待审核方案**；本机 mac 上 95/95、Windows 上 96/96 均为 Rita 侧自测结果（Tom 所见口径）。
- 95/95 与 96/96 的 1 项差异来自平台专用用例 `T22d2`，非本轮回归引入（详见 §1）。

## 4. 状态（维持未变）

- 凭证事件维持 **OPEN**；T1-B B 列修复生产批准数维持 **0**。
- 本轮**未部署、未执行轮换**；Tom 审核通过 ≠ 生产授权，真实轮换须经 Rita / 生产负责人单独授权。
- 本意见不构成凭证轮换授权。
