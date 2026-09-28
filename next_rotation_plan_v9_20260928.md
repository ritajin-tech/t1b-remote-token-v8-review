# T1-B REMOTE_TOKEN 轮换 方案 v9（2026-09-28）
## 回应 Tom **第七轮**复审（复审 v8）：v8 未通过，3 项待修正

> 治理前提（不变）：Tom 复审通过 ≠ 生产授权；**修复并复审前不部署、不执行轮换**；
> 凭证事件维持 **OPEN**；T1-B B 列修复生产批准数维持 **0**。

---

## 一、Tom 第七轮意见逐条对应

| # | Tom 意见（第七轮，复审 v8） | 本方案处置 | 验证物 |
|---|---|---|---|
| **1** | `_parseStrictPositiveInt` / `strict_pos_int` 在校验前先 `trim()`，因此**带前后空白的值仍会通过纯数字检查**。要求确认是否允许该格式；若要求原始值严格为纯数字，请**移除 trim() 并增加空白前缀、后缀的负向测试** | **确认：不允许该格式**，已**移除 `trim()`（gs）/ `strip()`（Python）**。理由：创建时间由本系统以 `String(Date.now())` 写入，永不含空白；trim 属不必要宽容，会让被篡改/污染的值静默通过。现在任何空白（空格/制表符/换行）都使 `/^[0-9]+$/` 校验失败 ⇒ 拒绝、清理 capability、**不改令牌**。新增空白前缀/尾随/制表符换行三类负向测试；基线刻意取"若被 trim 则恰好合法且未过期"的时间戳，以真正证明 trim 必须移除 | 服务端 `F7m/F7n/F7o`；Python `T26m/T26n/T26o`；正向对照 `F7l/T26g` |
| **2** | 清单声明 `TEST_OUTPUT_20260928.txt` 为 26,023 B / SHA `5b8700…`，但包内实际为 25,798 B / SHA `1d4534…`，要求更正清单或重交匹配文件 | **根因已定位并修复**：不是文件内容问题，而是 **git 提交时 CRLF→LF 的换行转换** —— 清单按本地 CRLF 字节算哈希，而 Tom 从仓库下载到的是 LF 字节（差值 225 B 恰等于该文件行数）。**影响不止这一个文件**：实测 7 个文件存在同类偏差。已改为**清单哈希一律按"实际分发字节"（从仓库 raw 抓取）计算，并在生成后二次抓取逐文件自校验**，杜绝本地/分发字节不一致 | 见本文档 §三；`DELIVERY_MANIFEST_20260928.md` 顶部新增"哈希口径"声明；自校验结果逐文件 PASS |
| **3** | 说明仍写「95/96」的平台差异，本轮实际应为 **macOS 118 / Windows 119**，要求更新口径 | 已全量更正。且因 v9 新增 9 项检查，本轮口径更新为 **Python Windows 128 / macOS 127**、**Node 94/94**；`T22d2`（Windows 专属 ACL 读回核验）仍是那 1 项差值来源，非口径不一致 | `DELIVERY_MANIFEST_20260928.md` §三；`rotation_runbook_20260928.md` §9.7 |

---

## 二、v9 相对 v8 的代码变更（仅此一处收紧）

服务端 `rotation_action_actual.gs`：

```javascript
function _parseStrictPositiveInt(raw, nowMs) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== 'string') raw = String(raw);
  // v9：【不做 trim】——任何前导/尾随空白都会让纯数字校验失败 ⇒ 返回 null（失败关闭）
  if (!/^[0-9]+$/.test(raw)) return null;          // 仅数字：拒符号/小数/指数/后缀/空白
  if (raw.length > 16) return null;
  var n = parseInt(raw, 10);
  if (!(n > 0)) return null;
  if (n > Number.MAX_SAFE_INTEGER) return null;
  if (n > nowMs) return null;
  return n;
}
```

Python 测试模型 `rotation_logic_test.py` 的 `strict_pos_int` 同步去掉 `.strip()`，保持与服务端语义逐条对齐。

拒绝提示同步更新为：`capability 创建时间缺失或无效（须为严格正整数时间戳，不含符号/小数/指数/后缀/空白）`。

**未改动**：v6 三项（owner 必须存在且严格匹配 / 消费时强制 TTL / ACL 读回失败关闭）、v7 fail-closed 双条件、v8 严格正整数解析——均**保留并回归通过**。

---

## 三、清单哈希口径修正（针对 Tom 第 2 项）

**缺陷**：往版清单直接对本地文件算 SHA-256。本地为 CRLF，git 提交时转为 LF，仓库分发的字节与本地不同 ⇒ 清单声明值与 Tom 实际下载到的文件**必然不一致**。实测受影响文件 7 个（`TEST_OUTPUT_20260928.txt`、`rotate_remote_token_client.py`、`_gen_dispatch_sim.py`、`deployment_evidence_20260926.json`、`STATE.json`、`STATE.json.sha256`、`DELIVERY_MANIFEST_20260928.md`）。

**修正后流程**：
1. 先推送全部交付文件到仓库；
2. 从仓库 raw **抓取实际分发字节**，据此计算每个文件的 大小 / SHA-256 / SHA-1；
3. 用抓取到的字节拼装 `ALL_IN_ONE_20260928.txt` 并推送，再抓取其分发字节计算哈希；
4. 生成 `DELIVERY_MANIFEST_20260928.md` 并推送；
5. **二次抓取**每个文件的分发字节，与清单声明值逐文件比对并输出 PASS/FAIL（自校验）。

清单不声明自身的哈希（避免自引用）；交付主体为仓库，`ALL_IN_ONE_*.txt` 为单文件合集备用。

---

## 四、测试（本机真实执行，均 exit 0）

- `python rotation_logic_test.py` → **128/128 PASS**（macOS 为 **127/127**；缺 `deployment_evidence_20260926.json` 时退出码 2 且不输出任何裁决）
- `node dispatch_sim_test.js` → **94/94 PASS**（嵌入生产真实 `RemoteTrigger.gs` 与真实 `doPost`，由 `_gen_dispatch_sim.py` 自动生成、零手抄）

本轮新增：`F7m/F7n/F7o`、`T26m/T26n/T26o`（各 3 项断言：拒绝 / 令牌未改 / capability 已清理）。

**范围声明**（不变）：以上均为**仿真与静态断言**——分发层用生产分发器真实源码，服务端状态为按其行为复刻的 mock，非 GAS 运行时；不构成生产轮换放行。
**如实声明**（不变）：Tom 本机无 Node，**94/94 分发测试仍未由他独立复现**（v7 为 71/71、v8 为 85/85）。如需，可改为纯 Python 复刻一份分发层仿真以便其本机复跑。

---

## 五、状态（维持未变）

- 凭证事件维持 **OPEN**。
- T1-B B 列修复生产批准数维持 **0**；本包不涉及 T1-B B 列修复。
- v9 **仍为待审核方案**；Tom 审核通过 ≠ 生产授权，真实轮换须经 Rita / 生产负责人单独授权。
- 本轮未部署、未执行轮换。

---

## 六、v9.1 交付修正（回应 Tom 第八轮 —— 仅交付/文档，代码未改动）

Tom 第八轮结论：**就本轮修订范围，代码复审通过**（macOS 实跑 Python **127/127 PASS**，退出码 0；Node 94/94 未由其本机独立复跑）。
另提出 1 项**交付/文档**问题：交付说明中写了 `python _build_manifest.py verify` 的复跑指引，但该脚本**不在收到的包内**，无法按指引复跑。

核查后问题比表面更深一层：即使把脚本原样随包发出，审核人**仍然跑不起来**——
原 `verify` 依赖一份**不随包分发**的本地台账 `_manifest_hashes.json`（构建时生成的中间产物），包内没有。

修正（两处，均只涉及交付物，不动轮换代码）：

1. **`_build_manifest.py` 随包分发**，并在交付清单中声明其大小与 SHA-256。
2. **`verify` 改为离线自包含**：直接解析**包内** `DELIVERY_MANIFEST_20260928.md` 的声明值，与同目录实际文件逐字节比对；
   不再依赖任何包外文件，也不需要网络。用法：`python _build_manifest.py verify`（或 `--dir DIR` 指定目录）；
   全部一致退出码 0，任一不符退出码 1。`--net` 仍可选（改为抓取仓库 raw 字节比对）。

**代码零改动**：`rotation_action_actual.gs`、`rotate_remote_token_client.py`、两套测试的源码与上一轮（Tom 已过审的 v9）逐字节一致，
仅包内新增一个核验脚本 + 清单/合集/说明文字更新。
