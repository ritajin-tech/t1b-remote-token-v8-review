# Tom 交付包 v8 — 交付清单（2026-09-28，回应 Tom 第六轮复审 1 条阻断）

> 目的：回应 Tom 2026-09-28 **第六轮**复审（1 条新阻断：capability 创建时间解析不够严格，`parseInt`/`int(float)` 会接受带后缀/小数/科学记数法的非法值）。
> 第五轮 1 条阻断（创建时间缺失/无效时 TTL 检查被跳过）已在 v7 修复；**本轮在 v7 基础上进一步加严**为"创建时间须为严格正整数时间戳"，v7 的双条件失败关闭**保留并叠加**。
> 第四轮 3 条阻断（遗留 capability 跳过归属检查 / 消费时未校验 TTL / ACL 读回失败未失败关闭）已在 v6 全部修复，v7/v8 均**保留并回归通过**。
> 本机无 Node 导致 60/60 分发测试当时未由你复现 —— 本轮该测试已扩到 **85/85**，仍为你未复现项，已如实标注。
> 本包**直接附全部文件本体**。全部文件零真实令牌、零真实 URL。
> 校验：`certutil -hashfile <文件> SHA256`（Windows）或 `sha256sum <文件>`，与下表逐一比对。

---

## 🔴 上一处笔误已更正（沿用往版说明，供对照）

- 往版清单写的 `d66ca…` 是**侧车文件自身的 SHA-256**，不是侧车的内容。
- **本包侧车实际内容**：
  - `STATE.json.sha256` → `845876f8082eeda3d3d39b3cb85563d2547eaefff082ca2d7b47c2f8326989dc  STATE.json`
  - `STATE.json.sha1`   → `c211bf3aaacebd8cff8a8a1007efa8ec421cee0d  STATE.json`
- 两者均记 CRLF 原字节哈希 `845876f8…` / `c211bf3a…`，与本包 `STATE.json`（82179 B，CRLF）逐字节一致。

---

## 一、Tom 第六轮 1 条新阻断 —— 修订与验证物

| # | Tom 意见（第六轮，复审 v7） | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | 服务端 `parseInt(createdRaw, 10)` 会接受"带字母后缀的有效时间戳"（如 `"1700000000000x"`→`1700000000000`）；Python 测试模型 `int(float(...))` 会接受小数/科学记数法。即"非法格式原始值"仍能被误判为合法正整数，绕过创建时间校验 | 新增 **`_parseStrictPositiveInt(raw, nowMs)`（gs）/ `strict_pos_int(raw, now)`（Python mock）**，在 TTL 判断**之前**严格校验原始值：①仅纯数字串 `/^[0-9]+$/`；②位宽 ≤16；③`>0` 且 `≤ MAX_SAFE_INTEGER`；④**不为未来时间** `≤ nowMs`。任一不满足 ⇒ 返回 `null` ⇒ 拒绝、清理 capability 三键、**不改令牌**。仅"干净正整数且未过期"才允许消费 | 服务端 **F7h/F7i/F7j/F7k**（真实 gs，后缀/小数/科学记数法/未来 → 拒绝、令牌未改、已清理）+ **F7l**（干净正整数 → 允许，正向对照）；Python **T26h/T26i/T26j/T26k**（负向）+ **T26g**（正向对照） |

**前几轮已修且本轮保持**：处理函数 `return JSON.stringify` 契约；`inflight` 在途标记 + 两次稳定观测终判；写前暂存 escrow；字段对齐 `token`；部署断言读真实枚举产物（缺输入 exit 2）；令牌门严格 mock；去恒真断言；退出码 0/1/2；取消无条件 `force`（owner + TTL + 在途互斥）；**owner 必须存在且严格匹配**；**消费时强制 TTL**；**ACL 读回失败关闭**；**v7 的 fail-closed 双条件**（创建时间缺失/0/非数字不跳过 TTL）保留并叠加 v8 最严解析。

## 二、第四轮 3 条阻断（v6 已修，本轮回归通过，供对照）

| # | Tom 意见 | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | `tsRotateRemoteToken` 仅在 `owner` 非空时校验归属；旧版遗留 capability（哈希在、owner 为空）归属检查被跳过 | 改为 **owner 必须存在且严格匹配**：`if (!owner \|\| reqOwner !== owner)` 即拒绝且**不消费**（不删哈希） | 服务端 **F6/F6b**（真实 gs，遗留 owner 空→拒绝、未消费）；Python **T25/T25b** |
| **2** | capability TTL 仅用于"设置时能否覆盖"，轮换**消费时未校验创建时间** | **消费时强制校验 TTL**：`created && (_nowMs() - created) > ROTATION_CAP_TTL_MS` ⇒ 拒绝、**不改令牌**，清理过期 capability | 服务端 **F7/F7b/F7c**（真实 gs，capability 推到 TTL 之前→`expired` 拒绝、令牌未改、已清理）；Python **T26/T26b/T26c** |
| **3** | Windows ACL 读回函数返回了 `icacls` 退出码，但 `_nt_acl_foreign` 忽略它；读回失败且解析为空可能误判为"仅本用户" | `_nt_acl_principals` 读回**失败（rc≠0）/ 结果为空 / 无法解析** ⇒ 统一 `raise PermissionHardeningError`（失败关闭） | Python **T24/T24b/T24c**；**T22d2/T22e** 仍验证正常收紧后读回仅剩本用户 |

## 三、关于 96/95 的平台差异（Tom 问到的 —— 与 v6 同因，非本轮引入）

两套测试**逻辑完全等价**，差异仅来自一个 **Windows 专用用例**：

- Windows 运行输出 **96/96**：含 `T22d2 Windows：读回 ACL 核验仅剩本用户`（仅在 `os.name == 'nt'` 时执行，验证 `icacls` 读回 ACL 主体列表仅剩本用户）。
- macOS 运行输出 **95/95**：该用例被平台守卫跳过（macOS 无 `icacls`，无法做 ACL 读回），其余 95 项逐一对齐通过。

即多出那 1 项就是 `T22d2`（ACL 读回核验），非测试口径不一致。本轮 Python 从 96/96 增到 **119/119**（v7 新增 T26d/T26e/T26f/T26g，v8 再新增 T26h/T26i/T26j/T26k），Node 从 71/71 增到 **85/85**（v8 新增 F7h/F7i/F7j/F7k/F7l），但该平台差仍存在于 `T22d2`，与本轮修订无关。若希望 macOS 也能覆盖 ACL 读回逻辑，可改为纯字符串解析层的单元测试（与平台无关）——本包已在 `T24/T24b/T24c` 用 monkeypatch 覆盖 `_nt_acl_principals` 的失败/空/rc=0 三态，跨平台可跑。

## 四、文件清单（按顺序）

| 文件 | 说明 | 大小 | sha256 |
|---|---|---|---|
| `next_rotation_plan_v8_20260928.md` | 方案 v8（本轮主体：回应 Tom 第六轮 1 条阻断 — capability 创建时间须为严格正整数时间戳，拒绝数字后缀/小数/科学记数法/未来时间） | 4811 B | `831f5f6cd9383d7a64fc114294d8d82e8bb46debca37a66e8fe01571cbce914b` |
| `next_rotation_plan_v7_20260928.md` | 方案 v7（已被 v8 取代，保留供比对；回应 Tom 第五轮 1 条阻断 — capability 创建时间缺失/无效 ⇒ 失败关闭） | 4238 B | `db41874d68ee44dfc7b55c03ae9e63d560147dec5517c090468d66c705b85be5` |
| `rotation_deploy_diff_20260928.patch` | 拟部署代码差异（unified diff，含源文件 SHA-256，已 git apply 实测） | 3586 B | `25ccab0d995f14b0ba2e6016a8b9024eebb8669aae2ddccaf8b0808ca70d1045` |
| `rotation_action_actual.gs` | 拟部署服务端代码全文 v8（创建时间严格正整数解析 _parseStrictPositiveInt；owner 必须存在/消费时 TTL/ACL 读回失败关闭 三项 v6 修订 + v7 双条件失败关闭 均保留并回归通过） | 18100 B | `88b942454ab245cbd29b440244c7c13bed347350a523226af92faa9ebafc3af3` |
| `dispatch_sim_test.js` | 用【真实】RemoteTrigger.gs + 真实 doPost 仿真的 Node 测试（85/85，含 F6/F6b/F7/F7b/F7c/F7d/F7e/F7f/F7g/F7h/F7i/F7j/F7k/F7l） | 50388 B | `54c97a122dc7bba575779183194f59f77836f006621695736eb75d56e7e0121a` |
| `_gen_dispatch_sim.py` | 上项的生成器：证明嵌入源码来自真实文件、零手抄 | 32151 B | `3ca995c83ce087da85344df2051528a417bfc7a0d6a799afa7230b8c2f9f577f` |
| `rotate_remote_token_client.py` | 客户端 v6（v8 服务端改动不要求客户端变更；字段对齐 token + capability 归属/TTL + 在途判定 + 权限收紧 + ACL 读回失败关闭 + 写前暂存） | 26603 B | `e12bcbc1d71f286249c12d92943d730fcde5d0a79a7a3c0ee58d5d883271c05f` |
| `rotation_logic_test.py` | Python 逻辑测试 v8（119/119；含 T26d/T26e/T26f/T26g + T26h/T26i/T26j/T26k 及既有竞态/权限/并发/ACL失败关闭/遗留capability/消费时TTL负向；缺输入 exit 2） | 41433 B | `eba85ad6e08ff5824fb0e381b17b743dcd24c1d5260a0cb9dde22e3d4dee2246` |
| `deployment_evidence_20260926.json` | rotation_logic_test.py 的必需输入（真实只读枚举产物） | 3518 B | `03d63efaedfd8c639a784b3053cb71bc0cbce63504a09476f9d74e123f9b872d` |
| `TEST_OUTPUT_20260928.txt` | 【本轮】两套测试在本机真实执行的完整输出（含 T24/T24b/T24c、T25/T25b、T26/T26b/T26c/T26d/T26e/T26f/T26g/T26h/T26i/T26j/T26k、F6/F6b/F7/F7b/F7c/F7d/F7e/F7f/F7g/F7h/F7i/F7j/F7k/F7l 负向用例行） | 26023 B | `5b870070283cecf5251a317ff6b6f5dbfc3b32ef6e780a0c5137a9a7975fae07` |
| `rotation_runbook_20260928.md` | 操作步骤 v8：含 §9.5 创建时间失败关闭 + §9.6 严格正整数时间戳解析；不暴露令牌，含在途终判/权限/并发/ACL失败关闭处理 | 14411 B | `339f0c38efaad2824fa38233b8552489fc712e5988e87695d586e4e4f1246db5` |
| `next_rotation_plan_v6_20260928.md` | 方案 v6（已被 v7/v8 取代，保留供比对；3 条阻断：遗留capability跳过归属/消费时未校验TTL/ACL读回未失败关闭） | 4445 B | `af80ba9df030cd7342dfbd342d5d6d5694caf828ec3844f1219f68b4eb661b41` |
| `next_rotation_plan_v5_20260928.md` | 方案 v5（已被 v6/v7 取代，保留供比对） | 28926 B | `386191e893e430473bb8f223e477a6fe49489dd89a8db1124466ad3f46cbd9c0` |
| `next_rotation_plan_v4_20260928.md` | 方案 v4（已被 v5/v6/v7 取代，保留供比对） | 27800 B | `41b767f26ecdb2666cef38da770006bb142e10c62f94f4cdb199adf9ade21fe8` |
| `next_rotation_plan_v3_20260927.md` | 方案 v3（已被 v4/v5/v6/v7 取代，保留供比对） | 25894 B | `d64b06b9174e4d1dedb7c0410c054b2c669039cb9b559949e888cbe129a8ecf7` |
| `REMOTE_TOKEN_rotation_audit_20260927.md` | 审计记录全文 | 25986 B | `accce13acecb20aa1293dc4d997407c2263d23e9d501d3ece1cb4aca6f0f52b4` |
| `STATE.json` | T1-B 交付状态本体（CRLF 原字节） | 82179 B | `845876f8082eeda3d3d39b3cb85563d2547eaefff082ca2d7b47c2f8326989dc` |
| `STATE.json.sha256` | 侧车（CRLF 哈希） | 78 B | `d66ca136ae1c1349a0ca8b995b5b1926a123ba07f4b84a75420a581b37046dfe` |
| `STATE.json.sha1` | 侧车（CRLF 哈希） | 53 B | `935584cecee14d07b9c10c2add14a84e45dfbe5662c66d56a5deae48f17eb34a` |

---

## 五、STATE.json 本体与侧车

| 文件 | 大小 | sha256 |
|---|---|---|
| `STATE.json` | 82179 B | `845876f8082eeda3d3d39b3cb85563d2547eaefff082ca2d7b47c2f8326989dc`（CRLF 原字节） |
| `STATE.json.sha256` | 78 B | `d66ca136ae1c1349a0ca8b995b5b1926a123ba07f4b84a75420a581b37046dfe` |
| `STATE.json.sha1` | 53 B | `935584cecee14d07b9c10c2add14a84e45dfbe5662c66d56a5deae48f17eb34a` |

侧车内容（原文）：`845876f8082eeda3d3d39b3cb85563d2547eaefff082ca2d7b47c2f8326989dc  STATE.json` ／ `c211bf3aaacebd8cff8a8a1007efa8ec421cee0d  STATE.json`

---

## 六、测试输出（Tom 要求"提交对应负向测试和测试输出"）

`TEST_OUTPUT_20260928.txt` 为本机真实执行的两份原始输出（未删改），含本轮新增负向用例行：

- Python 侧：`T22d2/T22e` Windows 读回 ACL 仅剩本用户｜`T24` ACL 读回失败（rc≠0/空）→ 抛 `PermissionHardeningError`｜`T24b` `restrict_perms`（Windows 分支）遇 ACL 读回失败→抛错｜`T24c` 读回 rc=0 但结果为空→失败关闭｜`T25/T25b` 遗留 capability（owner 空）→ 拒绝、未消费｜`T26/T26b/T26c` 延迟请求 capability 已过期→拒绝（`expired`）、令牌未改、已清理｜`T26d` 创建时间缺失→拒绝、令牌未改、capability 已清理｜`T26e` 创建时间 `'0'`→拒绝｜`T26f` 创建时间 `'abc'`→拒绝｜`T26g` 创建时间有效且未过期→允许轮换（正向对照）｜**`T26h` 创建时间带数字后缀 `1700000000000x`→拒绝**｜**`T26i` 创建时间为小数 `123.456`→拒绝**｜**`T26j` 创建时间为科学记数法 `1.7e12`→拒绝**｜**`T26k` 创建时间为未来时间戳→拒绝**（以上均令牌未改、capability 已清理）。
- Node 侧：`E5c` 缺 owner_id 拒｜`E5e/E5f` 他人 capability 拒且不改原值｜`F1/F1b` 在途拒设｜`F2/F2b` 在途拒第二个轮换｜`F3/F3b/F3c` owner 不匹配不消费｜`F6/F6b` 遗留 owner 空→拒绝、未消费｜`F7/F7b/F7c` 消费时 TTL 过期→拒绝、令牌未改、已清理｜`F7d` 创建时间缺失→拒绝、令牌未改、已清理｜`F7e` 创建时间 `'0'`→拒绝｜`F7f` 创建时间 `'abc'`→拒绝｜`F7g` 创建时间有效且未过期→允许轮换（正向对照）｜**`F7h` 创建时间带数字后缀 `1700000000000x`→拒绝**｜**`F7i` 创建时间为小数 `123.456`→拒绝**｜**`F7j` 创建时间为科学记数法 `1.7e12`→拒绝**｜**`F7k` 创建时间为未来时间戳 `9999999999999`→拒绝**｜**`F7l` 干净正整数 `3000000`→允许轮换（正向对照）**（以上负向均令牌未改、capability 已清理）。

## 七、Tom 独立复跑指引（两套测试，均可在任意空目录运行）

```bash
# 1) 用真实分发源码的分发仿真（需要 node 18+）
node dispatch_sim_test.js          # 期望：PASS 85 / 85，退出码 0（需 Node 18+）

# 2) 逻辑层仿真（需要 python 3）
python rotation_logic_test.py      # 期望：PASS 119 / 119，退出码 0
                                   # 缺 deployment_evidence_20260926.json → 退出码 2 且不输出裁决
```

代码差异核验：
```bash
mkdir -p chk/ts-manager && cp <你的 RemoteActions.gs> chk/ts-manager/RemoteActions.gs
cd chk && git init -q . && git apply --check -p1 ../rotation_deploy_diff_20260928.patch
```

---

## 八、状态（维持未变）

- 凭证事件维持 **OPEN**：T2 曾现于 URL 查询串、Google 服务端日志可见性未证伪；须待方案 §5/§6/§7 核验通过方可降级。
- T1-B B 列修复批准数维持 **0**；本包不涉及 T1-B 修复。
- **v8 仍为待审核方案**。Tom 审核通过 ≠ 生产授权；真实轮换须经 Rita / 生产负责人单独授权。
- 119/119 与 85/85 均为 Rita 侧自测结果；**85/85 因你本机无 Node，尚未由你独立复现**。
