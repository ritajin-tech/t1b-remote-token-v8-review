# REMOTE_TOKEN 轮换 —— 操作步骤（runbook v5，2026-09-28）
> v5 相对 v4 新增：在途等待与终判规则（§4b）、文件权限（§4c）、并发与冲突处理（§4d）。
> 本文件**全程不写任何令牌原值**，也不要求任何人把令牌贴进邮件/聊天/工单。
> 任何一步若要求你"把令牌发给某人"，那一定是错的，请立即停止。

---

## 0. 谁可以做 / 前置条件
| 项 | 要求 |
|---|---|
| 授权 | Rita 或生产负责人**单独授权**本次轮换（与 T1-B 修复授权分开记录）。Tom 审核通过 ≠ 生产授权 |
| 环境 | 获批客户端机器（本机），已装 Python 3 + `requests`；Node 18+（仅跑分发测试需要） |
| 网络 | 能访问 `script.google.com`；**不经过任何会记录请求体的代理**（否则须先评估） |
| 前置核验 | 方案 §5 全部署核验通过（4 项失败标准全不满足）；v144 已由授权人员删除并留存核验 |
| 禁止 | 令牌不得进 git / IMA / 日志 / 邮件 / 截图 / 工单；不得把 `tools/.ts_selfcheck.json` 复制到别处 |

---

## 1. 部署前：把代码改动上到 GAS（由授权人员执行）
1. 打开 Apps Script 项目（ts-manager），确认当前 HEAD 源文件与 patch 声明的 SHA-256（LF 归一化）一致：
   ```
   RemoteActions.gs  sha256(LF) = 见 rotation_deploy_diff_20260928.patch 头部
   ```
2. 在 `RemoteActions.gs` 的 `var REMOTE_ACTIONS = { ... }` 内，`probeCalendar` 行尾补一个逗号，并追加 3 行（camelCase 键，见方案 §2.2）。
3. **新增文件** `RotationActions.gs`：把 `rotation_action_actual.gs` 第 2 节整段（`ROTATION_CAP_TTL_MS` / `_nowMs` / `tsSetRotationCapability` / `tsRotateRemoteToken` / `tsRotationStatus` / `_sha256`）粘入。
4. `Code.gs` 与 `RemoteTrigger.gs` **不要改**（真实 `doPost` 第 135–140 行已接入分发）。
5. 保存后访问一次 `<生产 Web App URL>?action=status&token=<当前令牌>`，
   期望 `actions` 列表出现 `rotationStatus` / `setRotationCapability` / `rotateRemoteToken`（说明注册成功；此时未做任何轮换）。

---

## 2. 轮换前：确认当前令牌"在哪、是什么"（不打印、不外发）
- 当前令牌在本机 `tools/.ts_selfcheck.json` 的 **`token`** 字段（同文件还有 `url`）。
- **不要打开它复制到别处**。脚本会自己读。
- 若该文件的 `token` 与 GAS 菜单「📱 生成手机远程链接」显示的 Token **不一致**，先停——须人工核对哪一侧为准。

---

## 3. 干跑（只读，不改动任何东西）
```bash
cd <仓库>/_tmp/t1b_delivery
python rotate_remote_token_client.py --status-only
```
- 期望 `{"reachable": true, "status": {...}, "using_token_sha256": "<64位哈希>"}`；输出只有哈希，无令牌。
- `reachable: false` ⇒ 当前令牌不通或网络不通，先排查。
- 关注 `status.inflight`：若已是 `true`，说明**有轮换在途**，不要发起新的轮换。

---

## 4. 执行轮换（一条命令，过程自动）
```bash
python rotate_remote_token_client.py --rotate
```
内部顺序（你不需要干预）：
1. 生成本次 `OWNER`（本次运行唯一 ID）、`nonce`、新令牌 `NEW`（仅内存）；
2. **先把 NEW 写入受保护暂存** `~/.smcn_rotation_escrow/`（0600 + 读回核验）——失败时仍能取回 NEW 的保命设计；
3. 调用 `setRotationCapability`（**受限覆盖**：不覆盖他人未过期的准备；在途直接拒）；
4. 调用 `rotateRemoteToken` 完成轮换（服务端置位/清除在途标记）；
5. 服务端确认切换后，把 NEW 原子写入 `tools/.ts_selfcheck.json` 的 `token` 字段；成功才清除暂存。

**返回与下一步**（照抄即可，不要自行"重试轮换"）：

| 返回 `result` | 含义 | 你该做的 |
|---|---|---|
| `rotated` | 成功，本地已写入 | 进入 §6 验收 |
| `confirmed_new` | 响应曾丢失，但已确认 NEW 生效并写入本地 | 进入 §6 验收 |
| `still_unknown`（reason=`inflight`） | **原请求仍在服务端执行**，稍后才可能生效 | **不要重跑轮换、不要删暂存**。等几分钟跑 `--status-only`；`inflight` 变 false 后跑 `--recover` |
| `still_unknown`（reason=`no_stable_observation`） | 状态不稳定/查询未达 | 同上；暂存保留 NEW |
| `confirmed_old_unrotated` | 连续两次稳定观测仍为旧令牌、无在途 ⇒ 判定未轮换 | 暂存被标记为 `abandoned` **但保留**。确认无用后 `--purge-escrow`；可清 `rotation_nonce_hash` 残值后重跑 |
| `rotated_server_but_persist_failed` | 服务端已换成 NEW，但本机文件没写成功（含权限核验失败） | **不要重跑轮换**。`--recover`；若是权限问题，先修正目录/ACL 再 `--recover` |
| `capability_conflict` | 他人已热装 capability 且未过期（10 分钟内） | 等其过期（TTL 10 分钟）或确认其确已作废后，由操作员显式加 `--force-over-foreign` 重跑。**默认不会覆盖他人** |
| `capability_setup_failed`（inflight=true） | 有轮换在途，本轮未热装 | 稍后重跑 |
| `rejected` | 明确拒绝（capability 无效/已消费/旧值不符/归属不符） | 服务端没换，本地仍是旧值。看 `error`；重备一次性凭据后重跑 |

### 4b. 在途等待与终判规则（防竞态误判）
- 服务端在轮换期间置位 `rotation_inflight`，结束即清除；`rotationStatus` 会返回它。
- **只要看到 `inflight=true`，脚本就维持 UNKNOWN、保留暂存**——绝不因为"此刻还显示旧令牌"就判定未轮换。
- 判定"未轮换"的门槛：连续两次观测都是旧令牌、两次 `inflight` 均为 false、两次 `counter` 相同，中间等待 30 秒（可用 `--settle-interval` 调整）。
- 即便终判，暂存也**只标记废弃、不删除**；删除只能由你显式 `--purge-escrow`。

### 4c. 文件权限（不依赖系统默认权限）
- 临时文件 `cred.json.tmp` **创建时即为 0600**；替换成正式文件后**再次**收紧并**读回核验**。
- POSIX：核验 `st_mode` 无 group/other 位；Windows：chmod 0600 + `icacls /inheritance:r` + `/grant:r <你>:F`，并**读回 ACL 确认只剩你本人**。
- 核验不通过 ⇒ 视为"本地写入失败"，不留一个权限过宽的令牌文件，NEW 留在暂存可恢复。

### 4d. 并发与冲突
- 每次运行自带 `OWNER`；自己的 capability 只会被自己的轮换消费。
- 在途时：既不会被新的 capability 设置覆盖，也不会被第二个轮换请求并发写入。
- 撞上他人未过期的 capability：默认**拒绝覆盖**（`capability_conflict`）；只有你确认对方确已作废后才用 `--force-over-foreign`。

---

## 5. 持久化失败后的恢复（可恢复交接）
```bash
python rotate_remote_token_client.py --recover
```
- 从暂存取出 NEW，**先拿它去服务端真实鉴权、比对 `sha256(token|counter)` 指纹**，确认它确是当前生效令牌后才写入本地。
- 服务端仍 `inflight=true` ⇒ 拒绝恢复（让你稍后再来，避免半途写值）。
- 暂存里的值不是当前生效令牌 ⇒ 拒绝写入。
- 恢复成功后暂存清除。

---

## 6. 轮换后验收（无需任何人看到令牌）
1. `--status-only` 应 `reachable: true`（用的是新值）。
2. 用一个只读业务 action（如 `readRange`）验证返回 `ok:true`。
3. Script Properties：`rotation_nonce_hash` **不存在**（用过即焚）；`rotation_inflight` **不存在**；`rotation_counter` 已 +1。
4. 按方案 §5 重新枚举全部署，4 项失败标准全不满足；v144 已删除并留存核验记录（执行人/时点/结果）。
5. 按方案 §6 做日志验收（Cloud Logging 未启用须如实注明"无法从日志侧排除"）。

---

## 7. 出事怎么办
| 情况 | 处置 |
|---|---|
| 本机 `tools/.ts_selfcheck.json` 丢失 | 从 GAS 菜单「📱 生成手机远程链接」取当前 Token，人工填回 `token` 字段；**不要**发邮件索取 |
| 暂存目录有残留 `escrow_*.json` | 先 `--recover` 判断它是否仍是当前生效令牌；确认无用后 `--purge-escrow` |
| 卡在 `still_unknown` | 先 `--status-only` 看 `inflight`；为 true 就等；为 false 就 `--recover`。**不要重跑 `--rotate`** |
| 撞上他人 capability | 等 10 分钟 TTL 过期后重跑；确需立即覆盖才用 `--force-over-foreign` |
| 怀疑令牌泄漏 | 再跑一次 `--rotate` 生成全新值作废旧值，并把事件记入审计；不要试图"删日志" |

---

## 8. 本 runbook 不做什么
- 不打印、不存储、不传输任何令牌原值；
- 不要求关闭任何安全日志（方案 §6）；
- 不提供"绕过令牌门/在途保护"的后门；
- 不构成生产授权：执行前仍须 Rita / 生产负责人单独批准。

---

## 9. v6 新增判定要点（Tom 第四轮复审 3 条）
- **9.1 归属必须存在且严格匹配**：任何 capability 都带 `owner`；轮换消费时若 capability 哈希在但 `owner` 为空（旧版遗留态），一律拒绝且**不消费**该 capability（不动哈希、不改令牌）。不要为兼容旧数据而"跳过 owner 检查"。
- **9.2 消费时强制 TTL**：capability 设了 TTL(10min)。不仅"设置时"据此判断可否覆盖，**"消费时"也须校验创建时间**——已过期就拒绝且不改令牌，并把过期 capability 一并清理（避免延迟到达的请求复用）。即使客户端已两次观测到稳定旧值，也不能据此放行过期请求。
- **9.3 权限读回必须失败关闭**：`restrict_perms` 在 Windows 上会 `icacls /inheritance:r` + `/grant:r <user>:F`，随后**读回 ACL 核验**。若读回命令失败（rc≠0）、结果为空或无法解析，**一律按失败关闭**（抛 `PermissionHardeningError`，绝不保留一个权限过宽的文件）。决不能用"解析为空"去推断"仅本用户"。
- 9.4 三步对应负向测试：`F6/F6b`、`T25/T25b`（9.1）；`F7/F7b/F7c`、`T26/T26b/T26c`（9.2）；`T24/T24b/T24c`（9.3）。

### 9.5（v7 新增）创建时间缺失/无效 ⇒ 失败关闭（Tom 第五轮 1 条阻断）
- **原缺陷**：`tsRotateRemoteToken` 仅在 `if (created)` 成立时才校验 TTL。若 capability 哈希+owner 都在、但创建时间字段**缺失 / 为 0 / 非数字 / 无法解析**，`created` 为 0/NaN，条件不成立 ⇒ **TTL 检查被完全跳过**，一个延迟到达的请求仍可能通过 nonce 校验完成轮换。
- **修订（失败关闭）**：TTL 校验改为双条件 fail-closed ——
  `if (!(created > 0) || (_nowMs() - created) > ROTATION_CAP_TTL_MS)` ⇒ 直接拒绝、**不改令牌**，并把 capability 三键一并清理（`rotation_nonce_hash` / `rotation_capability_owner` / `rotation_capability_created`）。
  只有 `created` 是**正整数**且**未过期**才允许消费。
- 含义：遗留/损坏的 capability（时间字段损坏）一律不可复用，必须重新热装 capability 才能轮换；延迟旧请求无法绕过 TTL。
- 对应负向 + 正向对照测试：
  - 服务端（真实 gs，嵌入 `dispatch_sim_test.js`）：`F7d` 创建时间缺失→拒绝、令牌未改、已清理；`F7e` 创建时间为 `'0'`→拒绝；`F7f` 创建时间为 `'abc'`→拒绝；`F7g` 创建时间有效且未过期→**允许**轮换（正向对照，证明正常路径未被误伤）。
  - Python mock：`T26d` 创建时间缺失→拒绝、令牌未改（仍 `OLD_MOCK`）、capability 已清理；`T26e` `'0'`→拒绝；`T26f` `'abc'`→拒绝；`T26g` 有效+未过期→允许、令牌切新值（正向对照）。
- 本轮（v7）测试规模：Python **107/107**、Node **71/71**，均 exit 0。

### 9.6（v8 新增）创建时间须为"严格正整数时间戳"——拒绝数字后缀/小数/科学记数法/未来时间（Tom 第六轮 1 条阻断）

- **原缺陷（v7 通过但仍不满足）**：v7 仅把 TTL 校验改成了 fail-closed 双条件，但解析创建时间仍用 `parseInt(createdRaw, 10)`（服务端）/ `int(float(...))`（Python mock）。二者都会**接受格式非法的原始值**：
  - 服务端 `parseInt("1700000000000x", 10)` → `1700000000000`（**带后缀字母被吞掉**）；
  - Python mock `int(float("1.7e12"))` → `1700000000000`（**科学记数法被接受**），`int(float("123.456"))` → `123`（**小数被截断接受**）。
  即一个被篡改/损坏的 `rotation_capability_created`（如 `"1700000000000x"`）仍能通过正整数判定并绕过 TTL 校验。
- **修订（v8，最严口径）**：新增 `_parseStrictPositiveInt(raw, nowMs)`（服务端）/ `strict_pos_int(raw, now)`（Python mock），**在 TTL 判断之前**先严格校验原始值：
  1. 必须是**纯数字字符串**（`/^[0-9]+$/`）——拒符号、小数、指数、后缀字母；
  2. 位宽 ≤ 16（快速拒超 safe-integer）；
  3. `> 0` 且 `≤ Number.MAX_SAFE_INTEGER`（gs）/ `≤ 2**53-1`（Python）；
  4. **不为未来时间**（`≤ nowMs`，不可能由本系统生成的时间戳若大于当前钟即视为非法）。
  任何一条不满足 ⇒ 返回 `null` ⇒ 拒绝轮换、清理 capability 三键、**绝不改令牌**。仅"干净正整数且未过期"才允许消费。
  `tsSetRotationCapability`（陈旧判定）、`tsRotateRemoteToken`（消费 TTL）、`tsRotationStatus`（状态展现）三处统一改用该严格解析。
- **为什么旧写法仍算"未通过"**：fail-closed 的双条件只解决了"缺失/0/非数字导致跳过 TTL"，没有解决"非法格式却被 parseInt 误判为合法正整数"这一旁路。v8 从解析源头堵死旁路。
- 对应负向 + 正向对照测试（均在 v8 重新跑通）：
  - 服务端（真实 gs，嵌入 `dispatch_sim_test.js`）：`F7h` 数字后缀 `"1700000000000x"`→拒绝、令牌未改、已清理；`F7i` 小数 `"123.456"`→拒绝；`F7j` 科学记数法 `"1.7e12"`→拒绝；`F7k` 未来时间戳 `"9999999999999"`→拒绝；`F7l` 干净正整数 `"3000000"`→**允许**轮换（正向对照）。
  - Python mock：`T26h` 后缀→拒绝、令牌未改（`OLD_MOCK`）、capability 已清理；`T26i` 小数→拒绝；`T26j` 科学记数法→拒绝；`T26k` 未来时间→拒绝；`T26g` 干净正整数→允许、令牌切新值（正向对照）。
- 本轮（v8）测试规模：Python **119/119**、Node **85/85**，均 exit 0。

