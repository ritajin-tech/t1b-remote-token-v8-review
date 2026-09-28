// ============================================================
// rotation_action_actual.gs  —— REMOTE_TOKEN 轮换【拟部署代码全文】（脱敏，供审核）
// 版本：v9（2026-09-28）—— 回应 Tom 第七轮复审（移除 trim：前/后空白一律拒绝，严格纯数字）
// ------------------------------------------------------------
// ⚠️ 本文件是"将要执行的代码"，并非已部署；须经 Rita/生产负责人单独授权后方可 PUT 进项目。
// 全文不含任何令牌原值；NONCE / NEW / OLD 由客户端运行期生成，从不进源码、从不进日志。
//
// 【v3 的真实缺陷（Tom 第 1 轮指出，已修正）】
//   v3 里处理函数写成 `return _rtResponse({ok:...})` —— 返回的是 ContentService 对象。
//   真实分发器 RemoteTrigger.gs 第 80–81 行：`result.message = String(out);`
//   ⇒ 对象被 String() 强转后变成 "[object Object]"，客户端拿不到 rotated / counter。
//   ✔ 正确合约（与既有 tsReadRange / tsAppendRows / tsPatchCells 一致）：
//       action 处理函数【必须 return JSON.stringify({...}) 字符串】。
//
// 【v5 相对 v4 的三处实质改动（Tom 第 3 轮）】
//   A. 竞态：新增 `rotation_inflight` 在途标记。轮换开始即置位、结束（finally）清除；
//      rotationStatus 暴露它。客户端【禁止】据单次"仍显示旧令牌"就判定"未轮换"——
//      必须 inflight=false 且连续两次稳定观测同 counter 才可终判（判定权在服务端标记 + 双观测）。
//   B. 归属：capability 增加 owner_id / 创建时间。轮换时 owner 必须存在且严格匹配才消费；
//      不匹配、或遗留 capability（哈希在、owner 空）⇒ 拒绝且【不删除】该 capability（不毁掉他人在途的准备）。
//   B2. TTL 消费校验：轮换消费时强制检查 capability 创建时间，过期请求拒绝且不改令牌，
//      过期 capability 一并清理，避免延迟到达的请求被复用。
//   B2.5（Tom 第五轮修正）失败关闭：创建时间缺失 / 为 0 / 非数字 / 无法解析 ⇒ 一律拒绝。
//      原 `if (created && …)` 在 created 缺失或 0 时会跳过 TTL 检查，遗留/损坏 capability 可被消费；
//      现改为「created 必须是正整数」且「未过期」双条件，否则拒绝并清理 capability。
//   B2.6（Tom 第六轮修正）严格解析：v7 的 `parseInt(createdRaw,10)` 仍会接受带数字后缀的非法值
//      （如 "1700000000000x" 解析成 1700000000000）、以及 0/NaN；而 `int(float(...))` 接受小数或科学计数法。
//      现改 `_parseStrictPositiveInt`：仅接受纯数字串（无符号/小数/指数/后缀）、>0、不超 safe-integer、
//      且不为未来时间；否则拒绝并清理 capability。负向测试：T26h/T26i/T26j/T26k、F7h/F7i/F7j/F7k。
//   C. 覆盖收紧：取消"客户端自动 force=true"这一不受限覆盖。允许覆盖的条件只剩三种：
//      ①同一 owner 的幂等重设；②已有 capability 已超过 TTL（默认 10 分钟，视为陈旧）；
//      ③操作员显式 force_over_foreign=true。且【任何情况下】只要 rotation_inflight 置位就拒绝。
// ============================================================

// ============================================================
// 1) 拟部署差异之一：RemoteActions.gs 的 REMOTE_ACTIONS 注册表新增 3 行
//    （真实文件：ts-manager / RemoteActions.gs，第 25 行 `probeCalendar: …` 之后补逗号、
//      第 26 行 `};` 之前插入）
//    机器可读 unified diff 见同包 `rotation_deploy_diff_20260928.patch`，
//    该 patch 由真实源文件生成，已用 `git apply --check` / `git apply` 实测。
// ------------------------------------------------------------
//   rotationStatus:        function(e) { return tsRotationStatus(e); },        // 只读状态查询（含 inflight）
//   setRotationCapability: function(e) { return tsSetRotationCapability(e); }, // 一次性能力热装（带 owner/TTL）
//   rotateRemoteToken:     function(e) { return tsRotateRemoteToken(e); },     // 执行轮换（在途标记 + 锁内先删后做）
//
//   ⚠️ 键名与客户端 action 的匹配规则：分发器第 76–78 行做
//      `String(_k).toLowerCase() === action`（action 已被第 36/120 行 lower 过）。
//      ⇒ 键 rotateRemoteToken 只能被 "rotateRemoteToken" / "rotateremotetoken" 等大小写变体命中；
//        客户端发 "rotate_remote_token"（下划线）会落到 "unknown action"（下划线不会被吃掉）。
//      正向 + 负向断言见 dispatch_sim_test.js 的 C 组（C1 命中 / C2 下划线未命中）。
// ============================================================

// ============================================================
// 2) 拟部署差异之二：新增文件 RotationActions.gs（以下为全文，直接新增，不改动任何既有函数）
//    放置位置：项目根，与 RemoteTrigger.gs / RemoteActions.gs 同级。
//    既有 doPost（Code.gs 第 135–140 行）已经是
//        function doPost(e) { var r = _rtMaybeHandlePost(e); if (r) return r; … }
//    ⇒ 【doPost 无需任何改动】；v3 方案里"给 doPost 加一行 hook"的说法对本项目不适用，已删除。
// ============================================================

var ROTATION_CAP_TTL_MS = 10 * 60 * 1000;   // capability 存活上限 10 分钟：超时视为陈旧，允许重建

function _nowMs() { return (new Date()).getTime(); }

/**
 * 严格解析"正整数毫秒时间戳"（v8 对 v7 的修正）。
 * 仅接受【纯数字字符串】（无符号 / 无小数 / 无指数 / 无后缀字母 / 无任何前后空白 — v9 起不做 trim），
 * 且 > 0、不超过 Number.MAX_SAFE_INTEGER、且不为未来时间；
 * 任何不满足 ⇒ 返回 null（调用方据此失败关闭）。
 * v7 的 `parseInt(createdRaw, 10)` 会接受 "1700000000000x"（带后缀）这类非法值；
 * 本函数杜绝此类绕过。
 */
function _parseStrictPositiveInt(raw, nowMs) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== 'string') raw = String(raw);
  // v9：【不做 trim】——任何前导/尾随空白都会让纯数字校验失败 ⇒ 返回 null（失败关闭）
  if (!/^[0-9]+$/.test(raw)) return null;          // 仅数字：拒符号/小数/指数/后缀/空白
  if (raw.length > 16) return null;                // 超出 safe-integer 位宽（快速拒）
  var n = parseInt(raw, 10);
  if (!(n > 0)) return null;                       // 0 或 NaN
  if (n > Number.MAX_SAFE_INTEGER) return null;    // 不安全整数
  if (n > nowMs) return null;                      // 未来时间戳（不可能由本系统生成）
  return n;
}

/**
 * (a) 一次性能力热装：写入 rotation_nonce_hash + 归属 owner + 创建时间。
 *     请求体：{"action":"setRotationCapability","token":OLD,"nonce_hash":"<64hex>",
 *              "expected_old":OLD,"owner_id":"<本次运行随机ID>"[,"force_over_foreign":"true"]}
 *     拒绝条件（任一）：
 *       · rotation_inflight 置位（有轮换在途）        → 拒（防打断/覆盖在途操作）
 *       · expected_old 与当前 REMOTE_TOKEN 不符        → 拒
 *       · nonce_hash 非 64 位小写十六进制              → 拒
 *       · 缺 owner_id                                  → 拒
 *       · 已存在 capability：既非同 owner、又未超 TTL、
 *         且未显式 force_over_foreign=true             → 拒（**不再接受无条件的 force**）
 */
function tsSetRotationCapability(e) {
  var props = PropertiesService.getScriptProperties();
  var body = (e && e.postBody) || {};
  var lock = LockService.getScriptLock();
  var locked = false;
  try { lock.waitLock(15000); locked = true; } catch (err) { locked = false; }
  if (!locked) return JSON.stringify({ ok: false, error: '无法获取脚本锁，请稍后重试' });

  try {
    if (props.getProperty('rotation_inflight')) {
      return JSON.stringify({ ok: false, error: '有轮换请求在途，拒绝设置/覆盖 capability',
                              inflight: true });
    }
    var cur = props.getProperty('REMOTE_TOKEN');
    if (String(body.expected_old || '') !== String(cur || '')) {
      return JSON.stringify({ ok: false, error: 'expected_old 与当前令牌不符，拒绝热装 capability' });
    }
    var h = String(body.nonce_hash || '');
    if (!/^[0-9a-f]{64}$/.test(h)) {
      return JSON.stringify({ ok: false, error: 'nonce_hash 必须是 64 位小写十六进制 SHA-256' });
    }
    var owner = String(body.owner_id || '');
    if (!owner) {
      return JSON.stringify({ ok: false, error: '缺少 owner_id（用于防止覆盖他人在途操作）' });
    }

    var existing = props.getProperty('rotation_nonce_hash');
    if (existing) {
      var exOwner = props.getProperty('rotation_capability_owner') || '';
      var created = _parseStrictPositiveInt(props.getProperty('rotation_capability_created'), _nowMs());
      var age = (created === null) ? (ROTATION_CAP_TTL_MS + 1) : (_nowMs() - created);
      var sameOwner = !!exOwner && exOwner === owner;
      var stale = age > ROTATION_CAP_TTL_MS;
      if (!sameOwner && !stale && String(body.force_over_foreign) !== 'true') {
        return JSON.stringify({
          ok: false,
          error: 'capability 已存在且属于另一笔操作，未覆盖；确认其已作废后带 force_over_foreign=true 重试',
          nonce_present: true, foreign: true, capability_age_ms: age
        });
      }
    }

    props.setProperty('rotation_nonce_hash', h);
    props.setProperty('rotation_capability_owner', owner);
    props.setProperty('rotation_capability_created', String(_nowMs()));
    // 只回显哈希/owner 指纹，不回显任何令牌
    return JSON.stringify({ ok: true, capability_set: true, nonce_present: true,
                            capability_ttl_ms: ROTATION_CAP_TTL_MS,
                            nonce_hash_fingerprint: _sha256(h).slice(0, 12),
                            owner_fingerprint: _sha256(owner).slice(0, 12) });
  } finally {
    lock.releaseLock();
  }
}

/**
 * (b) 执行轮换。请求体（POST，绝不经 URL）：
 *     {"action":"rotateRemoteToken","token":OLD,"nonce":"<nonce_hex>",
 *      "expected_old":OLD,"new_token":NEW,"owner_id":"<同上>","request_id":"<可选，便于追踪>"}
 *     前置：_rtMaybeHandle 已用 token 完成 standing 门校验（旧令牌鉴权在分发器里，不在本函数）。
 *     在途标记 rotation_inflight：进入即置位，finally 清除 —— 供"结果未知"时判断原请求是否仍在跑。
 */
function tsRotateRemoteToken(e) {
  var props = PropertiesService.getScriptProperties();
  var body = (e && e.postBody) || {};
  var lock = LockService.getScriptLock();
  var locked = false;
  try { lock.waitLock(15000); locked = true; } catch (err) { locked = false; }
  if (!locked) return JSON.stringify({ ok: false, error: '无法获取脚本锁，请稍后重试' });

  if (props.getProperty('rotation_inflight')) {
    return JSON.stringify({ ok: false, error: '已有轮换请求在途，本次未执行', inflight: true });
  }
  var reqId = String(body.request_id || '') || ('req_' + _nowMs());
  props.setProperty('rotation_inflight', reqId);       // ← 在途标记（先于删除 capability）
  try {
    var stored = props.getProperty('rotation_nonce_hash');
    if (!stored) return JSON.stringify({ ok: false, error: 'capability 已消费或未设置' });

    // (b0) 归属校验：capability 必须带 owner 且严格匹配。
    //      遗留 capability（哈希在、owner 为空）⇒ 视为归属缺失，拒绝且【不删除】，
    //      避免毁掉他人/不明来源在途的准备。
    var owner = props.getProperty('rotation_capability_owner') || '';
    if (!owner || String(body.owner_id || '') !== owner) {
      return JSON.stringify({ ok: false, error: 'capability 归属不匹配（或缺失），已中止（未消费该 capability）',
                              foreign: true });
    }

    // (b0b) TTL 校验（消费时强制，失败关闭）：原始创建时间必须是【严格正整数时间戳】
    //       —— 仅含数字、正、在 safe-integer 范围内、且不为未来时间；
    //       否则（缺失 / 格式错误 / 带后缀 / 小数 / 科学计数法 / 超范围 / 未来）一律拒绝、
    //       不改令牌、清理 capability 三键（免得被复用或绕过 TTL）。
    var createdRaw = props.getProperty('rotation_capability_created');
    var created = _parseStrictPositiveInt(createdRaw, _nowMs());
    if (created === null || (_nowMs() - created) > ROTATION_CAP_TTL_MS) {
      props.deleteProperty('rotation_nonce_hash');
      props.deleteProperty('rotation_capability_owner');
      props.deleteProperty('rotation_capability_created');
      var ttlMsg = (created === null)
        ? 'capability 创建时间缺失或无效（须为严格正整数时间戳，不含符号/小数/指数/后缀/空白），拒绝轮换（请重新热装 capability）'
        : 'capability 已过期，拒绝轮换（请重新热装 capability）';
      return JSON.stringify({ ok: false, error: ttlMsg, expired: true });
    }

    // (b1) 一次性能力校验：锁内【先删后做】，保证原子单用（非 HMAC）
    if (_sha256(String(body.nonce || '')) !== stored) {
      return JSON.stringify({ ok: false, error: 'capability 无效' });   // 无效 nonce：不删，便于排查
    }
    props.deleteProperty('rotation_nonce_hash');       // ← 用过即焚：第二次重放必然读到已删 → 拒绝
    props.deleteProperty('rotation_capability_owner');
    props.deleteProperty('rotation_capability_created');

    // (b2) 旧值校验：当前 REMOTE_TOKEN 必须等于 expected_old，否则中止（防并发/错位）
    if (props.getProperty('REMOTE_TOKEN') !== body.expected_old) {
      return JSON.stringify({ ok: false, error: '当前令牌与预期旧值不符，已中止；capability 已作废' });
    }

    // (b3) 写入新值 + 递增轮换计数（计数与指纹供独立状态查询，不泄露令牌）
    props.setProperty('REMOTE_TOKEN', String(body.new_token));
    var c = parseInt(props.getProperty('rotation_counter') || '0', 10) + 1;
    props.setProperty('rotation_counter', String(c));

    // ✔ 返回 JSON 字符串（不是对象、不是 ContentService）：见文件头 v3 缺陷说明
    return JSON.stringify({ ok: true, rotated: true, counter: c, request_id: reqId });
  } finally {
    props.deleteProperty('rotation_inflight');         // ← 无论成功/失败/异常，在途标记都要清除
    lock.releaseLock();
  }
}

/**
 * (c) 只读状态查询。请求体：{"action":"rotationStatus","token":<候选令牌>}
 *     ⚠️ 走分发器的标准令牌门：用错的令牌查询 ⇒ 外层 ok:false（据此判定"该候选未生效"）。
 *     返回：
 *       counter / token_fingerprint = sha256(token|counter)（不泄露令牌）
 *       inflight      —— 是否有轮换请求在途（客户端据此不得终判"未轮换"）
 *       inflight_id   —— 在途请求 ID（脱敏追踪用）
 *       nonce_present / capability_age_ms / owner_fingerprint —— capability 状态（供冲突判断）
 */
function tsRotationStatus(e) {
  var props = PropertiesService.getScriptProperties();
  var counter = parseInt(props.getProperty('rotation_counter') || '0', 10);
  var fp = _sha256((props.getProperty('REMOTE_TOKEN') || '') + '|' + counter);
  var created = _parseStrictPositiveInt(props.getProperty('rotation_capability_created'), _nowMs());
  var owner = props.getProperty('rotation_capability_owner') || '';
  var inflight = props.getProperty('rotation_inflight');
  return JSON.stringify({
    ok: true,
    counter: counter,
    token_fingerprint: fp,
    inflight: !!inflight,
    inflight_id: inflight || null,
    nonce_present: !!props.getProperty('rotation_nonce_hash'),
    capability_age_ms: created ? (_nowMs() - created) : null,
    owner_fingerprint: owner ? _sha256(owner).slice(0, 12) : null
  });
}

/** SHA-256 十六进制（与客户端 hashlib.sha256(...).hexdigest() 对齐；纯字符串输入）。 */
function _sha256(hexInput) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, hexInput, Utilities.Charset.UTF_8)
    .map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}

// ============================================================
// 3) 显式不做的事（v3 里的错误说法，逐条作废）
//    · ❌ 新增独立 function doPost(e){...}          → 会覆盖生产入口（Code.gs 第 135 行）
//    · ❌ 在既有 doPost 顶部再加一行分发调用          → 第 136 行已有，重复调用会二次解析
//    · ❌ 处理函数 return _rtResponse({...})         → 被 String() 变成 "[object Object]"
//    · ❌ 客户端自动 force=true 无条件覆盖 capability → v5 已改为三条件受限覆盖（见文件头 C）
//    · ❌ 把 nonce / new_token 放进 URL query         → 一律走 POST body
// ============================================================

// ============================================================
// 4) 客户端读取约定（必须遵守，否则成功路径拿不到 rotated）
//    服务端 _rtResponse(result) 的整体结构是：
//      { "ok": true,                     // ① 外层：令牌门 + 无异常。令牌错 ⇒ ok:false + error
//        "action": "rotateremotetoken", "version": "RT1.0", "ts": "...",
//        "message": "{\"ok\":true,\"rotated\":true,\"counter\":1}" }   // ② 内层：业务载荷（字符串！）
//    ⇒ 客户端：outer["ok"] 判门；inner = json.loads(outer["message"]) 取载荷；
//      message 以 "unknown action" 开头 ⇒ 动作名未命中（非 JSON，需先判可解析性）。
//    本约定已在 dispatch_sim_test.js 中用真实 RemoteTrigger.gs / RemoteActions.gs 源码实测。
// ============================================================
