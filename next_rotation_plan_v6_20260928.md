# REMOTE_TOKEN 轮换方案 v6（2026-09-28，回应 Tom 第四轮复审 3 条阻断）

> 本包直接附全部文件本体；全部文件零真实令牌、零真实 URL。
> 校验：`certutil -hashfile <文件> SHA256`（Windows）或 `sha256sum <文件>`，与 `DELIVERY_MANIFEST_20260928.md` 逐一对表。

## 0. Tom 第四轮 3 条阻断 → 逐条修订

| # | Tom 意见 | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | `tsRotateRemoteToken` 仅在 `owner` 非空时校验归属；若存在旧版遗留 capability（哈希在、owner 为空），归属检查被跳过 | 改为 **owner 必须存在且严格匹配**：`if (!owner \|\| reqOwner !== owner)` 即拒绝且**不消费**该 capability（不删哈希）。遗留 capability（哈希在、owner 空）⇒ 归属缺失 ⇒ 拒绝 | 服务端 `F6`/`F6b`（真实 gs，遗留 owner 空→拒绝、未消费）；Python `T25`/`T25b` |
| **2** | capability 的 TTL 仅用于"设置时能否覆盖"，轮换**消费时未校验创建时间**；客户端两观稳定旧值仍不能排除延迟请求随后完成轮换 | **消费时强制校验 TTL**：`created && (_nowMs() - created) > ROTATION_CAP_TTL_MS` ⇒ 拒绝、**不改令牌**，并清理过期 capability（免延迟请求复用） | 服务端 `F7`/`F7b`/`F7c`（真实 gs，capability 推到 TTL 之前→`expired` 拒绝、令牌未改）；Python `T26`/`T26b`/`T26c` |
| **3** | Windows ACL 读回函数返回了 `icacls` 退出码，但 `_nt_acl_foreign` 忽略它；读回失败且解析为空可能误判为"仅本用户" | `_nt_acl_principals` 读回**失败（rc≠0）/ 结果为空 / 无法解析** ⇒ 统一 `raise PermissionHardeningError`（失败关闭），绝不因解析为空而冒充"仅本用户"；`restrict_perms` 据此抛出、留不下权限过宽文件 | Python `T24`/`T24b`/`T24c`（读回失败、Windows 分支端到端、rc=0 但空→均失败关闭）；`T22d2`/`T22e` 仍验证正常收紧后读回仅剩本用户 |

**前几轮已修且本轮保持**：处理函数 `return JSON.stringify` 契约；`inflight` 在途标记 + 两次稳定观测终判；写前暂存 escrow；字段对齐 `token`；部署断言读真实枚举产物（缺输入 exit 2）；令牌门严格 mock；去恒真断言；退出码 0/1/2；取消无条件 `force`（owner + TTL + 在途互斥）。

## 1. 关于 86/85 的平台差异（Tom 问到的）

两套测试**逻辑完全等价**，差异仅来自一个 **Windows 专用用例**：

- Windows 运行输出 **86/86**：含 `T22d2 Windows：读回 ACL 核验仅剩本用户`（仅在 `os.name == 'nt'` 时执行，验证 `icacls` 读回 ACL 主体列表仅剩本用户）。
- macOS 运行输出 **85/85**：该用例被平台守卫跳过（macOS 无 `icacls`，无法做 ACL 读回），其余 85 项逐一对齐通过。

即多出那 1 项就是 `T22d2`（ACL 读回核验），非测试口径不一致。若 Tom 希望 macOS 也能覆盖 ACL 读回逻辑，可改为纯字符串解析层的单元测试（与平台无关）——本包已在 `T24`/`T24b`/`T24c` 用 monkeypatch 覆盖 `_nt_acl_principals` 的失败/空/rc=0 三态，跨平台可跑。

## 2. 测试（两套，均可在任意空目录独立跑；exit 0 = 全通过）

- `python rotation_logic_test.py` → **96/96 PASS，exit 0**（缺 `deployment_evidence_20260926.json` → exit 2 且不输出裁决）
- `node dispatch_sim_test.js` → **60/60 PASS，exit 0**（用**生产真实** RemoteTrigger.gs + 真实 doPost + 拟部署处理函数原文仿真；含 F6/F6b/F7/F7b/F7c）

完整原始输出见包内 `TEST_OUTPUT_20260928.txt`（本机真实执行、未删改）。

## 3. 诚实说明（沿用往轮口径）

- 以上 60/60 与 96/96 均为**仿真与静态断言**：分发层用生产分发器真实源码，服务端状态为按其真实行为复刻的 mock / 真实函数体，非 GAS 运行时。
- Node 分发测试此前因 Tom 本机无 Node 未由他独立复现；本轮 60/60 仍为他未复现项，已如实标注。如需要，可改为纯 Python 复刻一份分发层仿真供其本机复跑。
- **v6 仍为待审核方案**；本机 mac 上 85/85、Windows 上 86/86 均为 Rita 侧自测结果。

## 4. 状态（维持未变）

- 凭证事件维持 **OPEN**；T1-B B 列修复生产批准数维持 **0**。
- 本轮**未部署、未执行轮换**；Tom 审核通过 ≠ 生产授权，真实轮换须经 Rita / 生产负责人单独授权。
