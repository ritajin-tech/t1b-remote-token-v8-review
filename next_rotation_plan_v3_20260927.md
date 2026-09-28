# 下一次 REMOTE_TOKEN 轮换 — 执行方案 v3（脱敏，供审核；非生产授权）

> 本方案为**待审核方案**，按 Tom 2026-09-27T21:51 复核意见重写，并据 2026-09-27T22:14 复审意见收紧 v144 与"全部署 clean"表述。
> 全文不含任何令牌原值；本方案不执行任何轮换，须经 Rita/生产负责人单独授权后方可执行。
> 相对 v2 的关键更正：①术语统一（无 HMAC，实为一次性 SHA-256 nonce 能力）②给出**实际可部署代码**并说明如何接入现有 `doPost` 分发（避免覆盖生产入口）③补"结果未知时如何独立确认状态、何时允许重备凭据、禁止未知态直接重试"④"全部署入口关闭核验"改为**实测可运行方法 + 真实部署清单（含逐项判定依据与采集时点）+ 失败标准 + v144 防再绑定（须授权人员操作并留存核验）**⑤说明日志来源/权限/时间范围/限制。
> 相对 v3 初版（22:0x）的收紧：§3 客户端代码补齐**四路径凭证交接**（成功/confirmed_new 写 NEW，拒绝/未知保留 OLD）；§5 标注采集时点、逐项判定依据（HEAD 直检 vs 版本钉死型推断）、探测仅击中鉴权门未触达副作用入口、v144 删除须授权人员操作并留存核验。

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

### 2.2 REMOTE_ACTIONS 注册（RemoteActions.gs 内追加一行）
```javascript
// 在 var REMOTE_ACTIONS = { ... } 内追加：
rotate_remote_token: function(e){ return tsRotateRemoteToken(e); },
rotationStatus:      function(e){ return tsRotationStatus(e); },   // 只读状态查询（独立确认用）
```

### 2.3 处理函数（新增，放在项目任意文件，例如 RemoteActions.gs 末尾）
```javascript
function tsRotateRemoteToken(e) {
  var props = PropertiesService.getScriptProperties();
  var body = (e && e.postBody) || {};
  var lock = LockService.getScriptLock();
  var locked = false;
  try { lock.waitLock(15000); locked = true; } catch (err) { locked = false; }
  if (!locked) return _rtResponse({ ok:false, error:'无法获取脚本锁，请稍后重试' });
  try {
    // (a) 一次性能力校验：SHA-256(nonce) 比对；锁内【先删后做】保证原子单用（非 HMAC）
    var stored = props.getProperty('rotation_nonce_hash');
    if (!stored) return _rtResponse({ ok:false, error:'capability 已消费或未设置' });
    var computed = _sha256(String(body.nonce || ''));
    if (computed !== stored) return _rtResponse({ ok:false, error:'capability 无效' });
    props.deleteProperty('rotation_nonce_hash');   // ← 用过即焚：第二次重放必然读到已删 → 拒绝
    // (b) 旧值校验：当前 REMOTE_TOKEN 必须等于 expected_old，否则中止（防并发/重放错位）
    if (props.getProperty('REMOTE_TOKEN') !== body.expected_old) {
      return _rtResponse({ ok:false, error:'当前令牌与预期旧值不符，已中止；capability 已作废' });
    }
    // (c) 写入新值 + 递增轮换计数（计数供独立状态查询，不泄露令牌）
    props.setProperty('REMOTE_TOKEN', String(body.new_token));
    var c = parseInt(props.getProperty('rotation_counter') || '0', 10) + 1;
    props.setProperty('rotation_counter', String(c));
    return _rtResponse({ ok:true, rotated:true, counter:c });
  } finally { lock.releaseLock(); }
}

// 只读状态查询：返回计数 + 令牌指纹（sha256(token|counter)，不泄露令牌本身）+ 是否仍有残留 capability
function tsRotationStatus(e) {
  var props = PropertiesService.getScriptProperties();
  var counter = parseInt(props.getProperty('rotation_counter') || '0', 10);
  var fp = _sha256((props.getProperty('REMOTE_TOKEN') || '') + '|' + counter);
  return _rtResponse({ ok:true, counter:counter, token_fingerprint:fp,
                       nonce_present: !!props.getProperty('rotation_nonce_hash') });
}

function _sha256(hexInput) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, hexInput, Utilities.Charset.UTF_8)
    .map(function(b){ return ('0'+(b&0xff).toString(16)).slice(-2); }).join('');
}
```
> 注：`_rtResponse` / `REMOTE_ACTIONS` / `_rtMaybeHandlePost` 均为项目已有符号，无需新增。
> 红线：§2.3 不得含任何 `Logger.log` / `console.log` 引用请求体/nonce/令牌（已通过 T8 测试）。

### 2.4 接入 doPost（仅加一行，非替换）
```javascript
function doPost(e) {
  var r = _rtMaybeHandlePost(e); if (r) return r;   // ← 新增这一行（接管的动作返回响应，其余请求继续原逻辑）
  // ... 原有 doPost 逻辑保持不变 ...
}
```

### 2.5 旧凭据如何校验（双因子）
- **一次性能力（授权）**：服务端存 `SHA256(nonce)`；调用方在 body 提交 `nonce`；服务端重算 `SHA256(body.nonce)` 与存储值比对（锁内 + 命中即删）。
- **旧 REMOTE_TOKEN（状态）**：调用方在 body 提交 `expected_old`；服务端确认当前 `REMOTE_TOKEN` == `expected_old` 才写入新值；若已被他人轮换则中止。
- 两者均在 **POST body**，均不进 URL、不进日志。

---

## 3. 实际客户端代码（POST 请求体，URL 零令牌；含四路径凭证交接）

> 以下为 `rotate_remote_token_client.py`（v3，sha256=`643186d8980f95749e09205767cc8bd02512cead4ec37082a05bfa53e9132201`）的同源精简副本。规范以该文件为准。

```python
import secrets, hashlib, json, os, requests

WEBAPP = "<DEPLOYMENT_URL>"          # 取自 tools/.ts_selfcheck.json 的 url；脱敏占位
OLD = "<CURRENT_REMOTE_TOKEN>"       # 轮换前活动令牌，运行前从本地凭据存储读入内存，不硬编码
# 获批客户端存放 REMOTE_TOKEN 的本地凭据存储（脱敏占位）。
# 红线：此路径含令牌，绝不进 git/IMA/日志/URL；仅本脚本在成功交接时原子覆盖 REMOTE_TOKEN 字段。
CREDENTIAL_STORE = "<LOCAL_CREDENTIAL_STORE_PATH>"

def _sha256_hex(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()

def _persist_new_token(new_token):
    """凭证交接（仅服务端已确认切换后调用）：把 NEW 原子写入本地凭据存储，覆盖 OLD。
    - 绝不在此发起或重试轮换写入。
    - 原子写：先写 .tmp 再 os.replace，避免半写导致本地存储损坏、客户端彻底失认证。
    - 不打印 / 不记录 new_token 任何值。
    - 若写入失败：抛异常，由调用方按恢复步骤处理（重试持久化或人工介入），绝不重发轮换请求。
    """
    with open(CREDENTIAL_STORE, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    cfg['REMOTE_TOKEN'] = new_token
    tmp = CREDENTIAL_STORE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f)
    os.replace(tmp, CREDENTIAL_STORE)

def rotate():
    NONCE = secrets.token_bytes(32)              # 一次性能力原始值，仅内存
    NEW = secrets.token_urlsafe(48)             # 新 REMOTE_TOKEN，仅内存
    nonce_hash = _sha256_hex(NONCE.hex())       # 应与 Script Properties 中 rotation_nonce_hash 一致
    payload = {
        "action": "rotate_remote_token",
        "token": OLD,                 # 既有 standing 凭据，用于通过 _rtMaybeHandle 门校验
        "nonce": NONCE.hex(),
        "expected_old": OLD,
        "new_token": NEW,
    }
    try:
        r = requests.post(WEBAPP, json=payload, timeout=15)
        resp = r.json()
    except Exception:
        return _resolve_unknown(NEW, OLD)       # 超时/响应丢失 → 独立确认，绝不在此直接重试写入

    if resp.get("ok") and resp.get("rotated"):
        # 成功路径：服务端已切 NEW → 交接 NEW 到本地配置（覆盖 OLD）。
        # 若本地写入失败：服务端已切换，绝不能重试轮换（会 rejected/重复），
        # 只能重试“持久化”或人工将 NEW 写入 CREDENTIAL_STORE。
        try:
            _persist_new_token(NEW)
        except Exception:
            return {"result": "rotated_server_but_persist_failed", "counter": resp.get("counter"),
                    "next": "重试 _persist_new_token(NEW) 或人工将 NEW 写入 CREDENTIAL_STORE；切勿重发轮换请求"}
        _discard(NONCE, NEW, OLD)
        return {"result": "rotated", "counter": resp.get("counter")}

    # 已知失败分支：capability 已消费 / 无效 / 旧值不符 → 不修改本地存储（保留 OLD），不重试写入
    _discard(NONCE, NEW, OLD)
    return {"result": "rejected", "error": resp.get("error")}

def _resolve_unknown(NEW, OLD):
    """结果未知时：用 rotationStatus（只读指纹）独立确认实际状态，绝不盲目重试写入。"""
    for cand in (OLD, NEW):
        try:
            r = requests.post(WEBAPP, json={"action": "rotationStatus", "token": cand}, timeout=15)
            st = r.json()
        except Exception:
            continue
        if not st.get("ok"):
            continue
        counter = st.get("counter")
        fp = st.get("token_fingerprint")
        if fp == _sha256_hex(NEW + "|" + str(counter)):
            # confirmed_new：NEW 已生效 → 交接 NEW 到本地配置
            try:
                _persist_new_token(NEW)
            except Exception:
                return {"result": "confirmed_new_persist_failed", "counter": counter,
                        "next": "重试 _persist_new_token(NEW) 或人工写入；切勿重发轮换请求"}
            _discard(None, NEW, None)
            return {"result": "confirmed_new", "counter": counter}   # NEW 已生效（之前写入成功）
        if fp == _sha256_hex(OLD + "|" + str(counter)):
            # 仍是 OLD，未轮换；此时才允许操作员清掉残留 capability 并重新准备一次性凭据
            return {"result": "confirmed_old_unrotated", "counter": counter,
                    "next": "清 rotation_nonce_hash 残值 → 重新生成 NONCE → 重写哈希 → 再发一次"}
    return {"result": "still_unknown", "next": "间隔后再次 rotationStatus；必要时人工核查 Script Properties"}

def _discard(NONCE, NEW, OLD):
    # 显式丢弃内存中的敏感变量，且本脚本不打印 r.url / r.request.body
    del NONCE, NEW, OLD
```

### 3.1 四路径凭证交接语义（Tom 复核要求）
客户端本地配置（`CREDENTIAL_STORE` 的 `REMOTE_TOKEN` 字段）的覆盖，**只在服务端已确认切换时发生**，四路径行为：

| 路径 | 服务端实际状态 | 本地配置动作 | 返回 result | 是否重发轮换 |
|---|---|---|---|---|
| **成功** `rotated` | 已切 NEW | 原子写 NEW 覆盖 OLD | `rotated` | 否（已成功） |
| **confirmed_new**（超时后独立查询确认 NEW 已生效） | 已切 NEW | 原子写 NEW 覆盖 OLD | `confirmed_new` | 否 |
| **拒绝** `rejected`（capability 无效/已消费/旧值不符） | 未切，仍为 OLD | **保留 OLD，不修改** | `rejected` | 否（须重备一次性凭据后另发） |
| **未知** `still_unknown`（status 也失败） | 不确定 | **保留 OLD，不修改** | `still_unknown` | 否（仅隔后重试 status 或人工核查） |

红线：本地持久化失败（`rotated_server_but_persist_failed` / `confirmed_new_persist_failed`）**绝不重发轮换请求**——服务端已切，重发必被 `rejected`；只能重试 `_persist_new_token` 或人工将 NEW 写入 `CREDENTIAL_STORE`。以上四路径已由 `rotation_logic_test.py` 的 T9–T12 本地仿真验证（见 §9）。

> 调用结束后丢弃 `NONCE/NEW/OLD` 本机变量；不打印 `r.url` / `r.request.body`。

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
- **发生时（轮换后）**：删除临时版本 v144，使其无法被任何部署钉死。**删除操作须由具备 GAS 项目编辑权限的授权人员执行**——优先在 GAS 编辑器 Project History 中删除（UI 支持删除未绑定活动部署的版本，含批量删除）；若经 API 删除，则**仅当该版本未绑定任何活动部署时** API 才允许（REST API 无删除方法，故 agent 无法自动化，须人工）。
- **核验留存**：删除 v144 后，**重新枚举 deployments + versions** 确认 v144 已从版本列表消失且无任何部署 `versionNumber == 144`，并将该核验结果（含采集时点、执行人）记录存档，作为闭环证据。
- **结构上**：临时轮换入口**只存在于临时版本 v144**，并在"切回干净版本"步骤即从 HEAD 移除 `REMOTE_ACTIONS['rotate_remote_token']` 与 `tsRotateRemoteToken`/`tsRotationStatus` 函数；干净版本（生产钉死版本）不含这些符号。
- **约束**：任何部署的 `versionNumber` 不得设为临时版本号；本方案执行后由 §5.1 枚举校验"无部署钉在 v144"。
- **实测现状（2026-09-27T22:0x +08）**：当前 16 个部署**无任何一个钉在 v144**（grep 144 = 0），故 v144 当前已不可被再绑定；删除 v144 为额外保险，须按上款由授权人员操作并留存核验。

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

## 9. 测试结果（本地逻辑仿真，26/26 PASS，2026-09-27T22:14 +08:00）
| 用例 | 结论 |
|---|---|
| T1 正常轮换 + 计数自增 + 新令牌写入 + capability 用过即焚 | PASS |
| T2 重放同 nonce → 拒绝（capability 已消费） | PASS |
| T3 旧值不符 → 拒绝且 capability 作废（锁内先删） | PASS |
| T4 无效 nonce → 拒绝（capability 不删，便于排查） | PASS |
| T5 超时/响应丢失 → 独立查询判定 NEW 已生效（不重试） | PASS |
| T6 未知态 → 独立查询判定仍 OLD（允许重备凭据） | PASS |
| T7 无部署钉在 v144（防再绑定）+ 生产在 HEAD 且 clean | PASS |
| T8 服务端代码零 Logger/console 日志调用 | PASS |
| T9 成功路径 → 本地存储写入 NEW（凭证交接） | PASS |
| T10 未知→确认 NEW 已生效 → 本地存储写入 NEW（凭证交接） | PASS |
| T11 拒绝路径 → 本地存储仍为 OLD（不交接） | PASS |
| T12 未知路径 → 本地存储仍为 OLD（不交接） | PASS |
> 范围限制：逻辑层仿真，非生产执行；真实轮换须经授权后在 GAS 端运行。完整输出见 `rotation_logic_test.py`（sha256=`aa9068a25354e617dea0be55ca62c10117baa52478f4a5e34a7736654e3d8a3b`）运行结果 26/26。客户端规范文件 `rotate_remote_token_client.py`（sha256=`643186d8980f95749e09205767cc8bd02512cead4ec37082a05bfa53e9132201`）。四路径交接语义见 §3.1。
