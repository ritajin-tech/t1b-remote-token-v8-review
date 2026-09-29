# Tom 交付包 v9.1 — 交付清单（2026-09-28，v9 代码已过审 + 回应 Tom 第八轮交付修正）

> **代码版本仍为 v9，未改动**：Tom 第八轮已复审通过（针对 v9 修订范围）。本版仅修正**交付/文档**问题。
> **本轮追加（v9.1 addendum）**：新增纯 Python 分发仿真 `dispatch_sim_py.py`（94/94），**无需 Node**，Tom 可在 macOS 直接复跑 —— 补上"无 Node 环境下的分发用例运行入口"。其定位为**补充测试 / 语义复刻**：按真实源码逻辑逐行镜像分发器与 3 个处理函数，用例名/编号与 `dispatch_sim_test.js` 对齐，但**不在 JavaScript 运行时执行真实分发器**，故不等同于 Node 测试的完全等价替代（Tom v9.2 复审明确）。生成器 `_gen_dispatch_sim_py.py` 一并随包分发，含 `self_check()`（**25 条**静态断言，测试开始时执行一次，对嵌入源码做关键片段断言防漂移，非完整字节哈希）。
> v9.1 修正（Tom 第八轮）：交付说明引用了 `python _build_manifest.py verify`，但该脚本**未随包分发**，
> 且其原实现还依赖一份**不随包分发**的本地台账 `_manifest_hashes.json`，故无法按指引复跑。
> 现：`_build_manifest.py` **已随包分发并在下表声明哈希**；`verify` 改为**离线自包含**
> （直接解析包内本清单取声明值，与同目录实际文件逐字节比对，无需网络、无需任何包外文件）。
>
> 目的：回应 Tom 2026-09-28 **第七轮**复审（v8 未通过，3 项待修正：① `trim()` 使带空白的值仍能通过纯数字检查；② 清单声明的 `TEST_OUTPUT_20260928.txt` 大小/SHA 与包内实际文件不一致；③ 平台差异口径仍写「95/96」）。
> 三项均已修正：**移除 `trim()`**（空白前缀/尾随/制表符换行一律拒绝）、**清单哈希改为按实际分发字节计算并二次自校验**、**平台口径更新为 Windows 128 / macOS 127**。
> 前几轮阻断（v6 三项 / v7 双条件失败关闭 / v8 严格正整数解析）均**保留并回归通过**。
> Node 测试已扩到 **94/94**。本轮**新增纯 Python 分发仿真 `dispatch_sim_py.py`（94/94）**，**无需 Node** —— Tom 可在 macOS 直接 `python3 dispatch_sim_py.py` 复跑这 94 个分发用例。其定位为**补充测试 / 语义复刻**（用例名/编号与 `dispatch_sim_test.js` 对齐，但属 Python 对真实逻辑的镜像，**非 JavaScript 运行时执行真实分发器**），故作为"无 Node 环境下的运行入口"补充证据，不视为 Node 测试的完全等价替代。
> 校验：`sha256sum <文件>`（Windows 用 `certutil -hashfile <文件> SHA256`），与下表逐一比对。

## 🔴 哈希口径（针对第七轮第 2 项，务必先读）

- 往版清单直接对**本地文件**算 SHA-256。但 git 提交时会做 **CRLF→LF 换行转换**，导致"仓库实际分发的字节"与本地不同 —— 例如 `TEST_OUTPUT_20260928.txt` 本地 26,023 B / `5b8700…`，仓库实际分发 25,798 B / `1d4534…`，**差值 225 B 恰等于该文件行数**。实测同类偏差共影响 **7 个文件**。
- **本版修正**：下表的大小与 SHA-256 **一律按仓库实际分发字节计算**，而非本地字节；生成后再次抓取逐文件比对做**自校验**。
- **字节来源必须是 GitHub Contents API（权威 blob），不能用 raw 抓取**：本轮实测 raw.githubusercontent.com 存在 CDN 缓存，
  推送后仍返回**旧版本**字节（`_build_manifest.py` 的 API 权威值 22,835 B，raw 却仍给 21,259 B）。
  若用 raw 生成清单，声明值会再次与实际分发不一致 —— 等于重犯上一轮那个问题。故本包改用 API 取权威 blob，raw 仅作兜底。
- 清单**不声明自身哈希**（避免自引用）；`ALL_IN_ONE_20260928.txt` 的哈希按其分发字节声明并已自校验。
- 交付主体为本仓库；`ALL_IN_ONE_*.txt` 为单文件合集备用。
- **一键核验（离线）**：`python _build_manifest.py verify` —— 脚本已在包内；它解析本清单的声明值并与同目录文件逐字节比对，输出逐行 PASS/FAIL，全部一致时退出码 0、任一不符退出码 1。**不需要网络，也不需要任何包外文件**（`--net` 可选，改为抓取仓库 raw 字节比对）。
- **换行形态**：清单声明的是**仓库存储字节（LF）**。经 GitHub「Download ZIP」下载即为 LF，核验直接 `PASS`；
  若在 Windows 上用 `git clone` 检出（默认 `core.autocrlf=true` 会转成 CRLF，字节数 += 行数），脚本会再按 CRLF→LF 归一比对一次，
  命中则显示 `PASS(LF归一)` 并给出说明。两种形态都视为一致，但**不会静默兜底**：若归一后仍不符，即为 `FAIL`。

---

## 一、Tom 第七轮 3 项修正 —— 修订与验证物

| # | Tom 意见（第七轮，复审 v8） | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | `_parseStrictPositiveInt` / `strict_pos_int` 在校验前先 `trim()`，带前后空白的值仍会通过纯数字检查。请确认是否允许该格式；若要求严格纯数字，请移除 `trim()` 并增加空白前缀、后缀的负向测试 | **确认：不允许该格式**。已**移除 `trim()`（gs）/ `strip()`（Python）**。理由：创建时间由本系统以 `String(Date.now())` 写入，永不含空白；trim 属不必要宽容，会让被篡改/污染的值静默通过。现任何空白（空格/制表符/换行）均使 `/^[0-9]+$/` 校验失败 ⇒ 拒绝、清理 capability、**不改令牌**。拒绝提示同步改为"不含符号/小数/指数/后缀/**空白**" | 服务端 **F7m/F7n/F7o**（前导空白/尾随空白/制表符换行 → 拒绝、令牌未改、已清理）；Python **T26m/T26n/T26o**；正向对照 **F7l/T26g**（干净正整数→允许） |
| **2** | 清单声明 `TEST_OUTPUT_20260928.txt` 为 26,023 B / `5b8700…`，包内实际为 25,798 B / `1d4534…` | 根因=git CRLF→LF 换行转换（非文件内容问题）。**清单哈希改为按实际分发字节计算 + 二次自校验**；同时把口径写进本清单顶部 | 见上方「哈希口径」；`python _build_manifest.py verify`（离线、脚本在包内）逐文件 PASS |
| **2b**（第八轮） | 交付说明引用 `python _build_manifest.py verify`，但该脚本不在包内，无法按指引复跑 | 脚本**已随包分发**（并在下表声明哈希）；且 `verify` 原依赖包外台账 `_manifest_hashes.json`，已改为**离线自包含**：直接解析包内清单取声明值、比对同目录文件 | 在包目录内执行 `python _build_manifest.py verify` 即可复跑；无需网络 |
| **3** | 说明仍写「95/96」的平台差异，本轮应为 macOS 118 / Windows 119 | 已全量更正；因 v9 新增 9 项检查，本轮实际为 **Windows 128 / macOS 127**、Node **94/94** | 见 §三；`rotation_runbook_20260928.md` §9.7 |

**负向测试基线设计（供复核）**：空白用例的时间戳基线刻意取「若被 trim 则恰好合法且未过期」的值（如 `" 4000000"` @ clock 4000000）。若代码中仍存在 `trim()`，这些用例会**失败**——因此它们能真正证明 trim 已被移除，而非只是"恰好被未来时间戳规则拒掉"。

**前几轮已修且本轮保持**：处理函数 `return JSON.stringify` 契约；`inflight` 在途标记 + 两次稳定观测终判；写前暂存 escrow；字段对齐 `token`；部署断言读真实枚举产物（缺输入 exit 2）；令牌门严格 mock；去恒真断言；退出码 0/1/2；取消无条件 `force`（owner + TTL + 在途互斥）；**owner 必须存在且严格匹配**；**消费时强制 TTL**；**ACL 读回失败关闭**；**v7 fail-closed 双条件**；**v8 严格正整数解析**。

## 二、v6 三项阻断（v6 已修，本轮回归通过，供对照）

| # | Tom 意见 | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | 遗留 capability（哈希在、owner 空）归属检查被跳过 | **owner 必须存在且严格匹配**：`if (!owner \|\| reqOwner !== owner)` 拒绝且**不消费** | 服务端 **F6/F6b**；Python **T25/T25b** |
| **2** | capability TTL 仅用于"设置时能否覆盖"，消费时未校验 | **消费时强制校验 TTL** ⇒ 拒绝、**不改令牌**、清理 | 服务端 **F7/F7b/F7c**；Python **T26/T26b/T26c** |
| **3** | Windows ACL 读回失败且解析为空可能误判为"仅本用户" | 读回失败(rc≠0)/空/无法解析 ⇒ 统一 `raise PermissionHardeningError` | Python **T24/T24b/T24c**；**T22d2/T22e** |

## 三、平台差异（Windows 128 / macOS 127 —— 第七轮第 3 项口径更正）

两套测试**逻辑完全等价**，差异仅来自一个 **Windows 专用用例**：

- **Windows：128/128** —— 含 `T22d2 Windows：读回 ACL 核验仅剩本用户`（仅 `os.name == 'nt'` 时执行，验证 `icacls` 读回 ACL 主体列表仅剩本用户）。
- **macOS：127/127** —— 该用例被平台守卫跳过（macOS 无 `icacls`），其余 127 项逐一对齐通过。

即多出的 1 项就是 `T22d2`，**非测试口径不一致**。历史沿革：v6 为 96/95，v7 为 107/106，v8 为 **119/118**（与 Tom 第七轮实测的 macOS 118 一致），**v9 因新增 9 项空白负向检查而变为 128/127**。若希望 macOS 也能覆盖 ACL 读回逻辑，可改为纯字符串解析层单元测试（与平台无关）——本包已在 `T24/T24b/T24c` 用 monkeypatch 覆盖 `_nt_acl_principals` 的失败/空/rc=0 三态，跨平台可跑。

## 四、文件清单（按顺序；大小与 SHA-256 均为实际分发字节）

| 文件 | 说明 | 大小 | sha256 |
|---|---|---|---|
| `next_rotation_plan_v9_20260928.md` | 方案 v9（本轮主体：回应 Tom 第七轮 3 项修正 — 移除 trim 拒绝空白 / 清单哈希按分发字节重算 / 平台口径更正） | 7635 B | `9d99d3c218463155d788264a9273a0f99d9e846495193939c837990b7dc51dec` |
| `next_rotation_plan_v8_20260928.md` | 方案 v8（已被 v9 取代，保留供比对；回应 Tom 第六轮 1 条阻断 — 创建时间须为严格正整数时间戳） | 4811 B | `831f5f6cd9383d7a64fc114294d8d82e8bb46debca37a66e8fe01571cbce914b` |
| `next_rotation_plan_v7_20260928.md` | 方案 v7（已被 v8/v9 取代，保留供比对；创建时间缺失/无效 ⇒ 失败关闭） | 4238 B | `db41874d68ee44dfc7b55c03ae9e63d560147dec5517c090468d66c705b85be5` |
| `rotation_deploy_diff_20260928.patch` | 拟部署代码差异（unified diff，含源文件 SHA-256，已 git apply 实测） | 3586 B | `25ccab0d995f14b0ba2e6016a8b9024eebb8669aae2ddccaf8b0808ca70d1045` |
| `rotation_action_actual.gs` | 拟部署服务端代码全文 v9（v8 严格正整数解析 + v9 移除 trim：空白前后缀一律拒绝；v6 三项 + v7 双条件 均保留并回归通过） | 18273 B | `fa05d7537ce1f56fb43d29b4ea286495285f2c291a292e177c4f18f40dd1b488` |
| `dispatch_sim_test.js` | 用【真实】RemoteTrigger.gs + 真实 doPost 仿真的 Node 测试（94/94，含 F6/F6b/F7/F7b–F7l 及 v9 新增 F7m/F7n/F7o 空白负向） | 53244 B | `10640342ed1ed826d2df1dc7709258ee214d7c0e0fc75b58640532aa4faad797` |
| `_gen_dispatch_sim.py` | 上项的生成器：证明嵌入源码来自真实文件、零手抄 | 39036 B | `dc3d1f1537ff1c50c70c79890d54f46efca83776d51424750aa3fd826cf29bcb` |
| `dispatch_sim_py.py` | 纯 Python 语义复刻的分发层仿真（94/94，用例名/编号与 dispatch_sim_test.js 对齐；无 Node 依赖，Tom 可在 macOS 直接 `python3 dispatch_sim_py.py` 复跑；属【补充测试】，非 JavaScript 运行时执行真实分发器）。self_check() 25 条静态断言（测试开始时调用一次，对嵌入源码做关键片段断言防漂移） | 58838 B | `e6773b725269309ec2c562f69ecace4ec42bc4b3d988d130ca445aa34e19d96a` |
| `_gen_dispatch_sim_py.py` | 上项的生成器：证明嵌入的 dss_RemoteTrigger.js / doPost / 3 个处理函数均来自真实文件、零手抄；self_check() 25 条源码静态断言（测试开始时执行一次，片段断言，漂移即 exit 2） | 45238 B | `e66139a2f0744068e0b02481d178c16896921c6965d358408576fab7177a0706` |
| `rotate_remote_token_client.py` | 客户端 v6（v9 服务端改动不要求客户端变更；字段对齐 token + capability 归属/TTL + 在途判定 + 权限收紧 + ACL 读回失败关闭 + 写前暂存） | 26064 B | `fea761d82aa70973d10ccf597d1250aa6cd211bc60555c777480d5db7f5ea8a2` |
| `rotation_logic_test.py` | Python 逻辑测试 v9（Windows 128/128、macOS 127/127；含 T26d–T26k 及 v9 新增 T26m/T26n/T26o 空白负向；缺输入 exit 2） | 43497 B | `a28253aa7e12002b821da7421046a90afd08ed4824b6f37bbc1133ad1c6db429` |
| `deployment_evidence_20260926.json` | rotation_logic_test.py 的必需输入（真实只读枚举产物） | 3394 B | `97e59318bf71ea16bd71a3b907eae88b79f9c8d61c6093b5e65371d8de424788` |
| `TEST_OUTPUT_20260928.txt` | 【本轮】两套测试在本机真实执行的完整输出（含 T24–T26k 及 v9 新增 T26m/n/o；F6–F7l 及 v9 新增 F7m/n/o 负向用例行） | 28189 B | `d2b9390581cbf1747c5862ff1d68aaccaec05445723a4ddef66a1cbbe3853fad` |
| `rotation_runbook_20260928.md` | 操作步骤 v9：含 §9.5 创建时间失败关闭 + §9.6 严格正整数时间戳 + §9.7 移除 trim 拒绝空白；不暴露令牌 | 16364 B | `b7b6bc660f53911e3a28687490e4d86f9fcb355fea860b0bf9de149f79174f56` |
| `next_rotation_plan_v6_20260928.md` | 方案 v6（已被 v7/v8/v9 取代，保留供比对；3 条阻断：遗留capability跳过归属/消费时未校验TTL/ACL读回未失败关闭） | 4445 B | `af80ba9df030cd7342dfbd342d5d6d5694caf828ec3844f1219f68b4eb661b41` |
| `next_rotation_plan_v5_20260928.md` | 方案 v5（已被 v6/v7/v8 取代，保留供比对） | 28926 B | `386191e893e430473bb8f223e477a6fe49489dd89a8db1124466ad3f46cbd9c0` |
| `next_rotation_plan_v4_20260928.md` | 方案 v4（已被 v5/v6/v7 取代，保留供比对） | 27800 B | `41b767f26ecdb2666cef38da770006bb142e10c62f94f4cdb199adf9ade21fe8` |
| `next_rotation_plan_v3_20260927.md` | 方案 v3（已被 v4/v5/v6/v7 取代，保留供比对） | 25894 B | `d64b06b9174e4d1dedb7c0410c054b2c669039cb9b559949e888cbe129a8ecf7` |
| `REMOTE_TOKEN_rotation_audit_20260927.md` | 审计记录全文 | 25986 B | `accce13acecb20aa1293dc4d997407c2263d23e9d501d3ece1cb4aca6f0f52b4` |
| `STATE.json` | T1-B 交付状态本体 | 81235 B | `a99977c83f04afdf4a1edaf4f1baaa392fb874a84baf674d6dec31bf2af14f42` |
| `STATE.json.sha256` | 侧车（哈希内容） | 77 B | `373fc436b83d1889ac7b18a29b0b4b88147aeaf2c06332f566d06643628a2a1b` |
| `STATE.json.sha1` | 侧车（哈希内容） | 53 B | `935584cecee14d07b9c10c2add14a84e45dfbe5662c66d56a5deae48f17eb34a` |
| `_build_manifest.py` | 清单构建/核验脚本（v9.1 起随包分发，回应 Tom 第八轮：说明引用的脚本必须在包内；`verify` 为离线自包含，直接解析本清单与同目录文件比对，无需网络/包外文件） | 29239 B | `288fe16a76f38ae0ec20acb1b90e290ae116c59c2d25234d4f92d7595b6cd1ef` |
| `ALL_IN_ONE_20260928.txt` | 单文件合集（备用，内容=上表文件按序拼接） | 582613 B | `54b0e045647780955ceeafa48062b3aa8cb9a5056fef3c0e33509d9bdee25661` |

---

## 五、STATE.json 本体与侧车

| 文件 | 大小 | sha256 |
|---|---|---|
| `STATE.json` | 81235 B | `a99977c83f04afdf4a1edaf4f1baaa392fb874a84baf674d6dec31bf2af14f42` |
| `STATE.json.sha256` | 77 B | `373fc436b83d1889ac7b18a29b0b4b88147aeaf2c06332f566d06643628a2a1b` |
| `STATE.json.sha1` | 53 B | `935584cecee14d07b9c10c2add14a84e45dfbe5662c66d56a5deae48f17eb34a` |

侧车内容（原文）：`845876f8082eeda3d3d39b3cb85563d2547eaefff082ca2d7b47c2f8326989dc  STATE.json` ／ `c211bf3aaacebd8cff8a8a1007efa8ec421cee0d  STATE.json`

---

## 六、测试输出（Tom 要求"提交对应负向测试和测试输出"）

`TEST_OUTPUT_20260928.txt` 为本机真实执行的两份原始输出（未删改），含本轮新增负向用例行：

- Python 侧：`T22d2/T22e` Windows 读回 ACL 仅剩本用户｜`T24/T24b/T24c` ACL 读回失败/空/rc=0 → 失败关闭｜`T25/T25b` 遗留 capability（owner 空）→ 拒绝、未消费｜`T26/T26b/T26c` 过期→拒绝（`expired`）、令牌未改、已清理｜`T26d/T26e/T26f` 创建时间缺失/`'0'`/`'abc'`→拒绝｜`T26g` 有效未过期→允许（正向对照）｜`T26h/T26i/T26j/T26k` 数字后缀/小数/科学记数法/未来时间→拒绝｜**`T26m` 前导空白→拒绝｜`T26n` 尾随空白→拒绝｜`T26o` 制表符/换行包裹→拒绝**（负向均令牌未改、capability 已清理）。
- Node 侧：`E5c` 缺 owner_id 拒｜`E5e/E5f` 他人 capability 拒且不改原值｜`F1/F1b` 在途拒设｜`F2/F2b` 在途拒第二个轮换｜`F3/F3b/F3c` owner 不匹配不消费｜`F6/F6b` 遗留 owner 空→拒绝、未消费｜`F7/F7b/F7c` 消费时 TTL 过期→拒绝、令牌未改、已清理｜`F7d/F7e/F7f` 创建时间缺失/`'0'`/`'abc'`→拒绝｜`F7g` 正向对照｜`F7h/F7i/F7j/F7k` 后缀/小数/科学记数法/未来→拒绝｜`F7l` 干净正整数→允许｜**`F7m` 前导空白→拒绝｜`F7n` 尾随空白→拒绝｜`F7o` 制表符/换行→拒绝**。

## 七、Tom 独立复跑指引（两套测试，均可在任意空目录运行）

```bash
# 1) 用真实分发源码的分发仿真（需要 node 18+）
node dispatch_sim_test.js          # 期望：PASS 94 / 94，退出码 0

# 1b) 纯 Python 分发仿真（无需 node，macOS 直接可跑）
python3 dispatch_sim_py.py        # 期望：PASS 94 / 94，退出码 0（self_check：25 条静态断言，测试开始时执行一次，对嵌入源码做关键片段断言防漂移）

# 2) 逻辑层仿真（需要 python 3）
python rotation_logic_test.py      # 期望：PASS 128 / 128（Windows）或 127 / 127（macOS），退出码 0
                                   # 缺 deployment_evidence_20260926.json → 退出码 2 且不输出裁决

# 3) 清单哈希一键核验（离线，脚本在包内；不需要网络、不需要包外文件）
python _build_manifest.py verify            # 期望：逐行 PASS，末行 VERIFY: ALL PASS，退出码 0
python _build_manifest.py verify --dir DIR  # 指定交付目录（在别的目录跑脚本时用）
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
- **v9 仍为待审核方案**。Tom 审核通过 ≠ 生产授权；真实轮换须经 Rita / 生产负责人单独授权。
- 128/128（Windows）与 94/94（Node）均为 Rita 侧自测结果；**94/94 现已可由 Tom 在 macOS 用纯 Python 仿真 `dispatch_sim_py.py` 复现（无需 Node）**。`dispatch_sim_py.py` 为**补充测试 / 语义复刻**（非 JavaScript 运行时），定位见本清单顶部与 §九。

---

## 九、v9.2 复审记录（Tom，2026-09-29）

**结论**：v9.2 的清单核验与 Python 仿真在本机通过；该仿真**定位为补充测试**（语义复刻、非 JS 运行时），**不视为 Node 测试的完全等价替代**；v9 代码修订范围的复审结论不变。**不构成生产轮换授权、不构成 T1-B B 列修复授权；T1-B 生产写入批准数仍为 0。**

Tom 本机复核：`python3 _build_manifest.py verify` → 24/24 PASS；`python3 dispatch_sim_py.py` → 94/94 PASS；`python3 rotation_logic_test.py` → 127/127 PASS。本机无 Node，未独立运行 `dispatch_sim_test.js`。

**两点文案/材料修正（已落实于本清单 v9.2.1）：**
1. `self_check()` 实为 **25 条**静态断言（此前称 23 条有误）；在**测试开始时调用一次**（非每个用例分别执行）；检查方式是对**嵌入源码文本做关键片段断言**，**非完整字节哈希验证**。
2. Python 仿真与 Node fixture 的**过期时间错误提示曾存在一字之差**：Python 仿真提示含"空白"（与 v9 服务端 `rotation_action_actual.gs` 第 197 行一致）；而旧版 Node fixture 内嵌处理函数快照（第 310 行）缺"空白"——属**已知滞后**。该差异已于 **v9.2.2 消除**：Node fixture 已从当前 v9 服务端源码重新生成，`dispatch_sim_test.js` 内嵌处理函数现与 v9 服务端、`dispatch_sim_py.py` 逐字一致（第 310 行已含"空白"）。两版对全部 94 用例的**结构化结果始终完全一致**（断言仅校验 `ok`/`expired`/`令牌未改`/`capability 已清理`，从不依赖错误字符串原文）。

**已落实（v9.2.2）**：Node fixture 已从当前 v9 服务端源码重新生成，过期提示现已含"空白"，两套测试材料逐字一致；v9.2.2 仅替换 `dispatch_sim_test.js` 并重算清单哈希，无任何代码/逻辑变更。

## 十、v9.2.2 收尾（自主，2026-09-29）

- 触发：v9.2.1 复审已闭环（无新阻断、全链闭环），其中登记的「空白」文本差属 Node fixture 早于 v9 措辞的滞后；按用户授权做可选收尾。
- 动作：运行 `_gen_dispatch_sim.py`（实时读取当前 `rotation_action_actual.gs`）重新生成 `dispatch_sim_test.js`，使其内嵌处理函数与 v9 服务端、`dispatch_sim_py.py` 逐字一致（第 310 行过期提示已含"空白"）。
- 验证：在本机用 Node 18+ 实跑重生成后的 `dispatch_sim_test.js` → **PASS 94 / 94，退出码 0**（与旧版结构化结果完全一致，仅文本对齐）。
- 本包（v9.2.2）仅替换 `dispatch_sim_test.js` 并重算清单哈希；**无任何代码逻辑变更、无新授权需求**。
- 治理红线维持不变：Tom 复审 ≠ 生产授权；T1-B B 列生产写入批准数仍为 **0**；凭证事件仍为 **OPEN**；本包不部署、不执行真实轮换。
- 后续唯一外部依赖：仍须由 Rita / 生产负责人**单独授权**真实 REMOTE_TOKEN 轮换（与本次评审无关的独立治理闸门）。
