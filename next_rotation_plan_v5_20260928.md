# 下一次 REMOTE_TOKEN 轮换 — 执行方案 v5（脱敏，供审核；非生产授权）

> 本方案为**待审核方案**。v4 于 2026-09-28 经 Tom 第三轮复审后**仍未通过代码审核**（3 条阻断），本版为逐条修订后的 v5。
> 全文不含任何令牌原值；本方案不执行任何轮换，须经 Rita/生产负责人单独授权后方可执行。
> Tom 已确认：v4 交付哈希核对通过、Python 离线测试 49/49 由其独立复跑通过；本机无 Node，37/37 分发测试未由其复现（已如实标注）。

## 0. v5 相对 v4 的修订清单（逐条对应 Tom 第三轮复审意见）

| Tom 意见 | v4 的缺陷 | v5 修订 | 证据 / 验证 |
|---|---|---|---|
| **1.** 超时/响应丢失时，不能因一次状态查询仍显示旧令牌就删除新令牌暂存并判定"未轮换"；原请求可能仍在执行，稍后才生效。应保留新令牌、维持 UNKNOWN，待确认原请求不再在途并复核稳定状态后再终判。请补竞态负向测试 | `_resolve_unknown()` 只要看到指纹=OLD 就 `confirmed_old_unrotated` 并**立刻 `escrow_purge`** —— 单次观测即终判，且删除了可能稍后生效的 NEW | ①服务端新增 **`rotation_inflight` 在途标记**（轮换进入即置位，`finally` 清除），`rotationStatus` 暴露 `inflight` / `inflight_id`；②客户端只要观测到 `inflight=true` 就返回 `still_unknown(reason=inflight)`，**保留暂存、不终判**；③判定"未轮换"改为**连续两次稳定观测**（同为 old、inflight 均 false、counter 相同，中间等待 settle 默认 30s）；④即便终判也只把暂存标记 `abandoned` 并**保留**，删除只能由操作员显式 `--purge-escrow` | T17/T17b–T17g（竞态负向 + 随后落地可恢复）、T18/T18b–T18d（双观测门槛 + 暂存保留）；服务端侧 F4/F4b |
| **2.** 写入本地配置的临时文件及替换后的文件必须明确限制访问权限，并在失败路径核验；不能仅依赖系统默认权限 | 临时文件用普通 `open(...,'w')` 创建（继承默认权限），替换后未再收紧、未核验 | ①临时文件以 `os.open(..., 0o600)` **创建即为 0600**；②`os.replace` 后对最终文件**再次** `restrict_perms`；③`restrict_perms` 显式 chmod 0600 后**读回核验**：POSIX 校验 `st_mode` 无 group/other 位；Windows 追加 `icacls /inheritance:r` + `/grant:r <user>:F` 并**读回 ACL 核验仅剩本用户**；④核验失败抛 `PermissionHardeningError` ⇒ 落入"服务端已换、本地写入失败"路径，暂存保留可 `--recover` | T22/T22b–T22e、T23/T23b–T23e |
| **3.** 自动 `force=true` 覆盖已有 capability 及设置动作与轮换动作的并发关系，请收紧并补测，避免覆盖另一笔在途操作 | 客户端无条件 `force=True`，服务端只看一个 force 开关；且设置与轮换之间无并发保护 | ①**取消无条件 force**；capability 增加 `owner_id` + 创建时间 + TTL(10min)；允许覆盖的条件只剩三种：同 owner 幂等重设 / 已超 TTL（陈旧）/ 操作员显式 `force_over_foreign=true`（且默认关闭，需 `--force-over-foreign`）；②**任何情况下只要 `rotation_inflight` 置位就拒绝**设置或覆盖；③轮换时校验 `owner_id` 与存储归属一致，不匹配则拒绝且**不消费**（不删除）他人在途的 capability | E5c–E5h、F1/F1b、F2/F2b、F3/F3b–F3c、F5/F5b；客户端 T19–T21 |

> 承上：v5 **仍为待审核方案**；Tom 审核通过 ≠ 生产授权。凭证事件维持 OPEN，T1-B B 列修复批准数维持 0。
> 本轮**未部署、未执行任何轮换**（按 Tom 要求）。

---

## 0. 与本次事件（T1→T2）的差异（已采纳 Tom 指正）
| 项 | 本次（已发生） | 下版（本方案 v3） |
|---|---|---|
| 新令牌传输位置 | GET URL 查询串 `?...&t=<T2>`（泄漏面） | HTTPS POST **请求体** JSON，URL 零查询串 |
| 临时入口读取 | `e.parameter.t`（GET 查询串） | `e.postData.contents`（POST body），经现有 `_rtMaybeHandlePost` 解析后由 `e.postBody` 传入 |
| 入口鉴权 | 无 | 一次性 **SHA-256(nonce)** 能力（非 HMAC）+ 既有 REMOTE_TOKEN 门校验 + 锁内先删后做 |
| 接入方式 | 新增独立 `function doPost(e)`（**覆盖生产入口，v2 错误**） | 注册 action 到 `REMOTE_ACTIONS` + 在已有 doPost 顶部加**一行** hook（不覆盖） |
| 关闭方式 | 删除 HEAD 中 handler | 删 HEAD handler + **实测枚举全部署核验（§5，含逐项依据与采集时点）** + 删除临时版本 v144（须授权人员操作，§5.4） |
| 状态确认 | 无 | `rotationStatus` 只读指纹查询，解决超时/响应丢失的"未知态" |
| 日志 | 未系统性核查 | 代码层零日志 + 主动 Cloud Logging 查询（不搜令牌、不关日志） |

---

## 1. 术语统一（纠正 v2 的"HMAC"误称）
- v2 文档称"一次性 HMAC 凭据"，但示例实为 **随机 nonce + SHA-256 哈希比对**，**并无 HMAC**。本方案统一称为：
  - **一次性 SHA-256 nonce 能力（one-time SHA-256 nonce capability）**。
  - 服务端只存 `rotation_nonce_hash = SHA256(nonce_hex)`，永不存 nonce 原值；调用方在请求体提交 `nonce` 原值，服务端重算 `SHA256(nonce)` 比对。
  - 这不是 HMAC（无密钥、无消息认证码结构），不应称为 HMAC。已全文更正。

---

## 2. 实际服务端代码（待部署；接入现有分发，不覆盖生产入口）

### 2.1 现有生产入口结构（实测，来自 RemoteTrigger/RemoteActions 注册表模式）
- `doGet(e)` → `_rtMaybeHandle(e)`：校验 `e.parameter.token` 对 `REMOTE_TOKEN` → 按 `e.parameter.action` 查 `REMOTE_ACTIONS` 注册表 → 调用对应函数。
- `doPost(e)` → `_rtMaybeHandlePost(e)`：解析 `e.postData.contents` 为 JSON → 合并 `e.parameter` → 调用 `_rtMaybeHandle({parameter, postBody})`，并把解析后的 body 挂到 `e.postBody`。
- 因此新功能**只需**：①在 `REMOTE_ACTIONS` 注册一个 action；②在已有 `doPost` **顶部加一行** `_rtMaybeHandlePost` hook。绝不再写独立的 `function doPost(e)`。

### 2.2 拟部署差异（机器可读 patch，非注释指引）
| 文件 | 改动 | 形态 |
|---|---|---|
| `RemoteActions.gs` | `REMOTE_ACTIONS` 注册表新增 3 行（在 `probeCalendar` 之后补逗号并追加） | `rotation_deploy_diff_20260928.patch`（unified diff，含源文件 SHA-256） |
| `RotationActions.gs` | **新增文件**：`tsSetRotationCapability` / `tsRotateRemoteToken` / `tsRotationStatus` / `_sha256` | 全文见 `rotation_action_actual.gs` §2 |
| `Code.gs` | **零改动** | 第 135–140 行 `doPost` 已是 `var r = _rtMaybeHandlePost(e); if (r) return r;` |
| `RemoteTrigger.gs` | **零改动** | 分发器与令牌门均为既有代码 |

注册 3 行（camelCase 键）：
```javascript
  rotationStatus:        function(e) { return tsRotationStatus(e); },        // 只读状态查询（结果未知时独立确认用）
  setRotationCapability: function(e) { return tsSetRotationCapability(e); }, // 一次性能力热装（写 SHA-256(nonce)）
  rotateRemoteToken:     function(e) { return tsRotateRemoteToken(e); },     // 执行轮换（锁内先删后做）
```

**本机已实测**（非口头声明）：
```
git apply --check -p1 rotation_deploy_diff_20260928.patch   → PASS
git apply      -p1 rotation_deploy_diff_20260928.patch      → 应用成功，结果哈希与 patch 声明一致（忽略 CR）
node dispatch_sim_test.js                                   → 37/37 PASS，exit 0
```

### 2.3 服务端分发合约（v3 的真实 bug，已修正）
真实分发器 `RemoteTrigger.gs` 第 80–81 行：
```javascript
var out = REMOTE_ACTIONS[_rtKey](e);
if (out !== undefined && out !== null) result.message = String(out);
```
- **处理函数必须 `return JSON.stringify({...})` 字符串**（与既有 `tsReadRange`/`tsAppendRows`/`tsPatchCells` 完全一致）。
- v3 写成 `return _rtResponse({ok:...})`（ContentService 对象）→ 被 `String()` 强转成 `"[object Object]"`，客户端在**成功路径上就拿不到** `rotated`/`counter`（这是 v3 的真实缺陷，非文档问题）。
- **客户端必须按两层读取**：
```json
{ "ok": true, "action": "rotateremotetoken", "version": "RT1.0", "ts": "...",
  "message": "{\"ok\":true,\"rotated\":true,\"counter\":1}" }
```
  `outer["ok"]`=false ⇒ 令牌门失败或处理函数抛异常（不交接、不重试写入）；
  `inner = json.loads(outer["message"])` ⇒ 业务载荷；`message` 以 `unknown action` 开头 ⇒ 动作名未命中。
- **动作名匹配**：分发器做 `String(key).toLowerCase() === action.toLowerCase()`，故 `rotateRemoteToken`/`rotateremotetoken` 命中，而 **`rotate_remote_token`（下划线）不命中**（负向用例 C2 已实测）。

### 2.4 一次性能力热装 `setRotationCapability`（v5 收紧：归属 + TTL + 在途互斥）
- 客户端生成 `nonce` → 本地算 `nonce_hash = SHA256(nonce_hex)` → 经既有令牌门 POST
  `{"action":"setRotationCapability","token":OLD,"nonce_hash":...,"expected_old":OLD,"owner_id":<本次运行ID>}`。
- 服务端写入 `rotation_nonce_hash` + `rotation_capability_owner` + `rotation_capability_created`。
- **拒绝条件**（任一即拒，且不动已有 capability）：
  1. `rotation_inflight` 置位（有轮换在途）；
  2. `expected_old` 与当前 REMOTE_TOKEN 不符；
  3. `nonce_hash` 非 64 位小写十六进制；
  4. 缺 `owner_id`；
  5. 已存在 capability，且**既非同一 owner、又未超过 TTL(10 分钟)、又未显式 `force_over_foreign=true`**。
- **`force` 已被取消**：v4 的"客户端自动 force=true"等于无条件覆盖，v5 不再存在该参数。

### 2.5 在途标记与并发关系（v5 新增）
- `tsRotateRemoteToken` 进入即 `setProperty('rotation_inflight', request_id)`，`finally` 中删除（成功/失败/异常都清）。
- 在途期间：`setRotationCapability` 被拒；第二个 `rotateRemoteToken` 被拒 ⇒ 不会并发写令牌。
- `rotationStatus` 返回 `inflight` / `inflight_id` / `capability_age_ms` / `owner_fingerprint`（均不含令牌）。
- **并发语义小结**：设置与轮换通过同一把 `LockService` 脚本锁 + 在途标记串行化；归属 `owner_id` 保证"自己的 capability 只被自己的轮换消费"，他人 capability 不会被误删。

### 2.6 旧凭据如何校验（双因子，沿用 v3/v4）
- **一次性能力（授权）**：服务端存 `SHA256(nonce)` + owner；调用方在 body 提交 `nonce` 与 `owner_id`；服务端重算比对（锁内 + 命中即删）。
- **旧 REMOTE_TOKEN（状态）**：调用方在 body 提交 `expected_old`；服务端确认当前 `REMOTE_TOKEN` == `expected_old` 才写入新值。
- 两者均在 **POST body**，均不进 URL、不进日志。

## 3. 实际客户端代码（POST 请求体，URL 零令牌；含竞态/权限/并发修订）

> 规范文件：`rotate_remote_token_client.py`（v5）。以下为要点摘录，完整代码以该文件为准。

**配置来源与字段对齐**：运行期从 `tools/.ts_selfcheck.json`（真实结构 `{"_note","url","token"}`）读取；
持久化写 **`token`** 字段，历史别名 `REMOTE_TOKEN` 若存在一并同步。

**写前暂存 write-ahead escrow + 竞态规则（v5 核心修订）**
```python
esc = escrow_write(NEW, owner_id=OWNER)                     # 发起前：NEW 落受保护暂存（0600+核验）
okc, _ = set_capability(url, OLD, nonce_hash, OWNER)        # ① 热装（受限覆盖，无无条件 force）
outer  = post_json(url, {'action':'rotateRemoteToken','token':OLD,'nonce':NONCE.hex(),
                         'expected_old':OLD,'new_token':NEW,'owner_id':OWNER,'request_id':req_id})
# ② 结果未知时：双观测 + 在途判定，绝不单次终判
#    inflight=True           → still_unknown(reason=inflight)，保留暂存
#    指纹=NEW 且 inflight=False → confirmed_new（交接 NEW）
#    连续两次 old 且 inflight 均 False 且 counter 相同 → confirmed_old_unrotated（暂存标记 abandoned，保留）
```
- 终判"未轮换"后**不删除暂存**，只标记 `abandoned`；清除只能由操作员 `--purge-escrow`。
- `--recover` 会先用暂存值真实鉴权 + 比对 `sha256(token|counter)` 指纹；`inflight=true` 时拒绝恢复。

**文件权限（v5 新增）**
```python
fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)   # 临时文件创建即为 0600
...
os.replace(tmp, p)
restrict_perms(p)        # 替换后再次收紧 + 读回核验（POSIX 查 st_mode；Windows 查 icacls ACL）
```
核验失败 ⇒ 抛 `PermissionHardeningError` ⇒ 走"服务端已换、本地写入失败"路径，暂存保留可恢复。
**不依赖任何系统默认权限。**

**并发/覆盖（v5 新增）**：本次运行生成 `OWNER = uuid4().hex` 全程携带；
默认不覆盖他人未过期的 capability；确需覆盖须操作员显式 `--force-over-foreign`（终端会提示其含义）。

### 3.1 凭证交接语义（v5：含在途与稳定观测规则）

| 情形 | 服务端实际状态 | 本地配置动作 | 受保护暂存 | 返回 result | 是否重发轮换 |
|---|---|---|---|---|---|
| **成功** `rotated` | 已切 NEW | 原子写 NEW 覆盖 OLD | 成功后清除 | `rotated` | 否 |
| **confirmed_new**（响应丢失后确认 NEW 生效） | 已切 NEW | 写 NEW | 成功后清除 | `confirmed_new` | 否 |
| **在途** `inflight=true`（原请求可能稍后才生效） | **不确定** | **不改** | **保留（armed）** | `still_unknown`（reason=inflight） | 否，且**禁止**判定未轮换 |
| **未达稳定**（观测不足/状态变动） | 不确定 | **不改** | **保留** | `still_unknown`（reason=no_stable_observation） | 否 |
| **确认未轮换**（连续两次稳定观测均 old、inflight 均 false、counter 相同） | 仍为 OLD | 不改 | **保留并标记 abandoned** | `confirmed_old_unrotated` | 否（可清残值后重跑） |
| **服务端已切但本地持久化失败**（含权限核验失败） | 已切 NEW | 写入失败，仍 OLD | **保留** | `rotated_server_but_persist_failed` | **否**（capability 已焚毁）→ `--recover` |
| **拒绝** `rejected`（capability 无效/已消费/旧值不符/归属不符） | 未切，仍为 OLD | 不改 | 清除（NEW 从未生效） | `rejected` | 否（须重备一次性凭据后另发） |
| **capability 冲突**（他人未过期） | 未切 | 不改 | 清除 | `capability_conflict` | 否（等 TTL 或显式 `--force-over-foreign`） |

红线：持久化失败**绝不重发轮换请求**——服务端已切，重发必被 `rejected`；只能 `--recover` 或按 runbook 人工处理。
以上由 `rotation_logic_test.py` T9–T23 验证（见 §9）。

---

## 4. 结果未知时的独立状态确认（纠正 v2 的"锁内先删后做"盲区）
v2 在锁内"先删 nonce 再写令牌"，若旧值不符/写异常/超时，nonce 已删，不能盲目重试。本方案规定：

- **旧值不符**：返回拒绝且 capability 已作废（`rotation_nonce_hash` 已删）。客户端**不重试写入**；操作员需清掉（若残留）后重新准备全新 NONCE + 重写哈希，再次发起。
- **写入异常（服务端正抛错）**：同"旧值不符"路径，capability 已焚；客户端据返回错误分类处理，不重试。
- **请求超时 / 响应丢失（结果未知）**：客户端**禁止直接重试写入**。改为调用 `rotationStatus`（用 OLD 认证；若 OLD 已失效则用 NEW 认证），比较返回 `token_fingerprint` 与本地算出的 `SHA256(候选值|counter)`：
  - 命中 NEW 指纹 → **已生效**（之前写入成功）→ 结束，无需重备。
  - 命中 OLD 指纹 → **未轮换** → 允许操作员清残留 capability、重备一次性凭据后再次发起。
  - 仍不确定 → 间隔后再次 `rotationStatus` 或人工核查 Script Properties。
- **"何时允许重新准备一次性凭据"**：仅在 `rotationStatus` 确认当前仍为 OLD（未轮换）且 `nonce_present` 为 false（或操作员已显式清除残留哈希）之后。绝不在结果未知时重发写入。

---

## 5. 全部署入口关闭核验（实测可运行 + 真实清单 + 失败标准 + v144 防再绑定）

> **采集时点（单点快照）**：本轮枚举于 **2026-09-27T22:0x +08:00** 执行，使用项目 OAuth 令牌（`.clasprc.json`）仅做 `GET`（ deployments / versions / content ），无任何写入。以下结论仅代表该时点状态；执行轮换前须重新枚举核验。

### 5.1 实测枚举方法（只读，已执行于 2026-09-27T22:0x +08）
```bash
# 用项目 OAuth 令牌（.clasprc.json）调用 Apps Script API（GET，无写入）：
GET /v1/projects/{SCRIPT_ID}/deployments
# 对每个部署：取其 deploymentConfig.versionNumber（或 HEAD），GET 该版本/HEAD 的 files(source)
GET /v1/projects/{SCRIPT_ID}/versions/{vn}?fields=files(name,source)
# 或 HEAD： GET /v1/projects/{SCRIPT_ID}/content?fields=files(name,source)
# grep 轮换入口标记：rotate_remote_token | rotation_nonce_hash | tsRotateRemoteToken | rotation_counter
```
- **主动探测（语义须如实说明）**：对每个部署 URL 发 POST `{action:'rotate_remote_token',nonce:'probe',expected_old:'probe',new_token:'probe',token:'probe'}`。
  - **探测击中位置**：该 POST 的 `token:'probe'` 不等于真实 `REMOTE_TOKEN`，因此在 `_rtMaybeHandle` / `doGet` 的令牌门即被拒绝，**未到达任何处理函数**，更未触达轮换入口（副作用入口）。因此"探测被拒"证明的是**鉴权门生效**，而**不能直接证明轮换 handler 不存在**。
  - **轮换入口不存在的确证来源**：是源码 grep（见下），而非该探测。
- **源码级确证（权威依据）**：
  - **HEAD 部署**：`GET /content` 回源 10 个文件，对全部文件 grep 上述 4 个标记 = **0 命中** → HEAD 确为 clean（直接验证）。
  - **版本钉死型部署（15 个）**：经 `versions/{vn}?fields=files(name,source)` 取回时 `file_count=0`（该 fields 参数未回源正文），**无法对其实体源码做 grep 验证**。其"clean"判定依据为两条**间接**证据：①本轮枚举"无任一部署 `versionNumber` 钉在临时版 v144"（grep 144 = 0）；②轮换代码从未进入任何已提交版本（临时入口仅在 v144 短暂存在，见 §5.4）。此为基础 weaker 的推断，非直接源码验证，列为残留不确定性。
- 同时查 Script Properties 残留：`rotation_*` 键必须为空。

### 5.2 覆盖的部署清单（本次实测，16 个，采集于 2026-09-27T22:0x +08）
| 部署 | 版本 | 判定依据 | 轮换标记 |
|---|---|---|---|
| AKfycbwlxB2z9IDDo7pBv4sr0pu6-1ywvYBuRyqTwfjgl_o | HEAD（生产 Web App） | **直接**：content 回源 10 文件，grep=0 | 无 |
| AKfycbzX-9bRQmxCevgCIfQvu… | 28 | 间接：无 v144 钉 + 轮换代码未入任何提交版本 | 无（推断） |
| AKfycbzJcG929pxRKYPrPZk7Yz… | 126 | 间接（同上） | 无（推断） |
| AKfycbxoyvIDfpGcXOzaPvHX8e… | 30 | 间接（同上） | 无（推断） |
| AKfycbykglC9BbAuKgXz06QBQd… | 26 | 间接（同上） | 无（推断） |
| AKfycbzThsSfw3D-QWU-bitE1ea… | 113 | 间接（同上） | 无（推断） |
| AKfycbxzgWZslPGudxBXJ7TcZ5… | 66 | 间接（同上） | 无（推断） |
| AKfycbx64H5vGlmG772M8bxJA6… | 27 | 间接（同上） | 无（推断） |
| AKfycbyBT9QN3xfToWlDBFAQGl… | 112 | 间接（同上） | 无（推断） |
| AKfycbxwrj0s-a-HnioG021aGmb… | 29 | 间接（同上） | 无（推断） |
| AKfycbx1-vu1YUr-d67D8xd3xrm… | 65 | 间接（同上） | 无（推断） |
| AKfycbztl4U2x-QW1bKVekXDTpP… | 127 | 间接（同上） | 无（推断） |
| AKfycbxaAq1B6xCqtSZd49-XHrk… | 31 | 间接（同上） | 无（推断） |
| AKfycbyH1-sbOYmte6O6uThLivX… | 145 | 间接（同上） | 无（推断） |
| AKfycbwDGrQuHkc5klSTuQNxn_… | 67 | 间接（同上） | 无（推断） |
| AKfycbzw02OR6L0MUObKXDFRYiM… | 129 | 间接（同上） | 无（推断） |

> **结论措辞收紧**：本轮可断言"**生产 HEAD 部署源码直接验证 clean**"；对 15 个版本钉死型部署，只能断言"**无 v144 绑定 + 轮换代码未入任何提交版本（间接推断 clean）**"，不能断言"全部 16 个均已源码级验证 clean"。执行轮换前须重新枚举，并对版本钉死型部署改用可回源正文的取数方式（或经 GAS 编辑器逐版本查看）以补强该间接推断。

### 5.3 失败标准（任一即未闭环）
1. 任一部署源码 grep 命中任一轮换标记（`rotate_remote_token` / `rotation_nonce_hash` / `tsRotateRemoteToken` / `rotation_counter`）。
2. 任一部署探测 POST 返回 `rotated:true` 或 `ok:true`（临时入口仍可用）。注意：探测被拒仅证明鉴权门生效（见 §5.1），本条第 1 项的源码 grep 才是轮换入口是否存在的权威判定。
3. Script Properties 仍有 `rotation_*` 残留键。
4. 临时版本 v144 仍存在于版本列表且/或仍有部署钉死它。

### 5.4 临时版本 v144 一类如何防止日后重新绑定
> **已采纳 Tom 2026-09-28 指正（措辞收紧）**："v144 未被当前部署绑定"**只描述当前状态，并不阻止日后被重新绑定**——任何人只要把某部署的版本号改成 144，入口就会复活。因此删除 v144 是**必要闭环动作**，不是"额外保险"。删除**须由授权人员**执行并**留存核验**；删除前的"未绑定"状态不得作为已闭环的依据。

- **发生时（轮换后）**：删除临时版本 v144，使其无法被任何部署钉死。**删除操作须由具备 GAS 项目编辑权限的授权人员执行**——优先在 GAS 编辑器 Project History 中删除（UI 支持删除未绑定活动部署的版本，含批量删除）；若经 API 删除，则**仅当该版本未绑定任何活动部署时** API 才允许（REST API 无删除方法，故 agent 无法自动化，须人工）。
- **核验留存**：删除 v144 后，**重新枚举 deployments + versions** 确认 v144 已从版本列表消失且无任何部署 `versionNumber == 144`，并将该核验结果（含采集时点、执行人）记录存档，作为闭环证据。
- **结构上**：临时轮换入口**只存在于临时版本 v144**，并在"切回干净版本"步骤即从 HEAD 移除 `REMOTE_ACTIONS['rotate_remote_token']` 与 `tsRotateRemoteToken`/`tsRotationStatus` 函数；干净版本（生产钉死版本）不含这些符号。
- **约束**：任何部署的 `versionNumber` 不得设为临时版本号；本方案执行后由 §5.1 枚举校验"无部署钉在 v144"。
- **实测现状（限定范围表述）**：本次采集的 **16 个部署**中无任何一个 `versionNumber == 144`（grep 144 = 0，采集时点 2026-09-26T14:44:48Z，来源见 `deployment_evidence_20260926.json`）。该事实**仅说明"这些部署当前未钉在 v144"**，不等于 v144 已被删除、也不等于不可再绑定。**删除仍须执行**，并按上款由授权人员操作 + 重新枚举 + 留存核验。

---

## 6. 日志验收（不以"临时关闭安全日志"代替保护请求内容）
- **日志来源**：GAS 执行日志位于所关联 Google Cloud 项目的 Cloud Logging（若已启用 Cloud Logging / Executions 日志）。查询资源类型 `resource.type="app_script_function"`。
- **查询权限**：需项目 IAM 中 `roles/logging.viewer` / `roles/logging.privateLogViewer` / `roles/owner` / `roles/editor` 之一。验收时同时列出具备上述角色的主体，若范围过宽须收窄为最小权限并记录。
- **时间范围**：轮换执行窗口 ±30 分钟。
- **查询式（不以令牌为条件）**：
  ```
  resource.type="app_script_function"
  AND timestamp∈[T0-30m, T1+30m]
  AND (textPayload:"rotate_remote_token" OR textPayload:"new_token" OR textPayload:"nonce")
  ```
  期望命中 = **0**（因为服务端代码零 `Logger.log`/`console.log` 引用请求体/nonce/令牌，见 §2.3 源码）。
- **限制（如实披露）**：
  - 若 Cloud Logging **未启用**，则无服务端日志 → "零命中"为**空真**，必须注明"无法从日志侧排除请求体被留存"，不能据此声称已闭环。
  - Apps Script **不会**自动捕获请求 URL/body，除非代码主动记录；故主防护仍是**代码层零日志**（§2.3 已通过 T8 测试）+ 临时入口不存在（§5）。
  - **不将新令牌或其前缀填入日志搜索条件**（Tom 要求），也不为此关闭安全日志。
  - 平台/网络层（如代理、LB）是否留存请求行属 GAS 平台侧，超出本项目可控范围，列为残留风险。

---

## 7. 执行后验收标准（不提供任何令牌值）
1. 旧值拒绝：用 OLD 调 `readRange` → `{"ok":false}`。
2. 新值接受：用 NEW 调 `readRange` → `{"ok":true}`。
3. 临时入口不可用：capability 已删 → 任意调用返回拒绝；且 §5 全部署核验通过（4 项失败标准全不满足）。
4. 版本源码不含新值：全部被引用版本 `GET /content` grep NEW = 0；NEW 仅存 Script Properties + 操作员本机内存（已丢弃）。
5. 日志验收通过：§6 查询 0 命中（或注明未启用日志的局限）+ IAM 读者已收窄记录。

---

## 8. 授权与执行闸门
- 须 Rita / 生产负责人**单独授权**本次轮换（与令牌轮换授权 rotation_write_approved=1、T1-B 修复授权 production_write_approved=0 均分开记录）。
- Tom 可对本方案给书面审核意见；**审核意见 ≠ 生产授权**。
- 当前 T1-B 生产写入批准数 = 0；本方案不涉及 T1-B 修复。
- 凭证事件维持 OPEN（T2 曾现于 URL 查询串、Google 服务端日志可见性未证伪），直到 §5/§6/§7 核验通过方可降级。

## 9. 测试结果（v5，2026-09-28 +08:00）

### 9.1 `dispatch_sim_test.js`（Node；嵌入真实分发源码）—— **55/55 PASS，exit 0**
| 组 | 覆盖 | 结论 |
|---|---|---|
| A | POST body 解析与让位 | PASS |
| B | 旧令牌鉴权（错/无令牌被门拒且处理函数未执行） | PASS |
| C | action 名匹配（含下划线负向） | PASS |
| D | 既有 19 个 action 与内置 status 不受影响 | PASS |
| E | 轮换四路径 + **capability 热装护栏**（缺 expected_old / 非法哈希 / 缺 owner_id / 同 owner 幂等 / 他人新鲜拒 / 显式覆盖 / 超 TTL） | PASS（E1a–E6c） |
| F | **在途保护与归属校验**：在途拒设 capability 且不动原值、在途拒第二个轮换、owner 不匹配拒且不消费、在途状态查询返回 inflight、owner 指纹不泄露原文 | PASS（F1–F5b） |

### 9.2 `rotation_logic_test.py`（Python；逻辑仿真 + 负向）—— **86/86 PASS，exit 0**
| 组 | 覆盖 | 结论 |
|---|---|---|
| T1–T6 | 服务端基础（含在途标记 finally 清除、指纹、令牌门） | PASS |
| T7–T7d | 部署断言读真实枚举产物 | PASS |
| T8–T8k | 源码静态断言（含 inflight 置位/清除、owner 校验、取消无条件 force、双观测、权限收紧符号） | PASS |
| T9–T16 | 四路径交接 + 别名同步 + 持久化失败可恢复 | PASS |
| **T17–T17g** | **竞态负向**：在途时不得判定未轮换、暂存保留为 armed、随后落地可恢复 | PASS |
| **T18–T18d** | **终判门槛**：需 ≥2 次稳定观测；终判后暂存保留并标记 abandoned | PASS |
| **T19–T20e** | **覆盖收紧**：在途拒设、他人新鲜拒、同 owner 幂等、显式覆盖、超 TTL | PASS |
| **T21–T21c** | **归属校验**：owner 不匹配拒且不消费 | PASS |
| **T22–T22e** | **权限**：临时文件与最终文件均显式收紧并读回核验（Windows 读回 ACL 仅剩本用户） | PASS |
| **T23–T23e** | **权限失败路径**：核验失败 → 本地不写入、暂存保留、可恢复 | PASS |

### 9.3 退出码与负向实测
- `dispatch_sim_test.js`：0 全通过 / 1 有失败 / 2 嵌入源自检失败。
- `rotation_logic_test.py`：0 全通过 / 1 有失败 / 2 缺必需输入（`deployment_evidence_20260926.json`）且不输出任何裁决。
- 两套均可在任意空目录独立复跑（不依赖仓库结构、无网络、无真实令牌）。

> **范围限制（如实披露）**：以上为**仿真 + 静态断言**。分发层用生产分发器**真实源码**；服务端状态为按真实分发器行为复刻的 mock，非 GAS 运行时。
> Tom 本机无 Node，`dispatch_sim_test.js` 的 55/55 **尚未由其独立复现**（其已独立复跑 Python 侧 49/49）。这不构成生产轮换放行。

## 10. 操作步骤（不暴露令牌）
完整操作步骤见 `rotation_runbook_20260928.md`（v5 已补充：在途等待与终判规则、文件权限、并发/冲突处理）。

