# REMOTE_TOKEN 轮换事件 — 脱敏审计记录（2026-09-27）

> 本记录为应 Tom 要求提供的事件审核材料。**全文不含任何令牌原值**，令牌以 T0（轮换前旧值）/ T1（当前活动值）/ T2（拟再轮换值）代称。

## 0. 摘要
- **目标脚本**：`finance_dss_backend`（scriptId `1FPAwV50…JRb8R`，写 SYS_Time / DB_工时流水）
- **授权**：Rita @ 2026-09-27T13:35（"只要你们技术没问题 就轮换令牌。你可以安排"）
- **首次轮换执行**：13:45 完成（T0 → T1）
- **复核发现**：Tom 13:5x 指出 v142 含 T1 明文，要求重新核验并提议再次轮换
- **再轮换执行**：14:21 完成（T1 → T2，参数传入法，T2 不进任何源码/版本历史）
- **本记录**：脱敏时间线 + v142/v143 核验 + 旧令牌失效 + 本地文件访问控制 + 再轮换结果

## 0.5 口径更正（应 Tom 2026-09-27T14:43 指正）
- 本记录前文「业务数据一行未动」**口径过宽，特此更正**：准确说法为——**T1-B B 列修复写入未被授权且未见交付证据**（gate=0、未 --apply、未回滚），故无 T1-B 修复写入；但**不能据此确认整张生产表没有发生过其他写入**。是否还有其他写入，不在本凭证事件审计范围内，须由业务数据影响核验（见第 10 节）单独确认。
- 「九月没有丢数据」**仍为未证实说法**；以 Tom 复核结论为准：「业务数据影响尚未核实，不认定零影响」。

## 1. 脱敏操作时间线（不出现任何令牌原值）
| 时间 | 动作 | 令牌状态 |
|---|---|---|
| 13:35 | Rita 授权轮换 | — |
| 13:4x | HEAD 快照；加临时 setter（硬编码 T1）PUT；建 v142 | ⚠️ T1 进入源码（暴露点） |
| 13:4x | 生产部署切 v142；用 T0 触发 `rotatetokentmp` 写 T1 入 Script Properties | 活动令牌 = T1 |
| 13:4x | 验证：T0 readRange→Invalid；T1 readRange→ok | — |
| 13:4x | 恢复 HEAD（去临时文件）；建 v143；生产部署切 v143 | HEAD 恢复干净 |
| 13:45 | 本地 `tools/.ts_selfcheck.json` 同步 T1；删临时文件 | — |
| 13:5x | Tom 邮件：v142 含 T1 明文，要求复核 + 再轮换 | — |
| 13:56 | 本 agent 独立只读核验 v142/v143/部署绑定 | 确认暴露成立 |
| 14:19 | Rita 回复「你和tom技术没问题就可以修」→ 授权再轮换 + 删 v142 | — |
| 14:21 | 再轮换 T2（参数传入法）：HEAD+handler→v144→部署→GET `setremotetokenparam?token=T1&t=T2`（**T2 在 URL 查询串**）→验证 T1 失效/T2 生效→恢复 HEAD→v145 干净→部署 | **T2 不进任何源码/版本历史**（但 transit 时出现在请求 URL 查询串，见 §8 暴露点更正） |
| 14:25 | 本地 `tools/.ts_selfcheck.json` 同步 T2；STATE 升 v6.10（邮件2 为 v6.10 摘录，非完整 758 行） | 活动令牌 = T2 |

## 2. v142 / v143 源码与部署核验结果（只读，2026-09-27T13:56）
- **v142**：`GET /content?versionNumber=142` → **11 文件**；含 `token_rotate_tmp.js`
  - 该文件含 `setProperty('REMOTE_TOKEN', '<literal>')`，字面量为 **64 字符 urlsafe**（新令牌 T1 明文落入版本历史）
  - **结论：v142 暴露成立**
- **v142 部署绑定**：`GET /deployments` → 16 个部署；v142 **未绑定任何活动部署**（生产 Web App 绑定 v143；v142 不在任何部署的 versionNumber 中）
  - 含义：v142 不可经部署入口调用，但源码可被具项目编辑/所有者权限者读取
- **v143**：`GET /content?versionNumber=143` → **10 文件**；无 `token_rotate_tmp`；即当前 HEAD 干净版本
- **生产部署当前 = v143**（Web App URL 不变）

## 3. 旧令牌失效记录
- T0（首次轮换前旧值）readRange → `{"ok": false, "error": "Invalid or missing token"}`
- T1（首次轮换后活动值，曾落入 v142 明文）readRange → `{"ok": false, "error": "Invalid or missing token"}`（再轮换后已失效）
- T2（当前活动值）readRange → `{"ok": true}`
- 本地 `tools/.ts_selfcheck.json` 用 T2 实读 → `{"ok": true}`
- 说明：T0、T1 失效由两次 `setProperty` 覆写保证；T0 字面量仍存于 v135–v141 版本历史（均未绑定部署），T1 字面量存于 v142（均未绑定部署，T1 现已失效）

## 4. 本地令牌文件访问控制情况
- **文件**：`tools/.ts_selfcheck.json`（项目工作区内，Rita 本机）
- **当前工作副本**：含 `token` 字段（活动值 T1），`git status` = **已修改未提交**（T1 未进入任何 git 提交）
- **Git 跟踪问题**：该文件虽列于 `.gitignore`（line 6），但因曾提交（commit a64434b / 06432db / 7c0a10b）**仍被 git 跟踪**；历史提交中含一个 22 字符旧令牌值
  - 风险：令牌被纳入版本库历史；建议 `git rm --cached` 取消跟踪 + 历史擦除（BFG / filter-repo），或保持忽略后不再提交
- **权限**：`-rw-r--r--`，owner rita.jin（本机其他本地用户可读）
- **IMA**：未推送到任何 IMA 知识库（遵循 Tom 交付规则）
- **红线**：令牌值未打印、未进日志、未进 IMA；临时生成文件 `_tmp/.newtok` 与 oauth 缓存已删

## 5. 残留风险与建议处置
- **v142 含 T1 明文**：建议 (a) 再轮换到 T2（参数传入法，T2 不进源码/版本历史）；(b) Rita 在 **GAS 编辑器 Project History 手动删除 v142**（UI 支持未绑定版本删除，含批量；REST API 无 delete 方法，agent 无法自动化）
- **v135–v141 含旧令牌 T0 字面量**：可一并批量删除（均未绑定部署）
- **readRange 万能钥匙架构**：`ts_selfcheck.json` 的 readRange 接受任意 ssid，仅依赖令牌保密；轮换不改设计，建议后续收紧 ssid 白名单（独立改造，需授权）
- **版本删除前提**：REST API 无 `delete` 方法（仅 `create/get/list`）；仅编辑器 UI 可删未绑定版本；**非"只能删库"**

## 6. 授权范围说明（应 Tom 指正）
- 本次 `production_write_approved` 0→1 仅指 **REMOTE_TOKEN 轮换**授权
- **不构成 T1-B 工时表 B 列修复的生产写入授权**；该 gate 维持 0（未部署 / 未 --apply / 未回滚 / 未操作触发器）
- 再轮换 T2 与删除 v142 为新的生产动作，须 Rita 另行授权

## 7. 再轮换设计（T2，避免令牌进源码/历史）
- 临时 handler 从 POST 参数读取新令牌并 `setProperty`，**不在源码硬编码**
- 流程：快照 HEAD(v143) → 加参数式临时文件 → PUT → 建 v144 → 生产部署切 v144 → GET `?action=setremotetokenparam&token=<T1>&t=<T2>`（**T2 出现在 URL 查询字符串中，非 POST body**） → 验证 T1 失效 / T2 生效 → 恢复 HEAD(去临时文件) → 建 v143 之后版本（干净）→ 生产部署切回 → 本地文件同步 T2
- 结果：T2 仅存 Script Properties + 本地文件，**不进任何版本源码/历史**；v144 仅含无密钥的 handler（可后续 UI 删除）
- 删除 v142（及可选 v135–v141）由 Rita 在 GAS 控制台手动执行

## 8. 再轮换执行结果（2026-09-27T14:21，Rita 授权）
- **方法**：参数传入法，临时 handler `setRemoteTokenFromParam` 从请求参数 `e.parameter.t` 读取 T2（请求为 GET，故 `e.parameter.t` 即 URL 查询串中的 `t`）并 `setProperty`；T2 仅在进程内存生成（`secrets.token_urlsafe(48)`），**从未写入任何源码/版本历史**（但请求 URL 查询串含 T2，见下方暴露点更正）
- **版本轨迹**：HEAD(10文件) → 加参数 handler → **v144**(临时) → 部署 → GET `setremotetokenparam?token=T1&t=T2`（T2 在 URL 查询串） → 验证 → 恢复 HEAD(去 handler) → **v145**(干净) → 部署；生产 Web App URL 不变
- **验证（全过）**：
  - T1（旧，曾落 v142 明文）→ `Invalid or missing token` (ok=False) ✅ 已失效
  - T2（新）→ readRange `ok=True` ✅
  - HEAD = 10 文件，**0 处令牌明文** ✅
  - v144（临时版）= **0 处令牌明文**（仅参数 handler，无字面量）✅
  - 生产部署 = **v145**（干净版）✅
  - `setremotetokenparam` 临时动作已随 HEAD 恢复移除（unknown action）✅
- **安全结论**：**当前没有任何版本含活动令牌明文**。v142 仍含已**失效**的 T1 明文（残留，待手动 UI 删除）；v135–v141 含已失效的旧令牌明文（残留，待手动 UI 删除）
- **令牌红线**：T2 仅落 GAS Script Properties + 本地 `tools/.ts_selfcheck.json`；全程未打印、未进 git/IMA/日志
- **STATE.json 升 v6.10**：新增 `remote_token_rerotation` 块（本次邮件2 提供的是 v6.10 摘录，非 758 行完整文件）；`rotation` 块 verification/residual/v142_exposure.status 同步更新

## 9. 待 Rita 手动执行（agent 无法 API 自动化）
- **在 GAS 编辑器删除 v142、v135–v141**（均未绑定任何活动部署，UI 支持未绑定版本批量删除）：
  1. 打开 `finance_dss_backend` 项目 → 左侧 **「项目历史记录 / Project History」**
  2. 勾选 v142（含已失效 T1 明文）及 v135–v141（含已失效旧令牌明文）
  3. 点 **删除所选版本 / Delete**（批量删除按钮在列表上方）
  4. 确认删除；删除后这些版本从历史移除，**不影响当前生产 v145**
- 说明：REST API `projects.versions` 仅 `create/get/list`，无 delete 方法，故只能 UI 手动删；**非「只能删库」**
- **readRange 万能钥匙架构漏洞**（接受任意 ssid）仍为独立待改造项，本次未修

## 10. Tom 复核意见与待交负责人材料（2026-09-27T14:43 邮件，待逐项核验）

> Tom 已确认：令牌轮换授权与 T1-B B 列修复授权分开记录之口径正确。本审计记录与 STATE.json **v6.10 摘录**为其要求先行交付、供其独立核验的两份材料（**注意：本次仅提供 v6.10 摘录，未交付 758 行完整 STATE.json；摘录供口径核对，不能代替原始台账与操作证据**）。以下为其对 OPEN 项与数据恢复的逐项要求（agent 不替代负责人判断，仅代为整理待办清单）。

### 10.1 OPEN 项所需记录（每条须含：证据来源 / 采集时间 / 核验人 / 结论 / 仍未解决的限制；负责人可签收风险但不能替代缺失事实）
- **C4 正确生产基线**：生产负责人提供 09-24 至事件前的变更记录、当时生效的部署及源码依据，逐项确认恢复态是否保留合法变更；若无法重建事件前状态，记录「无法证明」并由负责人明确接受残余风险，**不得写成「已证明恢复正确」**。
- **业务数据影响**：提供事件前后可比的生产表快照及采集时间、行身份、关键字段差异结果，说明哪些变化来自正常业务、哪些无法归因；缺可比基线时结论继续「影响尚未核实」。
- **21:03 HEAD 是否物理含乱码**：现有证据不足；若无独立历史记录可补，以「无法判定」结案并由负责人签收，**不得改写为「无乱码」或「已证实损坏」**。
- **C5 未知部署**：由有权限的项目负责人确认该部署身份、用途、生效版本、访问范围，留存查询时间与原始记录；确认前 C5 继续 OPEN。
- **凭证事件**：提交本脱敏轮换审计记录，涵盖当前部署、临时入口关闭、旧值失效测试、本地凭证保护；历史版本处理与任意 ssid 读取问题另列负责人待办；**不得发送令牌原值**。

### 10.2 八月老数据 / 请假系统 / 九月完整性（均标记未决，不得合并成笼统结论）
- 目前无足够逐行对账证据确认三项已恢复或完整，亦不能确认「九月没有丢数据」。
- 须分别提交：来源数据、生产现状、行级差异、异常处置清单；对账完成前三项均标记未决。

### 10.3 未来任何 T1-B 业务数据写回的前置条件（审核意见 ≠ 生产授权）
- 先完成事件影响与正确基线核验，确定准确拟写范围；
- 再提交：逐行真值来源及目标行唯一绑定证据、明确 HOLD 清单、写前全表快照、现场重算结果、现存与候选间冲突检查、精确写入清单与 plan_id、触发器及其他写入入口的受控窗口方案、写后独立复读与异常停批/回滚方案；快照后漂移的行须重新审核。
- Tom 仅对具体证据包、精确清单、plan_id 给书面审核意见；Rita 再依公司权限对同一版本清单与 plan_id 单独作可留档的生产授权。**任一清单或现场状态变化都不能沿用原结论。**
- 当前 T1-B B 列修复批准数仍为 0。

### 10.4 当前待交付 / 待核验状态
- ✅ 已交付（本邮件）：脱敏轮换审计记录 + STATE.json v6.10 摘录（非 758 行完整文件）
- ⏳ 待 Tom 独立核验上述两份材料
- ⏳ 待负责人提交 10.1–10.2 材料后，Tom 逐项给出书面审核意见
- ⏳ T1-B 写回：须先满足 10.1–10.3 全部前置，且 Rita 单独授权（批准数 0→1）

## 11. Tom 复核后续（2026-09-27T15:02 邮件）— 已逐项更正

> Tom 15:02 复核指出三项须由 Rita／生产负责人处置并留档的事项；agent 不代行凭证操作、仅核验交付证据。以下为本次更正与处置结果（均不含令牌原值）。

### 11.1 凭证事件（tools/.ts_selfcheck.json）— 已处置
- **问题（Tom 原述）**：存放活动令牌 <T2> 的 `tools/.ts_selfcheck.json` 仍被 git 跟踪（虽 .gitignore 已列，但因曾提交故仍跟踪）、权限 `-rw-r--r--`；"未提交"不能保证后续不误提交，也不能视为已完成本机访问控制。
- **已执行**（Rita 授权，可逆）：
  - `git rm --cached tools/.ts_selfcheck.json _tmp/.ts_selfcheck.json tools/.ts_api_token.json` —— 取消跟踪（git status 现显示暂存删除 `D`，索引中不再含令牌文件）
  - Windows NTFS 上 `chmod 600` 不生效，改用 `icacls` **去除继承并仅授权 owner** `L-S-SH-26HH6\rita.jin:(R,W)`（仅本人可读写）
  - 补入 `.gitignore`（`_tmp/.ts_selfcheck.json`、`tools/.ts_api_token.json`）
  - 生成脱敏处置记录 `_tmp/t1b_delivery/credential_disposal_selfcheck_20260927.md`（含文件 sha256、历史提交清单，不含令牌值）
- **残留（待 Rita 决策）**：git 历史中 5 个 EOD backup 提交仍含旧令牌值；完整擦除需 git 历史重写（BFG / git filter-repo），属破坏性操作，**需 Rita 显式授权**。
- **已核实（2026-09-27 20:1x 补充，纠正此前"待确认"措辞）**：本机 `git rm --cached` 的暂存删除已由每日 EOD 自动备份提交 `b3eb22d`（18:30）最终定稿并推送远端（`HEAD == origin/main == a97b4d8…`），当前仓库树（本地 + 远端）均已不含令牌文件；`.gitignore` 第 6/7/8 行正确忽略三文件（已 `git check-ignore -v` 验证），后续 EOD 备份 `git add -A` 不会重新纳入 → 处置持久；活动令牌 T2 经全提交 blob 哈希比对确认**从未进入任何 git 提交**（处置成立）。历史 5 提交（`a64434b`/`06432db`/`7c0a10b`/`d50c974`/`656931c`，均为旧且已失效值）仍待负责人决策历史重写。脱敏证据见 `credential_git_evidence_20260927.md`。

### 11.2 再轮换请求构造 — 更正（T2 在 URL 查询串）
- **更正**：原审计"POST 参数 t"与"POST `setremotetokenparam(...)`"**不准确**。实测脚本第 117–118 行为：
  `q = urllib.parse.urlencode({'action':'setremotetokenparam','token':T1,'t':T2}); urllib.request.urlopen(WEBAPP + '?' + q)` —— **默认 GET 请求，T2 出现在 URL 查询字符串 `?...&t=<T2>` 中**，handler 用 `e.parameter.t`（GET 时即查询串）读取。
- **缓解（已确认）**：T2 从不进源码/版本历史（`secrets.token_urlsafe(48)` 内存生成）；脚本未打印请求 URL；handler 未记录参数。
- **未决限制（须如实披露，不得声称安全）**：无法证明 Google 服务端请求日志（若项目启用了 Cloud Logging / Executions 日志）未捕获该查询串；此点作为**残留风险**记录，不视为已闭环。

### 11.3 版本号统一 — 已更正
- 审计正文原"STATE 升 v6.9 / 已交付 v6.9"统一更正为 **v6.10**。
- 明确：**本次邮件2 仅提供 STATE.json v6.10 摘录（供口径核对），未交付 758 行完整 STATE.json**；摘录不能代替原始台账与操作证据。

### 11.4 维持结论
- 令牌轮换授权（rotation_write_approved=1）与 T1-B 修复授权（production_write_approved=0）严格分开。
- C4 / C5 / 业务数据影响 / 21:03 HEAD / 未知部署 等 OPEN 项维持原审核结论，无变化。
- T1-B 生产写入批准数仍为 **0**。

## 12. Tom 复核后续（2026-09-27T20:16 邮件）— 文件本体/SHA-256 交付 + 方案 v2 硬化

> Tom 20:16 指出：其本机仓库副本尚未取得 `_tmp/t1b_delivery/` 四份文件，故无法确认 Git 处置证据、STATE.json v6.12 或下一次轮换代码已通过复核；并进一步要求硬化下一次轮换方案。以下为落实（均不含令牌原值）。

### 12.1 文件本体与完整 SHA-256（交付渠道：GitHub 私有库 `ritajin-tech/SMCN_ERP-docs`，commit `a5257f5`；Tom 本机镜像需 `git pull` 同步）
- `REMOTE_TOKEN_rotation_audit_20260927.md`（本文件，含 §11–§12）— SHA-256 `13d74416e934b8c290f8cdf56db9a89b2353b0682ec2e719c78f80517693a37e`
- `STATE.json`（v6.12 台账，758 行，无令牌值）— SHA-256 `c3cb982eff3bcb841573f90773e000d8bedd4fb3c774646639a0989b353c03b8`
- `credential_git_evidence_20260927.md`（脱敏 Git 证据）— SHA-256 `ebc1305a4f93b8865655ef6e10a8caf6c287b6093cf5ce3eba047550b7faa179`
- `next_rotation_plan_20260927.md`（下一次轮换方案 **v2**，已硬化）— SHA-256 `fd14b616645820060abd7351ad290ea910a1387f8cf9c1061e2246ba1184f999`
- 注：上述 SHA-256 为交付时（v6.12/方案 v1）哈希；本节随 v6.13 重发后将更新为最终哈希。

### 12.2 取消跟踪与推送结论 — 维持"待核验"，历史旧值仍留 5 提交
- Tom 要求：取消跟踪与推送的结论**待其核验**；历史重写影响协作者与引用，须负责人单独决定，不得把 `git rm --cached` 表述为已清除仓库历史。
- 已如实记录：当前仓库树（本地+远端）已不含令牌文件，但 **5 个历史提交（`a64434b`/`06432db`/`7c0a10b`/`d50c974`/`656931c`）仍含旧（已失效）值**；清除需 filter-repo/BFG + 强制推送，属破坏性，待 Rita/负责人显式授权。

### 12.3 下一次轮换方案 v2 硬化（答复 Tom 四点）
方案 `next_rotation_plan_20260927.md` 已重写为 v2，逐条回应：
1. **一次性 HMAC 凭据**：操作员本机内存 CSPRNG 生成 `NONCE`/`NEW`；仅 `SHA256(NONCE)` 经 GAS 编辑器 UI 一次性写入 `rotation_nonce_hash`（服务端只存哈希，不存原值）；原子单用 = `ScriptLock` 串行 + 锁内"先删后做"（见 §1.3，残留风险据实披露）。
2. **实际脱敏代码**：调用方 `requests.post(URL, params={"action":...}, data=JSON{...})` 证明新令牌在 POST body、URL 无令牌；服务端 `doPost` 读 `e.postData.contents`；旧凭据校验 = `SHA256(body.nonce)` 比对 + 当前 `REMOTE_TOKEN` 须等于 `expected_old`（§2–§3.1）。
3. **全部署入口关闭核验**：仅删 HEAD handler 不足——须枚举所有部署（含版本钉部署）、读各版本源码 grep 轮换入口、主动探测每部署 URL 期望拒绝、确认无 `rotation_*` 残留属性（§4）。
4. **日志验收**：不关闭安全日志；代码层零日志 + 主动 Cloud Logging 查询断言 0 命中令牌 + 记录 IAM 日志读者范围（§5）。
- 方案 v2 仍**非生产授权**；须经 Rita/负责人单独授权后方可执行。

### 12.4 维持结论
- 令牌轮换授权（rotation_write_approved=1）与 T1-B 修复授权（production_write_approved=0）严格分开。
- C4 / C5 / 业务数据影响 / 21:03 HEAD / 未知部署 等 OPEN 项全部未变。
- 凭证事件维持 **OPEN**（T2 曾现于 URL 查询串、Google 服务端日志可见性未证伪）。
- **T1-B 生产写入批准数仍为 0**。

## 13. Tom 复核后续（2026-09-27T21:51 邮件）— 方案 v2 未过代码审核 → v3 重写 + 可读文件本体交付

> Tom 21:51 指出：方案 v2 暂不能通过代码审核，需补执行细节；且审计记录与完整 STATE.json 尚未在其本机取得，故四份文件哈希及操作记录仍待独立核验。要求先交付**脱敏实际代码、测试结果、审计与 STATE 可读本体**。以下为落实（均不含令牌原值）。

### 13.1 Tom 21:51 判定 v2 未过代码审核的四点 + v3 回应
1. **术语**：v2 称"一次性 HMAC 凭据"，示例实为随机 nonce + SHA-256 比对、**无 HMAC**。v3 统一改称**「一次性 SHA-256 nonce 能力（one-time SHA-256 nonce capability）」**，全文更正。
2. **实际代码 + 接入现有分发**：v2 示例 `function doPost(e){...}` 会**覆盖生产入口**。v3 改为——注册 `REMOTE_ACTIONS['rotate_remote_token']` + 在已有 `doPost` **顶部加一行** `_rtMaybeHandlePost(e)` hook（实测生产入口为 `_rtMaybeHandle`/`_rtMaybeHandlePost` → `REMOTE_ACTIONS[action]` 注册表；`doPost` 已能解析 `e.postData.contents` 为 body）。实际 `.gs` 与 `.py` 代码见 `rotation_action_actual.gs` / `rotate_remote_token_client.py`，并随本邮件内联。
3. **结果未知时的独立状态确认**：v2 在锁内"先删 nonce 再写令牌"，若旧值不符/写异常/超时则 nonce 已删，不能盲目重试。v3 新增 `rotationStatus` 只读指纹查询（`sha256(token|counter)`，不泄露令牌）；客户端 `_resolve_unknown` 在超时/响应丢失时**禁止直接重试写入**，改用指纹比对判定"已生效(NEW)/未轮换(OLD)"，仅当确认仍 OLD 且 capability 残值已清后才允许重备一次性凭据。
4. **全部署入口关闭核验 — 实测可运行**：v2 为示意代码。v3 改为已执行的只读枚举（Apps Script API GET，无写入）——本次实测 **16 个部署全部 clean、无任一钉在 v144**；附真实覆盖清单、四项失败标准、v144 防再绑定方法（轮换后删 v144 + 干净版本不含入口符号 + 枚举校验无部署引用 v144）。

### 13.2 日志验收范围（纠正"零命中=无留存"的过度解读）
- **来源**：GAS 执行日志位于关联 Google Cloud 项目的 Cloud Logging（`resource.type="app_script_function"`）。
- **权限**：需 `roles/logging.viewer` / `privateLogViewer` / `owner` / `editor`；验收同时列出具权主体，过宽则收窄。
- **时间范围**：轮换执行窗口 ±30 分钟。
- **查询式不以令牌为条件**：`textPayload:"rotate_remote_token" OR "new_token" OR "nonce"`，期望 0 命中（因代码零 `Logger.log`/`console.log` 引用请求体，T8 测试已证）。
- **限制（如实披露）**：①若 Cloud Logging 未启用，则"零命中"为**空真**，须注明无法从日志侧排除请求体被留存，不能据此声称闭环；②Apps Script 不自动捕获 URL/body，主防护是代码零日志 + 临时入口不存在；③**不将新令牌或其前缀填入搜索条件、不为此关闭安全日志**；④平台/网络层是否留存请求行属 GAS 平台侧，超出可控范围，列残留风险。

### 13.3 测试结果（本地逻辑仿真，17/17 PASS）
`rotation_logic_test.py` 纯逻辑层仿真（无真实凭据、不触生产）：T1 正常轮换/计数自增/写过即焚、T2 重放拒绝、T3 旧值不符作废、T4 无效 nonce、T5 超时→独立查询判 NEW 已生效、T6 未知态→判仍 OLD 可重备、T7 无 v144 绑定+生产在 HEAD clean、T8 代码零日志。范围限制：逻辑仿真非生产执行；真实轮换须经 Rita/负责人单独授权后在 GAS 端运行。

### 13.4 可读文件本体交付（回应"尚未取得"）
Tom 本机镜像此前未 `git pull`，故本次除 GitHub 推送外，**直接以邮件交付可读本体**：
- **审计记录**：本邮件内联（即本文件全文）。
- **STATE.json v6.14（82,179 B，无令牌值）**：以 **base64 附件**随本邮件发出（程序化生成，非手写，避免转抄损坏）；收件后可 `sha256sum` 比对下方哈希。
- **实际代码 + 测试**：`rotation_action_actual.gs` / `rotate_remote_token_client.py` / `rotation_logic_test.py` 随邮件附件或 GitHub 提供。

### 13.5 最终交付文件与完整 SHA-256（权威校验源，随本次推送/附件）
| 文件 | 大小 | SHA-256 |
|---|---|---|
| REMOTE_TOKEN_rotation_audit_20260927.md（本文件）| 25,775 B | 见随包 `REMOTE_TOKEN_rotation_audit_20260927.md.sha256` 侧车（自引用，本表不内嵌精确值以免偏差）|
| STATE.json（v6.14，无令牌值） | 82,179 B | 845876f8082eeda3d3d39b3cb85563d2547eaefff082ca2d7b47c2f8326989dc |
| credential_git_evidence_20260927.md | 5,037 B | ebc1305a4f93b8865655ef6e10a8caf6c287b6093cf5ce3eba047550b7faa179 |
| next_rotation_plan_v3_20260927.md | 17,752 B | f0ebe6b8c0965b48bf1f63e28087dd388084fece57f028e1a63ccc0c3a1c9182 |
> 注：上表为最终交付文件清单。审计文件自身哈希因含本表而自引用，故本表不内嵌其精确值，改由独立侧车 `REMOTE_TOKEN_rotation_audit_20260927.md.sha256` 承载权威校验值（收件后 `sha256sum -c` 即可）。STATE.json 行哈希为当前实测值，可直接校验。GitHub 私有库 `ritajin-tech/SMCN_ERP-docs` 同批推送（commit 见交付邮件正文）。

### 13.6 维持结论
- 令牌轮换授权（rotation_write_approved=1）与 T1-B 修复授权（production_write_approved=0）严格分开。
- C4 / C5 / 业务数据影响 / 21:03 HEAD / 未知部署 等 OPEN 项全部未变。
- 凭证事件维持 **OPEN**（T2 曾现于 URL 查询串、Google 服务端日志可见性未证伪）。
- 下一次轮换方案 v3 仍**待审核，非生产授权**；须经 Rita/生产负责人单独授权后方可执行。
- **T1-B 生产写入批准数仍为 0**。
