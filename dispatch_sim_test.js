// ============================================================
// dispatch_sim_test.js —— 用【真实 GAS 分发源码】仿真验证 REMOTE_TOKEN 轮换接入
// 生成方式：由 _gen_dispatch_sim.py 从真实文件自动嵌入（零手抄）
//   · 嵌入的真实分发器 RemoteTrigger.gs  SHA-256(LF) = 9064d772cb89bf98796dba03b331914e4dcbd4e3109daefca1932c1921ae960e
//   · 嵌入的真实 doPost（Code.gs 第 135-140 行）
//   · 嵌入的拟部署处理函数（rotation_action_actual.gs 第 2 节）SHA-256(LF) = 9827aca1a09de5e392a5bade84bdfe8ed5ccd2dd35a990ac7b72413a9fd6c943
//   · REMOTE_ACTIONS 键名取自打补丁后的真实注册表（22 个，新增 3 个）
// 运行：node dispatch_sim_test.js    退出码：0=全通过 1=有失败 2=自检失败（嵌入源缺失/被改）
// 红线：全程 mock，无网络、无真实令牌、不触生产。
// ============================================================
const vm = require('vm');
const crypto = require('crypto');

// ---------- 嵌入的真实源码（逐字，来自生产只读副本） ----------
const REMOTE_TRIGGER_SRC = `// ============================================================
// RemoteTrigger.gs  v1.0  —  SMCN 标准化「手机远程触发」helper
// ------------------------------------------------------------
// 让任意 GAS 项目获得手机/云端 Web App 触发能力（复制到项目根即可）。
//
// 接入步骤：
//   1) 复制本文件到项目根目录
//   2) 新建 RemoteActions.gs，定义：
//        var REMOTE_ACTIONS = {
//          myaction: function(){ /* ... */ return "完成提示"; }
//        };
//        function doGet(e){
//          var r = _rtMaybeHandle(e); if (r) return r;   // ← 接管远程触发
//          /* 你原本的 doGet 逻辑（没有就返回状态 JSON） */
//        }
//      （若项目已有 doGet，把第一行改成调用 _rtMaybeHandle 即可，原逻辑放后面）
//   3) 在 onOpen 菜单加：.addItem('📱 生成手机远程链接','showRemoteTriggerLinks')
//   4) 部署为 Web App（执行身份=我；访问=仅自己 或 任何人/匿名）
//
// 安全：首跑自动生成 REMOTE_TOKEN 存 Script Properties；调用须带 ?token=
// 触发：<WEBAPP_URL>?action=<动作>&token=<token>
//       内置动作：status（看状态）、_seturl（注册真实 URL，供菜单显示）
// ============================================================
var RT_VERSION = "RT1.0";

// 👇 REMOTE_WEBAPP_URL 由各系统的 RemoteActions.gs 定义（部署后的真实 Web App URL）。
//    运行时优先读取 Script Properties REMOTE_WEBAPP_URL（由 ?action=_seturl 写入，可热更新），
//    其次取本常量，最后才用 scriptId 推导（仅供示意，scriptId ≠ 部署ID，需校正）。
//    故此处不再声明该变量，避免与 RemoteActions.gs 的赋值冲突。

/**
 * 核心分发。返回 ContentService 响应；若无 action 参数则返回 null（调用方继续原有逻辑）。
 */
function _rtMaybeHandle(e) {
  e = e || {};
  var action = String(e.parameter.action || "").toLowerCase();
  if (!action) return null;

  var props = PropertiesService.getScriptProperties();
  var expected = props.getProperty("REMOTE_TOKEN");
  var isFirstRun = false;
  if (!expected) {
    expected = "SMCN-" + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMdd") + "-" + _rtMakeShortToken(6);
    props.setProperty("REMOTE_TOKEN", expected);
    isFirstRun = true;
  }

  var ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
  var token = String(e.parameter.token || "");

  if (token !== expected) {
    var errObj = {
      ok: false,
      error: "Invalid or missing token",
      hint: isFirstRun ? "Token initialized on first run. Open sheet menu '📱 生成手机远程链接' to view it." : undefined,
      ts: ts
    };
    // 首跑时一次性把刚生成的 token 回显，便于手机/云端首次配置（之后不再泄露）
    if (isFirstRun) errObj.token = expected;
    return _rtResponse(errObj);
  }

  var result = { ok: true, action: action, version: RT_VERSION, ts: ts };
  try {
    if (action === "status") {
      result.message = "ok";
      result.actions = _rtActionList();
    } else if (action === "_seturl") {
      var u = String(e.parameter.url || "").trim();
      if (u) { props.setProperty("REMOTE_WEBAPP_URL", u); result.message = "REMOTE_WEBAPP_URL saved"; }
      else { result.ok = false; result.error = "missing url param"; }
    } else if (typeof REMOTE_ACTIONS === "object") {
      // 大小写不敏感查找：分发器早期把 action .toLowerCase()，但 REMOTE_ACTIONS 键是混合大小写
      // (checkLeaves/syncLeaves/cleanupLeaves/setupAmy/testAmySelf)，直接查会全部 miss。线性找一次即可。
      var _rtKey = null;
      for (var _k in REMOTE_ACTIONS) {
        if (String(_k).toLowerCase() === action && typeof REMOTE_ACTIONS[_k] === "function") { _rtKey = _k; break; }
      }
      if (_rtKey) {
        var out = REMOTE_ACTIONS[_rtKey](e);
        if (out !== undefined && out !== null) result.message = String(out);
      } else {
        result.message = "unknown action: " + action + ". available: " + _rtActionList().join(", ");
      }
    } else {
      result.message = "unknown action: " + action + ". available: " + _rtActionList().join(", ");
    }
  } catch (err) {
    result.ok = false;
    result.error = err.message;
  }
  return _rtResponse(result);
}

/** 列出所有可用动作（含内置）。 */
function _rtActionList() {
  var list = ["status", "_seturl"];
  if (typeof REMOTE_ACTIONS === "object") {
    for (var k in REMOTE_ACTIONS) {
      if (typeof REMOTE_ACTIONS[k] === "function" && list.indexOf(k) < 0) list.push(k);
    }
  }
  return list;
}

/**
 * V4.3.62 POST 分发 —— 与 _rtMaybeHandle 共用同一套 token 校验与动作分发，
 * 额外把解析后的 JSON body 挂在 e.postBody 上供动作函数读取（appendRows / patchCells 用）。
 * 返回 ContentService 响应；body 无 action 时返回 null（调用方继续原有逻辑）。
 */
function _rtMaybeHandlePost(e) {
  e = e || {};
  var body = {};
  try {
    if (e.postData && e.postData.contents) body = JSON.parse(e.postData.contents);
    else if (e.parameter && e.parameter.payload) body = JSON.parse(e.parameter.payload);
  } catch (err) {
    return _rtResponse({ ok: false, error: 'invalid JSON body: ' + ((err && err.message) || err) });
  }
  var action = String(body.action || (e.parameter && e.parameter.action) || '').toLowerCase();
  if (!action) return null;

  var params = {};
  var src = e.parameter || {};
  for (var k in src) params[k] = src[k];
  for (var k2 in body) { if (typeof body[k2] !== 'object') params[k2] = body[k2]; }
  params.action = action;
  if (!params.token && body.token) params.token = body.token;

  return _rtMaybeHandle({ parameter: params, postBody: body });
}

/** 统一 JSON 响应。 */
function _rtResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** 生成短随机 token 后缀。 */
function _rtMakeShortToken(len) {
  var chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  var out = "";
  for (var i = 0; i < len; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
  return out;
}

/**
 * 菜单入口：显示当前 Web App URL + 各 action 的完整远程触发链接。
 * URL 优先取 Script Properties REMOTE_WEBAPP_URL（部署后由 _seturl 写入），
 * 其次取本文件常量 REMOTE_WEBAPP_URL，最后用 scriptId 推导（示意，需校正）。
 */
function showRemoteTriggerLinks() {
  var ui = SpreadsheetApp.getUi();
  if (!ui) return;
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty("REMOTE_TOKEN");
  if (!token) {
    token = "SMCN-" + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyyMMdd") + "-" + _rtMakeShortToken(6);
    props.setProperty("REMOTE_TOKEN", token);
  }
  var url = props.getProperty("REMOTE_WEBAPP_URL") || REMOTE_WEBAPP_URL ||
            ("https://script.google.com/a/macros/spacematrix.com/s/" + ScriptApp.getScriptId() + "/exec");
  var actions = _rtActionList().filter(function(a) { return a !== "_seturl"; });
  var links = "";
  actions.forEach(function(a) {
    var u = url + "?action=" + a + "&token=" + token;
    links += '<p><b>' + a + ':</b><br><a href="' + u + '" target="_blank">' + u + '</a></p>';
  });
  var html = '<h3>📱 SMCN 远程触发链接</h3>' +
    '<p><b>Web App URL:</b><br><code>' + url + '</code></p>' +
    '<p><b>Token:</b> <code>' + token + '</code></p><hr>' + links +
    '<p style="color:#666;font-size:12px;">把常用链接收藏到手机浏览器书签，或发给 WorkBuddy 手机端。' +
    'Token 存在 Script Properties，换设备也通用。如菜单链接打不开，说明 Web App URL 未校正，' +
    '点一次「部署」后在手机或电脑执行一次 <code>?action=_seturl&url=&lt;真实URL&gt;</code> 即可。</p>';
  ui.showModalDialog(HtmlService.createHtmlOutput(html).setWidth(700).setHeight(480), '📱 远程触发链接');
}
`;

const REAL_DOPOST_SRC = `function doPost(e) {
  var r = _rtMaybeHandlePost(e);
  if (r) return r;
  return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'no action in POST body' }))
           .setMimeType(ContentService.MimeType.JSON);
}`;

const ROTATION_HANDLERS_SRC = `var ROTATION_CAP_TTL_MS = 10 * 60 * 1000;   // capability 存活上限 10 分钟：超时视为陈旧，允许重建

function _nowMs() { return (new Date()).getTime(); }

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
        ? 'capability 创建时间缺失或无效（须为严格正整数时间戳，不含符号/小数/指数/后缀），拒绝轮换（请重新热装 capability）'
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


function _sha256(hexInput) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, hexInput, Utilities.Charset.UTF_8)
    .map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}
`;

const ALL_KEYS = ["refreshqs", "exception", "archive", "setup", "setupAmy", "testAmySelf", "cleanupLeaves", "syncLeaves", "checkLeaves", "readRange", "appendRows", "patchCells", "snapshot", "trimblank", "dupreport", "driveList", "purgeSoftLeaves", "purgeRows", "probeCalendar", "rotationStatus", "setRotationCapability", "rotateRemoteToken"];
const NEW_KEYS = ["rotationStatus", "setRotationCapability", "rotateRemoteToken"];
const OLD_KEYS = ALL_KEYS.filter(k => NEW_KEYS.indexOf(k) < 0);

// ---------- 自检：嵌入源必须完整（fail-closed） ----------
function selfCheck() {
  const need = [
    ['RemoteTrigger.gs 含 _rtMaybeHandle(e)', REMOTE_TRIGGER_SRC.includes('function _rtMaybeHandle(e)')],
    ['RemoteTrigger.gs 含 _rtMaybeHandlePost(e)', REMOTE_TRIGGER_SRC.includes('function _rtMaybeHandlePost(e)')],
    ['RemoteTrigger.gs 含 String(out) 强转', REMOTE_TRIGGER_SRC.includes('result.message = String(out);')],
    ['真实 doPost 已调用 _rtMaybeHandlePost', REAL_DOPOST_SRC.includes('_rtMaybeHandlePost(e)')],
    ['处理函数含 JSON.stringify 返回', ROTATION_HANDLERS_SRC.includes('return JSON.stringify(')],
    ['处理函数不含 _rtResponse 误用', !ROTATION_HANDLERS_SRC.includes('_rtResponse(')],
    ['新增 3 键齐全', NEW_KEYS.length === 3 && NEW_KEYS.every(k => ALL_KEYS.includes(k))],
  ];
  let bad = need.filter(x => !x[1]).map(x => x[0]);
  if (bad.length) { console.error('SELF-CHECK FAILED: ' + bad.join(' | ')); process.exit(2); }
  return true;
}
selfCheck();

// ---------- GAS 服务 mock ----------
function makeProps(init) {
  const d = Object.assign({}, init || {});
  return {
    getProperty: k => (k in d ? d[k] : null),
    setProperty: (k, v) => { d[k] = String(v); },
    deleteProperty: k => { delete d[k]; },
    _dump: () => d,
  };
}
function sha256hex(s) { return crypto.createHash('sha256').update(s, 'utf8').digest('hex'); }

function buildSandbox(props) {
  const calls = [];
  const sb = {
    console,
    // PropertiesService
    PropertiesService: { getScriptProperties: () => props },
    // Utilities
    Utilities: {
      DigestAlgorithm: { SHA_256: 'SHA_256' },
      Charset: { UTF_8: 'UTF_8' },
      // 真实语义：返回 SHA-256 摘要字节（GAS 返回有符号字节数组）
      computeDigest: (alg, input) => Array.from(crypto.createHash('sha256').update(String(input), 'utf8').digest())
        .map(b => (b > 127 ? b - 256 : b)),
      formatDate: (d, tz, fmt) => '2026-09-28 12:00:00',
    },
    // ContentService：只需要拿到最终 JSON 文本
    ContentService: {
      MimeType: { JSON: 'JSON' },
      createTextOutput: s => ({ getContent: () => s, setMimeType() { return this; } }),
    },
    LockService: { getScriptLock: () => ({ waitLock() { return true; }, releaseLock() {} }) },
    Session: { getScriptTimeZone: () => 'GMT+8' },
    Logger: { log() {} },
    __clock: 1000000,
    __calls: calls,
  };
  return sb;
}

// 组装 sandbox：真实分发器 + 真实 doPost + 拟部署处理函数 + 真实键名注册表
// 既有 19 个 action 用探针桩替代（只验证"分发是否仍正确路由到它们"，不触发真实副作用）；
// 新增 3 个 action 绑定【真实处理函数原文】。
function makeEnv(props) {
  const sb = buildSandbox(props);
  vm.createContext(sb);
  vm.runInContext(REMOTE_TRIGGER_SRC, sb);          // 真实分发器
  vm.runInContext(ROTATION_HANDLERS_SRC, sb);        // 拟部署处理函数
  vm.runInContext('_nowMs = function(){ return __clock; };', sb);   // 可控时钟（TTL 用例用）
  vm.runInContext(REAL_DOPOST_SRC, sb);              // 真实 doPost（验证无需改动即可工作）
  const regLines = ALL_KEYS.map(k => {
    if (k === 'rotationStatus') return '  rotationStatus: function(e) { return tsRotationStatus(e); },';
    if (k === 'setRotationCapability') return '  setRotationCapability: function(e) { return tsSetRotationCapability(e); },';
    if (k === 'rotateRemoteToken') return '  rotateRemoteToken: function(e) { return tsRotateRemoteToken(e); },';
    return '  ' + k + ': function(e) { __calls.push("' + k + '"); return JSON.stringify({ok:true, stub:"' + k + '"}); },';
  }).join('\n');
  vm.runInContext('var REMOTE_ACTIONS = {\n' + regLines + '\n};', sb);
  return sb;
}

// 走真实链路：doPost(e) → _rtMaybeHandlePost(e) → _rtMaybeHandle → REMOTE_ACTIONS
function post(sb, bodyObj, rawText) {
  const contents = rawText !== undefined ? rawText : JSON.stringify(bodyObj);
  const e = { postData: { contents }, parameter: {} };
  const out = sb.doPost(e);
  if (!out) return { __null: true };
  return JSON.parse(out.getContent());
}

// ---------- 断言 ----------
const results = [];
function check(name, cond, detail) {
  results.push([name, !!cond]);
  console.log((cond ? 'PASS' : 'FAIL') + ' - ' + name + (detail ? '  | ' + detail : ''));
}

const OLD = 'OLD_MOCK_TOKEN';
const NEW = 'NEW_MOCK_TOKEN_VALUE';
const NONCE_HEX = 'ab12cd34ef56ab12cd34ef56ab12cd34';
const NONCE_HASH = sha256hex(NONCE_HEX);
const OWNER = 'owner_unit_test';

// ============================================================
// A 组：POST body 解析（真实 _rtMaybeHandlePost）
// ============================================================
{
  const props = makeProps({ REMOTE_TOKEN: OLD, rotation_counter: '0' });
  const sb = makeEnv(props);
  // A1 body 里的 nonce_hash 能到达处理函数（证明 e.postBody 打通）
  let r = post(sb, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
                     expected_old: OLD, owner_id: OWNER });
  check('A1 POST body 被解析并挂到 e.postBody（capability 热装成功）',
    r.ok === true && r.message && JSON.parse(r.message).capability_set === true, JSON.stringify(r.message));
  // A2 token 来自 body 而非 URL
  const props2 = makeProps({ REMOTE_TOKEN: OLD, rotation_counter: '0' });
  const sb2 = makeEnv(props2);
  const r2 = post(sb2, { action: 'rotationStatus', token: OLD });
  check('A2 token 取自 POST body（URL 无任何参数亦可通过门）', r2.ok === true, JSON.stringify(r2));
  // A3 非法 JSON
  const r3 = post(sb2, null, '{not-json');
  check('A3 非法 JSON body → ok:false + invalid JSON body', r3.ok === false && /invalid JSON body/.test(r3.error || ''), JSON.stringify(r3));
  // A4 body 无 action → 分发器必须让位（_rtMaybeHandlePost 返回 null），由既有 doPost 兜底
  const e4 = { postData: { contents: JSON.stringify({ token: OLD, foo: 1 }) }, parameter: {} };
  const dispNull = sb2._rtMaybeHandlePost(e4);
  check('A4 body 无 action → 分发器让位（_rtMaybeHandlePost 返回 null）', dispNull === null, String(dispNull));
  const r4 = post(sb2, { token: OLD, foo: 1 });
  check('A4b 随后由【既有】doPost 自身兜底（no action in POST body），未被分发器劫持',
    r4.ok === false && /no action in POST body/.test(r4.error || ''), JSON.stringify(r4));
}

// ============================================================
// B 组：旧令牌鉴权（分发器前置，处理函数内不重复实现也不绕过）
// ============================================================
{
  const props = makeProps({ REMOTE_TOKEN: OLD, rotation_counter: '0', rotation_nonce_hash: NONCE_HASH,
                           rotation_capability_owner: OWNER,
                           rotation_capability_created: '1000000' });  // 对齐 mock 时钟 __clock=1000000：有效且未过期
  const sb = makeEnv(props);
  // B1 错误令牌 → 拒绝，且处理函数未被调用（capability 未被消费）
  const r = post(sb, { action: 'rotateRemoteToken', token: 'WRONG_TOKEN', nonce: NONCE_HEX, expected_old: OLD, new_token: NEW });
  check('B1 错误令牌 → 外层 ok:false + Invalid or missing token',
    r.ok === false && /Invalid or missing token/.test(r.error || ''), JSON.stringify(r));
  check('B1b 错误令牌 → 处理函数未执行（capability 未被消费）',
    props.getProperty('rotation_nonce_hash') === NONCE_HASH, 'nonce_hash 仍在');
  // B2 缺 token
  const r2 = post(sb, { action: 'rotateRemoteToken', nonce: NONCE_HEX, expected_old: OLD, new_token: NEW });
  check('B2 缺 token → 拒绝', r2.ok === false && /Invalid or missing token/.test(r2.error || ''), JSON.stringify(r2));
  // B3 正确 OLD → 通过；随后 OLD 失效
  const r3 = post(sb, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX, expected_old: OLD, new_token: NEW, owner_id: OWNER });
  const inner3 = JSON.parse(r3.message);
  check('B3 正确旧令牌 → 通过门并完成轮换', r3.ok === true && inner3.ok === true && inner3.rotated === true, JSON.stringify(r3));
  const r4 = post(sb, { action: 'rotationStatus', token: OLD });
  check('B4 轮换后用 OLD 查询状态 → 被门拒绝（旧值确已失效）', r4.ok === false, JSON.stringify(r4));
}

// ============================================================
// C 组：action 名匹配规则（正向 + 负向）
// ============================================================
{
  const props = makeProps({ REMOTE_TOKEN: OLD, rotation_counter: '3' });
  const sb = makeEnv(props);
  const r1 = post(sb, { action: 'rotationStatus', token: OLD });
  check('C1 camelCase "rotationStatus" 命中真实处理函数', r1.ok === true && JSON.parse(r1.message).ok === true, JSON.stringify(r1.message));
  const r2 = post(sb, { action: 'rotation_status', token: OLD });   // 下划线：负向
  check('C2 下划线 "rotation_status" → unknown action（证明下划线不会被吃掉）',
    r2.ok === true && /^unknown action/.test(r2.message || ''), JSON.stringify(r2.message));
  const r3 = post(sb, { action: 'rotationstatus', token: OLD });    // 全小写：大小写不敏感
  check('C3 全小写 "rotationstatus" 命中（大小写不敏感查找生效）', r3.ok === true && JSON.parse(r3.message).ok === true, JSON.stringify(r3.message));
}

// ============================================================
// D 组：其他 action 不受影响（既有 19 个 + 内置）
// ============================================================
{
  const props = makeProps({ REMOTE_TOKEN: OLD, rotation_counter: '0' });
  const sb = makeEnv(props);
  const probe = OLD_KEYS[OLD_KEYS.indexOf('driveList') >= 0 ? OLD_KEYS.indexOf('driveList') : 0];
  const r1 = post(sb, { action: probe, token: OLD });
  check('D1 既有 action（' + probe + '）仍被正确路由',
    r1.ok === true && JSON.parse(r1.message).stub === probe, JSON.stringify(r1.message));
  check('D1b 既有 action 未被误触发其它分支', sb.__calls.filter(c => c === probe).length === 1, '调用次数=1');
  const r2 = post(sb, { action: 'status', token: OLD });
  check('D2 内置 status 仍可用且列出全部动作', r2.ok === true && Array.isArray(r2.actions), JSON.stringify(r2.actions && r2.actions.length));
  check('D2b status 列表包含新增 3 个动作',
    NEW_KEYS.every(k => r2.actions.indexOf(k) >= 0), JSON.stringify(NEW_KEYS));
  check('D2c 动作总数 = 内置2 + 注册表' + ALL_KEYS.length + ' = ' + (2 + ALL_KEYS.length),
    r2.actions.length === 2 + ALL_KEYS.length, '实际=' + r2.actions.length);
  const r3 = post(sb, { action: 'noSuchAction', token: OLD });
  check('D3 未知 action → unknown action 提示（不报错、不影响其它）', /^unknown action/.test(r3.message || ''), JSON.stringify(r3.message));
  // D4：证明 String(out) 是【既有】约定——若某 action 返对象，同样被强转成 [object Object]
  const sb2 = makeEnv(makeProps({ REMOTE_TOKEN: OLD, rotation_counter: '0' }));
  vm.runInContext('REMOTE_ACTIONS.readRange = function(){ return {ok:true}; };', sb2);
  const r4 = post(sb2, { action: 'readRange', token: OLD });
  check('D4 既有约定复现：返回对象会被 String() 变成 [object Object]（故必须返 JSON 字符串）',
    r4.message === '[object Object]', JSON.stringify(r4.message));
}

// ============================================================
// E 组：轮换四路径 + capability 热装（真实处理函数）
// ============================================================
function fresh(counter) {
  return makeProps({ REMOTE_TOKEN: OLD, rotation_counter: String(counter || 0) });
}
{
  // E1 正常轮换（含 owner 归属）
  let props = fresh(0);
  let sb = makeEnv(props);
  let a = post(sb, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
                     expected_old: OLD, owner_id: OWNER });
  check('E1a capability 热装成功（无需进编辑器手填）',
    JSON.parse(a.message).capability_set === true, JSON.stringify(a.message));
  let r = post(sb, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
                     expected_old: OLD, new_token: NEW, owner_id: OWNER });
  let inner = JSON.parse(r.message);
  check('E1b 成功路径：外层 ok=true 且 message 是可解析 JSON 字符串',
    r.ok === true && typeof r.message === 'string' && inner.ok === true, JSON.stringify(r));
  check('E1c 成功路径：rotated=true / counter=1 / 令牌已切 NEW',
    inner.rotated === true && inner.counter === 1 && props.getProperty('REMOTE_TOKEN') === NEW,
    JSON.stringify(inner));
  check('E1d capability 用过即焚', props.getProperty('rotation_nonce_hash') === null, '已删除');
  check('E1e 在途标记已清除（finally）', props.getProperty('rotation_inflight') === null, '已清除');

  // E2 重放
  let r2 = post(sb, { action: 'rotateRemoteToken', token: NEW, nonce: NONCE_HEX,
                      expected_old: NEW, new_token: 'X', owner_id: OWNER });
  check('E2 重放被拒（capability 已消费）',
    JSON.parse(r2.message).ok === false, JSON.stringify(r2.message));
  check('E2b 重放后令牌未被改', props.getProperty('REMOTE_TOKEN') === NEW);

  // E3 expected_old 不符 → 拒绝且 capability 作废
  let props3 = fresh(0); let sb3 = makeEnv(props3);
  post(sb3, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
              expected_old: OLD, owner_id: OWNER });
  let r3 = post(sb3, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
                       expected_old: 'WRONG_OLD', new_token: 'Z', owner_id: OWNER });
  check('E3 旧值不符被拒', JSON.parse(r3.message).ok === false && /旧值/.test(JSON.parse(r3.message).error),
    JSON.stringify(r3.message));
  check('E3b 旧值不符后 capability 已作废', props3.getProperty('rotation_nonce_hash') === null);
  check('E3c 旧值不符后在途标记已清除', props3.getProperty('rotation_inflight') === null);
  check('E3d 令牌未被改（仍 OLD）', props3.getProperty('REMOTE_TOKEN') === OLD);

  // E4 无效 nonce → 拒绝且 capability 保留
  let props4 = fresh(0); let sb4 = makeEnv(props4);
  post(sb4, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('REAL_NONCE'),
              expected_old: OLD, owner_id: OWNER });
  let r4 = post(sb4, { action: 'rotateRemoteToken', token: OLD, nonce: 'WRONG_NONCE',
                       expected_old: OLD, new_token: 'Z', owner_id: OWNER });
  check('E4 无效 nonce 被拒', JSON.parse(r4.message).ok === false && /无效/.test(JSON.parse(r4.message).error),
    JSON.stringify(r4.message));
  check('E4b 无效 nonce 时 capability 保留', props4.getProperty('rotation_nonce_hash') === sha256hex('REAL_NONCE'));

  // E5 capability 热装的护栏（v5：取消无条件 force）
  let props5 = fresh(0); let sb5 = makeEnv(props5);
  sb5.__clock = 1000000;
  let s1 = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH });
  check('E5a 缺 expected_old → 拒', JSON.parse(s1.message).ok === false, JSON.stringify(s1.message));
  let s2 = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: 'zz',
                       expected_old: OLD, owner_id: OWNER });
  check('E5b 非法 nonce_hash → 拒',
    JSON.parse(s2.message).ok === false && /64/.test(JSON.parse(s2.message).error), JSON.stringify(s2.message));
  let s2b = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
                        expected_old: OLD });
  check('E5c 缺 owner_id → 拒（防覆盖他人在途操作）',
    JSON.parse(s2b.message).ok === false, JSON.stringify(s2b.message));
  // 同 owner 幂等重设
  post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('n1'),
              expected_old: OLD, owner_id: OWNER });
  let s3 = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('n2'),
                       expected_old: OLD, owner_id: OWNER });
  check('E5d 同 owner 幂等重设允许', JSON.parse(s3.message).ok === true, JSON.stringify(s3.message));
  // 他人 + 新鲜 → 拒
  let s4 = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('n3'),
                       expected_old: OLD, owner_id: 'owner_OTHER' });
  check('E5e 他人新鲜 capability → 默认拒绝覆盖（foreign）',
    JSON.parse(s4.message).ok === false && JSON.parse(s4.message).foreign === true, JSON.stringify(s4.message));
  check('E5f 拒绝时原 capability 未变',
    props5.getProperty('rotation_nonce_hash') === sha256hex('n2'), '仍为 owner 的 n2');
  // 显式覆盖
  let s5 = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('n4'),
                       expected_old: OLD, owner_id: 'owner_OTHER', force_over_foreign: 'true' });
  check('E5g 显式 force_over_foreign=true → 允许覆盖', JSON.parse(s5.message).ok === true,
    JSON.stringify(s5.message));
  // 超 TTL（推时钟）
  sb5.__clock += 11 * 60 * 1000;
  let s6 = post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('n5'),
                       expected_old: OLD, owner_id: 'owner_THIRD' });
  check('E5h 已超 TTL（陈旧）→ 无需显式覆盖即可重建', JSON.parse(s6.message).ok === true,
    JSON.stringify(s6.message));

  // E6 状态查询暴露在途/归属，且不泄露令牌
  let props6 = makeProps({ REMOTE_TOKEN: NEW, rotation_counter: '7' });
  let sb6 = makeEnv(props6);
  let st = JSON.parse(post(sb6, { action: 'rotationStatus', token: NEW }).message);
  check('E6 指纹 = sha256(token|counter) 与客户端算法一致',
    st.token_fingerprint === sha256hex(NEW + '|' + '7'), st.token_fingerprint);
  check('E6b 状态查询不泄露令牌原文', JSON.stringify(st).indexOf(NEW) < 0, JSON.stringify(st));
  check('E6c 状态含 inflight 字段（客户端据此不得终判"未轮换"）',
    typeof st.inflight === 'boolean', JSON.stringify(st.inflight));
}

// ============================================================
// F 组：在途保护 / 归属校验（Tom 第三轮第 3 条：并发关系）
// ============================================================
{
  // F1 有轮换在途 ⇒ 拒绝再次设置 capability，且不动已有 capability
  let props = fresh(0);
  let sb = makeEnv(props);
  post(sb, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
             expected_old: OLD, owner_id: OWNER });
  const before = props.getProperty('rotation_nonce_hash');
  props.setProperty('rotation_inflight', 'req_someone_else');       // 模拟另一笔轮换在执行
  let f1 = JSON.parse(post(sb, { action: 'setRotationCapability', token: OLD,
    nonce_hash: sha256hex('other'), expected_old: OLD, owner_id: 'owner_OTHER' }).message);
  check('F1 在途时设置 capability 被拒（inflight=true）',
    f1.ok === false && f1.inflight === true, JSON.stringify(f1));
  check('F1b 在途时已有 capability 未被改动', props.getProperty('rotation_nonce_hash') === before);

  // F2 在途时第二个轮换请求被拒（不并发写）
  let f2 = JSON.parse(post(sb, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SOMEONE_ELSE', owner_id: OWNER }).message);
  check('F2 在途时第二个轮换请求被拒', f2.ok === false && f2.inflight === true, JSON.stringify(f2));
  check('F2b 在途时令牌未被改', props.getProperty('REMOTE_TOKEN') === OLD);
  props.deleteProperty('rotation_inflight');

  // F3 owner 不匹配 ⇒ 拒绝且不消费他人在途的 capability
  let props3 = fresh(0);
  let sb3 = makeEnv(props3);
  post(sb3, { action: 'setRotationCapability', token: OLD, nonce_hash: sha256hex('nonceA'),
              expected_old: OLD, owner_id: 'owner_AAA' });
  let f3 = JSON.parse(post(sb3, { action: 'rotateRemoteToken', token: OLD, nonce: 'nonceA',
    expected_old: OLD, new_token: 'X', owner_id: 'owner_BBB' }).message);
  check('F3 owner 不匹配→拒绝', f3.ok === false && f3.foreign === true, JSON.stringify(f3));
  check('F3b owner 不匹配→不消费该 capability（哈希仍在）',
    props3.getProperty('rotation_nonce_hash') === sha256hex('nonceA'));
  check('F3c 令牌未被改', props3.getProperty('REMOTE_TOKEN') === OLD);

  // F4 在途时状态查询 inflight=true（客户端据此维持 UNKNOWN）
  let props4 = fresh(0);
  let sb4 = makeEnv(props4);
  props4.setProperty('rotation_inflight', 'req_123');
  let f4 = JSON.parse(post(sb4, { action: 'rotationStatus', token: OLD }).message);
  check('F4 在途时状态查询返回 inflight=true + inflight_id',
    f4.inflight === true && f4.inflight_id === 'req_123', JSON.stringify(f4));
  check('F4b 在途时指纹仍对应旧令牌（不得据此判定未轮换）',
    f4.token_fingerprint === sha256hex(OLD + '|' + '0'), f4.token_fingerprint);

  // F5 归属指纹可区分（不泄露 owner 原文）
  let props5 = fresh(0);
  let sb5 = makeEnv(props5);
  post(sb5, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
              expected_old: OLD, owner_id: OWNER });
  let f5 = JSON.parse(post(sb5, { action: 'rotationStatus', token: OLD }).message);
  check('F5 状态含 owner_fingerprint 且不等于 owner 原文',
    typeof f5.owner_fingerprint === 'string' && f5.owner_fingerprint !== OWNER,
    JSON.stringify(f5.owner_fingerprint));
  check('F5b owner_fingerprint = sha256(owner)[:12]',
    f5.owner_fingerprint === sha256hex(OWNER).slice(0, 12), f5.owner_fingerprint);

  // F6 遗留 capability（哈希在、owner 空）→ 拒绝且不消费（Tom 第四轮第 1 条）
  let props6 = fresh(0);
  let sb6 = makeEnv(props6);
  props6.setProperty('rotation_nonce_hash', NONCE_HASH);       // 注意：未设 owner（遗留态）
  let f6 = JSON.parse(post(sb6, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'X', owner_id: 'owner_ANY' }).message);
  check('F6 遗留 capability（owner 空）→ 拒绝（foreign）',
    f6.ok === false && f6.foreign === true, JSON.stringify(f6));
  check('F6b 遗留 capability 未被消费（哈希仍在、令牌未改）',
    props6.getProperty('rotation_nonce_hash') === NONCE_HASH && props6.getProperty('REMOTE_TOKEN') === OLD,
    JSON.stringify([props6.getProperty('rotation_nonce_hash'), props6.getProperty('REMOTE_TOKEN')]));

  // F7 消费时 TTL 校验：延迟到达的过期请求必须拒绝且不改令牌（Tom 第四轮第 2 条）
  let props7 = fresh(0);
  let sb7 = makeEnv(props7);
  sb7.__clock = 1000000;
  post(sb7, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
              expected_old: OLD, owner_id: OWNER });
  props7.setProperty('rotation_capability_created', String(1000000 - 11 * 60 * 1000));  // 推到 TTL 之前
  let f7 = JSON.parse(post(sb7, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'DELAYED', owner_id: OWNER }).message);
  check('F7 延迟请求：capability 已过期→拒绝（expired）', f7.ok === false && f7.expired === true, JSON.stringify(f7));
  check('F7b 延迟请求：令牌未被改（仍 OLD）', props7.getProperty('REMOTE_TOKEN') === OLD);
  check('F7c 延迟请求：过期 capability 已清理（无法被后续延迟请求复用）',
    props7.getProperty('rotation_nonce_hash') === null);

  // F7d/F7e/F7f 消费时创建时间失败关闭：缺失/为0/格式错误 ⇒ 拒绝且不消费（Tom 第五轮）
  // F7d created 缺失
  let props7d = fresh(0);
  let sb7d = makeEnv(props7d);
  post(sb7d, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7d.deleteProperty('rotation_capability_created');   // 创建时间完全缺失
  let f7d = JSON.parse(post(sb7d, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7d 创建时间缺失→拒绝（expired）', f7d.ok === false && f7d.expired === true, JSON.stringify(f7d));
  check('F7d 创建时间缺失：令牌未被改（仍 OLD）', props7d.getProperty('REMOTE_TOKEN') === OLD);
  check('F7d 创建时间缺失：capability 已清理（无法被复用）',
    props7d.getProperty('rotation_nonce_hash') === null);

  // F7e created 为 0
  let props7e = fresh(0);
  let sb7e = makeEnv(props7e);
  post(sb7e, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7e.setProperty('rotation_capability_created', '0');
  let f7e = JSON.parse(post(sb7e, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7e 创建时间为 0→拒绝（expired）', f7e.ok === false && f7e.expired === true, JSON.stringify(f7e));
  check('F7e 创建时间为 0：令牌未被改（仍 OLD）', props7e.getProperty('REMOTE_TOKEN') === OLD);
  check('F7e 创建时间为 0：capability 已清理', props7e.getProperty('rotation_nonce_hash') === null);

  // F7f created 格式错误（非数字）
  let props7f = fresh(0);
  let sb7f = makeEnv(props7f);
  post(sb7f, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7f.setProperty('rotation_capability_created', 'abc');
  let f7f = JSON.parse(post(sb7f, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7f 创建时间格式错误→拒绝（expired）', f7f.ok === false && f7f.expired === true, JSON.stringify(f7f));
  check('F7f 创建时间格式错误：令牌未被改（仍 OLD）', props7f.getProperty('REMOTE_TOKEN') === OLD);
  check('F7f 创建时间格式错误：capability 已清理', props7f.getProperty('rotation_nonce_hash') === null);

  // F7g 正向对照：时间戳有效且未过期 ⇒ 允许消费（证明失败关闭不误伤正常 capability）
  let props7g = fresh(0);
  let sb7g = makeEnv(props7g);
  let g7 = JSON.parse(post(sb7g, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER }).message);
  let f7g = JSON.parse(post(sb7g, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'GOOD_NEW', owner_id: OWNER }).message);
  check('F7g 创建时间有效且未过期→允许轮换', f7g.ok === true && f7g.rotated === true, JSON.stringify(f7g));
  check('F7g 正向对照：令牌已切为新值', props7g.getProperty('REMOTE_TOKEN') === 'GOOD_NEW');

  // F7h/F7i/F7j/F7k 消费时创建时间严格解析（v8 修正，Tom 第六轮）：
  // 数字后缀 / 小数 / 科学记数法 / 未来时间戳 均非"严格正整数时间戳"，必须拒绝并清理 capability。

  // F7h created 带数字后缀 "1700000000000x"（v7 的 parseInt 会吞掉 x）
  let props7h = fresh(0);
  let sb7h = makeEnv(props7h);
  post(sb7h, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7h.setProperty('rotation_capability_created', '1700000000000x');
  let f7h = JSON.parse(post(sb7h, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7h 创建时间带数字后缀→拒绝（expired）', f7h.ok === false && f7h.expired === true, JSON.stringify(f7h));
  check('F7h 创建时间带数字后缀：令牌未被改（仍 OLD）', props7h.getProperty('REMOTE_TOKEN') === OLD);
  check('F7h 创建时间带数字后缀：capability 已清理', props7h.getProperty('rotation_nonce_hash') === null);

  // F7i created 为小数 "123.456"
  let props7i = fresh(0);
  let sb7i = makeEnv(props7i);
  post(sb7i, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7i.setProperty('rotation_capability_created', '123.456');
  let f7i = JSON.parse(post(sb7i, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7i 创建时间为小数→拒绝（expired）', f7i.ok === false && f7i.expired === true, JSON.stringify(f7i));
  check('F7i 创建时间为小数：令牌未被改（仍 OLD）', props7i.getProperty('REMOTE_TOKEN') === OLD);
  check('F7i 创建时间为小数：capability 已清理', props7i.getProperty('rotation_nonce_hash') === null);

  // F7j created 为科学记数法 "1.7e12"
  let props7j = fresh(0);
  let sb7j = makeEnv(props7j);
  post(sb7j, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7j.setProperty('rotation_capability_created', '1.7e12');
  let f7j = JSON.parse(post(sb7j, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7j 创建时间为科学记数法→拒绝（expired）', f7j.ok === false && f7j.expired === true, JSON.stringify(f7j));
  check('F7j 创建时间为科学记数法：令牌未被改（仍 OLD）', props7j.getProperty('REMOTE_TOKEN') === OLD);
  check('F7j 创建时间为科学记数法：capability 已清理', props7j.getProperty('rotation_nonce_hash') === null);

  // F7k created 为未来时间戳（不可能由本系统生成，必须失败关闭）
  let props7k = fresh(0);
  let sb7k = makeEnv(props7k);
  post(sb7k, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7k.setProperty('rotation_capability_created', '9999999999999');
  let f7k = JSON.parse(post(sb7k, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7k 创建时间为未来时间戳→拒绝（expired）', f7k.ok === false && f7k.expired === true, JSON.stringify(f7k));
  check('F7k 创建时间为未来时间戳：令牌未被改（仍 OLD）', props7k.getProperty('REMOTE_TOKEN') === OLD);
  check('F7k 创建时间为未来时间戳：capability 已清理', props7k.getProperty('rotation_nonce_hash') === null);

  // F7l 正向对照：创建时间为严格正整数时间戳（手动设为有效近值）⇒ 允许消费（证明严格解析不误伤正常 capability）
  let props7l = fresh(0);
  let sb7l = makeEnv(props7l);
  sb7l.__clock = 3000000;
  post(sb7l, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7l.setProperty('rotation_capability_created', '3000000');   // 明确写入一个干净正整数时间戳
  let f7l = JSON.parse(post(sb7l, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'GOOD_NEW', owner_id: OWNER }).message);
  check('F7l 创建时间为干净正整数时间戳→允许轮换', f7l.ok === true && f7l.rotated === true, JSON.stringify(f7l));
  check('F7l 正向对照：令牌已切为新值', props7l.getProperty('REMOTE_TOKEN') === 'GOOD_NEW');

  // F7m/F7n/F7o 创建时间带空白（前导/尾随/制表符换行）⇒ 拒绝（Tom 第七轮：移除 trim 后空白一律非法）
  // 基线取"若被 trim 则恰好合法且未过期"的时间戳 ⇒ 可真正证明 trim 必须移除
  let props7m = fresh(0);
  let sb7m = makeEnv(props7m);
  sb7m.__clock = 4000000;
  post(sb7m, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7m.setProperty('rotation_capability_created', ' 4000000');        // 前导空白
  let f7m = JSON.parse(post(sb7m, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7m 创建时间带前导空白→拒绝（expired）', f7m.ok === false && f7m.expired === true, JSON.stringify(f7m));
  check('F7m 前导空白：令牌未被改（仍 OLD）', props7m.getProperty('REMOTE_TOKEN') === OLD);
  check('F7m 前导空白：capability 已清理', props7m.getProperty('rotation_nonce_hash') === null);

  let props7n = fresh(0);
  let sb7n = makeEnv(props7n);
  sb7n.__clock = 5000000;
  post(sb7n, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7n.setProperty('rotation_capability_created', '5000000 ');        // 尾随空白
  let f7n = JSON.parse(post(sb7n, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7n 创建时间带尾随空白→拒绝（expired）', f7n.ok === false && f7n.expired === true, JSON.stringify(f7n));
  check('F7n 尾随空白：令牌未被改（仍 OLD）', props7n.getProperty('REMOTE_TOKEN') === OLD);
  check('F7n 尾随空白：capability 已清理', props7n.getProperty('rotation_nonce_hash') === null);

  let props7o = fresh(0);
  let sb7o = makeEnv(props7o);
  sb7o.__clock = 6000000;
  post(sb7o, { action: 'setRotationCapability', token: OLD, nonce_hash: NONCE_HASH,
               expected_old: OLD, owner_id: OWNER });
  props7o.setProperty('rotation_capability_created', '\t6000000\n');     // 制表符/换行包裹
  let f7o = JSON.parse(post(sb7o, { action: 'rotateRemoteToken', token: OLD, nonce: NONCE_HEX,
    expected_old: OLD, new_token: 'SHOULD_NOT', owner_id: OWNER }).message);
  check('F7o 创建时间被制表符/换行包裹→拒绝（expired）', f7o.ok === false && f7o.expired === true, JSON.stringify(f7o));
  check('F7o 制表符/换行：令牌未被改（仍 OLD）', props7o.getProperty('REMOTE_TOKEN') === OLD);
  check('F7o 制表符/换行：capability 已清理', props7o.getProperty('rotation_nonce_hash') === null);
}

// ---------- 汇总 ----------
const passed = results.filter(r => r[1]).length;
console.log('\n=== 结果 ===');
console.log('PASS ' + passed + ' / ' + results.length);
console.log('范围：用真实 RemoteTrigger.gs / 真实 doPost / 拟部署处理函数原文在 Node 中仿真；无网络、无真实令牌、未触生产。');
process.exit(passed === results.length ? 0 : 1);
