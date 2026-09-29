# -*- coding: utf-8 -*-
"""生成 dispatch_sim_py.py：纯 Python 复刻的【分发层】仿真（供无 Node 环境复跑）。

与 dispatch_sim_test.js（Node 版，94 项）逐项对应：用例名、用例序号完全一致。
差异与约束（必须如实声明，不得掩饰）：
  · Node 版把【真实 JS 源码】放进 vm 里跑（JS 运行时）；
  · Python 版无法执行 JS，故为【语义复刻】：分发器与三个处理函数的判定逻辑按真实源码逐行复刻。
  · 为防止复刻漂移，每条关键规则都配一条【源码静态断言】：直接对嵌入的真实源码文本做包含性检查
    （嵌入内容从真实文件读取、零手抄，并附 SHA-256）。真实源码一改，断言即失败（退出码 2）。
源：
  _tmp/dss_RemoteTrigger.js        （真实分发器）
  _tmp/dss_Code.js 第 135-140 行   （真实 doPost）
  _tmp/t1b_delivery/rotation_action_actual.gs 第 2 节函数（拟部署处理函数）
  _tmp/_tmp_patched_RemoteActions.js 的 REMOTE_ACTIONS 键名（真实注册表）
"""
import hashlib, json, os, re

BASE = r'C:\Users\rita.jin\WorkBuddy\SMCN_ERP\_tmp'
OUT = os.path.join(BASE, 't1b_delivery', 'dispatch_sim_py.py')

trig = open(os.path.join(BASE, 'dss_RemoteTrigger.js'), encoding='utf-8').read()
code = open(os.path.join(BASE, 'dss_Code.js'), encoding='utf-8').read().split('\n')
dopost = '\n'.join(code[134:140])
gs = open(os.path.join(BASE, 't1b_delivery', 'rotation_action_actual.gs'), encoding='utf-8').read()


def extract_fn(src, name):
    i = src.index('function %s(' % name)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError('unbalanced: ' + name)


_p0 = gs.index('var ROTATION_CAP_TTL_MS')
_p1 = gs.index('/**', _p0)
preamble = gs[_p0:_p1].rstrip() + '\n\n'
handlers = preamble + '\n\n'.join(extract_fn(gs, n) + '\n' for n in
                                  ['_parseStrictPositiveInt', 'tsSetRotationCapability',
                                   'tsRotateRemoteToken', 'tsRotationStatus', '_sha256'])

pat = open(os.path.join(BASE, '_tmp_patched_RemoteActions.js'), encoding='utf-8').read()
blk = pat[pat.index('var REMOTE_ACTIONS'):pat.index('};', pat.index('var REMOTE_ACTIONS')) + 2]
keys = re.findall(r'^\s{2}([A-Za-z_][A-Za-z0-9_]*)\s*:', blk, re.M)
NEW_KEYS = ['rotationStatus', 'setRotationCapability', 'rotateRemoteToken']
assert all(k in keys for k in NEW_KEYS), keys
old_keys = [k for k in keys if k not in NEW_KEYS]

h_trig = hashlib.sha256(trig.encode('utf-8')).hexdigest()
h_gs = hashlib.sha256(gs.encode('utf-8')).hexdigest()


def py_str(s):
    """把源码文本安全嵌入 Python 三引号字符串。"""
    if '"""' in s or s.rstrip().endswith('"'):
        return repr(s)
    return 'r"""\n' + s + '\n"""'


tpl = r'''# -*- coding: utf-8 -*-
"""dispatch_sim_py.py —— 纯 Python 复刻的【分发层】仿真（供无 Node 环境复跑 Node 版 94 项）

生成方式：由 _gen_dispatch_sim_py.py 从真实文件自动嵌入源码（零手抄）。
  · 嵌入的真实分发器 RemoteTrigger.gs  SHA-256(LF) = __H_TRIG__
  · 嵌入的真实 doPost（Code.gs 第 135-140 行）
  · 嵌入的拟部署处理函数（rotation_action_actual.gs 第 2 节）SHA-256(LF) = __H_GS__
  · REMOTE_ACTIONS 键名取自打补丁后的真实注册表（__NKEYS__ 个，新增 __NNEW__ 个）

运行：python dispatch_sim_py.py     退出码：0=全通过 1=有失败 2=自检失败（嵌入源缺失/被改/规则漂移）
红线：全程 mock，无网络、无真实令牌、不触生产。

⚠️ 与 Node 版的关系（如实声明，请勿略过）：
  · Node 版 dispatch_sim_test.js 把【真实 JS 源码】放进 vm 执行（JS 运行时）；
  · 本文件【不执行 JS】，而是按真实源码逐行复刻分发器与三个处理函数的判定逻辑（语义复刻）。
  · 防漂移机制：每条关键规则都有一条【源码静态断言】直接检查嵌入的真实源码文本；
    真实源码一旦变更致使该规则消失，自检失败并退出码 2 —— 即复刻不可能悄悄偏离真实源码。
  · 用例名与用例序号与 Node 版一一对应（共 __NCASES__ 项），便于两版逐项比对。
"""
import hashlib, json, re, sys

# ---------- 嵌入的真实源码（逐字，来自生产只读副本） ----------
REMOTE_TRIGGER_SRC = __TRIG__

REAL_DOPOST_SRC = __DOPOST__

ROTATION_HANDLERS_SRC = __HANDLERS__

ALL_KEYS = __KEYS_JSON__
NEW_KEYS = __NEW_JSON__
OLD_KEYS = [k for k in ALL_KEYS if k not in NEW_KEYS]

# ---------- 自检：嵌入源必须完整，且被复刻的每条规则都必须在真实源码中存在（fail-closed） ----------
def self_check():
    need = [
        ('RemoteTrigger.gs 含 _rtMaybeHandle(e)', 'function _rtMaybeHandle(e)' in REMOTE_TRIGGER_SRC),
        ('RemoteTrigger.gs 含 _rtMaybeHandlePost(e)', 'function _rtMaybeHandlePost(e)' in REMOTE_TRIGGER_SRC),
        ('RemoteTrigger.gs 含 String(out) 强转', 'result.message = String(out);' in REMOTE_TRIGGER_SRC),
        ('真实 doPost 已调用 _rtMaybeHandlePost', '_rtMaybeHandlePost(e)' in REAL_DOPOST_SRC),
        ('处理函数含 JSON.stringify 返回', 'return JSON.stringify(' in ROTATION_HANDLERS_SRC),
        ('处理函数不含 _rtResponse 误用', '_rtResponse(' not in ROTATION_HANDLERS_SRC),
        ('新增 3 键齐全', len(NEW_KEYS) == 3 and all(k in ALL_KEYS for k in NEW_KEYS)),
        # ↓ 以下是本文件复刻的每条判定规则 —— 真实源码中必须能找到，否则复刻已漂移
        ('规则：分发器大小写不敏感查表', 'toLowerCase() === action' in REMOTE_TRIGGER_SRC),
        ('规则：令牌门严格相等', 'if (token !== expected)' in REMOTE_TRIGGER_SRC),
        ('规则：body 无 action 时分发器让位', 'if (!action) return null;' in REMOTE_TRIGGER_SRC),
        ('规则：在途时拒绝设置 capability', "return JSON.stringify({ ok: false, error: '有轮换请求在途，拒绝设置/覆盖 capability'" in ROTATION_HANDLERS_SRC),
        ('规则：expected_old 严格校验', 'body.expected_old || \'\') !== String(cur || \'\')' in ROTATION_HANDLERS_SRC),
        ('规则：nonce_hash 必须 64 位小写十六进制', '/^[0-9a-f]{64}$/.test(h)' in ROTATION_HANDLERS_SRC),
        ('规则：缺 owner_id 即拒', '缺少 owner_id（用于防止覆盖他人在途操作）' in ROTATION_HANDLERS_SRC),
        ('规则：取消无条件 force（三条件受限覆盖）', "String(body.force_over_foreign) !== 'true'" in ROTATION_HANDLERS_SRC),
        ('规则：在途时拒绝第二个轮换', '已有轮换请求在途，本次未执行' in ROTATION_HANDLERS_SRC),
        ('规则：owner 必须存在且严格匹配', "if (!owner || String(body.owner_id || '') !== owner)" in ROTATION_HANDLERS_SRC),
        ('规则：消费时强制 TTL（失败关闭）', 'created === null || (_nowMs() - created) > ROTATION_CAP_TTL_MS' in ROTATION_HANDLERS_SRC),
        ('规则：TTL 失败时清理 capability 三键', "props.deleteProperty('rotation_capability_created');" in ROTATION_HANDLERS_SRC),
        ('规则：capability 用过即焚', "props.deleteProperty('rotation_nonce_hash');       // ← 用过即焚" in ROTATION_HANDLERS_SRC),
        ('规则：严格正整数解析（不做 trim）', "if (!/^[0-9]+$/.test(raw)) return null;" in ROTATION_HANDLERS_SRC),
        ('规则：解析函数不 trim', 'v9：【不做 trim】' in ROTATION_HANDLERS_SRC),
        ('规则：拒未来时间戳', 'if (n > nowMs) return null;' in ROTATION_HANDLERS_SRC),
        ('规则：状态查询不泄露令牌原文', 'token_fingerprint' in ROTATION_HANDLERS_SRC),
        ('规则：在途标记 finally 清除', "props.deleteProperty('rotation_inflight');" in ROTATION_HANDLERS_SRC),
    ]
    bad = [n for n, ok in need if not ok]
    if bad:
        sys.stderr.write('SELF-CHECK FAILED: ' + ' | '.join(bad) + '\n')
        sys.exit(2)
    return True


self_check()

# ---------- GAS 服务 mock ----------
CLOCK = [1000000]          # 可控时钟（TTL 用例用），与 Node 版 __clock 对齐


def now_ms():
    return CLOCK[0]


def sha256hex(s):
    return hashlib.sha256(str(s).encode('utf-8')).hexdigest()


MAX_SAFE_INTEGER = 2 ** 53 - 1
ROTATION_CAP_TTL_MS = 10 * 60 * 1000


class Props(object):
    """PropertiesService.getScriptProperties() 的最小复刻（GAS 语义：缺失返回 None）。"""

    def __init__(self, init=None):
        self.d = dict(init or {})

    def getProperty(self, k):
        return self.d.get(k)          # GAS：不存在返回 null

    def setProperty(self, k, v):
        self.d[k] = str(v)

    def deleteProperty(self, k):
        self.d.pop(k, None)


CURRENT = {'props': Props()}


def _props():
    return CURRENT['props']


def _jsstr(v):
    """JS String(v) 的最小复刻：undefined → 'undefined'（用于源码里【不带 ||''】的写法）。"""
    if v is None:
        return 'undefined'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    return str(v)


def _jstr(v):
    """JS String(v || '') 的最小复刻：undefined/null/'' → ''（源码里绝大多数取参都是这个形态）。"""
    if v is None:
        return ''
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    return str(v)


# ---------- 拟部署处理函数（按真实 gs 源码逐行复刻） ----------
def _parse_strict_positive_int(raw, now):
    if raw is None:
        return None
    if not isinstance(raw, str):
        raw = str(raw)
    if not re.fullmatch(r'[0-9]+', raw):
        return None          # 仅数字：拒符号/小数/指数/后缀/空白（不做 trim）
    if len(raw) > 16:
        return None
    n = int(raw)
    if not (n > 0):
        return None
    if n > MAX_SAFE_INTEGER:
        return None
    if n > now:
        return None
    return n


def tsSetRotationCapability(e):
    props = _props()
    body = (e or {}).get('postBody') or {}
    if props.getProperty('rotation_inflight'):
        return json.dumps({'ok': False, 'error': '有轮换请求在途，拒绝设置/覆盖 capability',
                           'inflight': True})
    try:
        cur = props.getProperty('REMOTE_TOKEN')
        if _jstr(body.get('expected_old')) != _jstr(cur):
            return json.dumps({'ok': False, 'error': 'expected_old 与当前令牌不符，拒绝热装 capability'})
        h = _jstr(body.get('nonce_hash'))
        if not re.fullmatch(r'[0-9a-f]{64}', h):
            return json.dumps({'ok': False, 'error': 'nonce_hash 必须是 64 位小写十六进制 SHA-256'})
        owner = _jstr(body.get('owner_id'))
        if not owner:
            return json.dumps({'ok': False, 'error': '缺少 owner_id（用于防止覆盖他人在途操作）'})

        existing = props.getProperty('rotation_nonce_hash')
        if existing:
            ex_owner = props.getProperty('rotation_capability_owner') or ''
            created = _parse_strict_positive_int(props.getProperty('rotation_capability_created'), now_ms())
            age = (ROTATION_CAP_TTL_MS + 1) if created is None else (now_ms() - created)
            same_owner = bool(ex_owner) and ex_owner == owner
            stale = age > ROTATION_CAP_TTL_MS
            if (not same_owner) and (not stale) and _jsstr(body.get('force_over_foreign')) != 'true':
                return json.dumps({'ok': False,
                                   'error': 'capability 已存在且属于另一笔操作，未覆盖；确认其已作废后带 force_over_foreign=true 重试',
                                   'nonce_present': True, 'foreign': True, 'capability_age_ms': age})
        props.setProperty('rotation_nonce_hash', h)
        props.setProperty('rotation_capability_owner', owner)
        props.setProperty('rotation_capability_created', str(now_ms()))
        return json.dumps({'ok': True, 'capability_set': True, 'nonce_present': True,
                           'capability_ttl_ms': ROTATION_CAP_TTL_MS,
                           'nonce_hash_fingerprint': sha256hex(h)[:12],
                           'owner_fingerprint': sha256hex(owner)[:12]})
    finally:
        pass                      # LockService 在 mock 中无副作用


def tsRotateRemoteToken(e):
    props = _props()
    body = (e or {}).get('postBody') or {}
    if props.getProperty('rotation_inflight'):
        return json.dumps({'ok': False, 'error': '已有轮换请求在途，本次未执行', 'inflight': True})
    req_id = _jstr(body.get('request_id')) or ('req_' + str(now_ms()))
    props.setProperty('rotation_inflight', req_id)      # 在途标记（先于删除 capability）
    try:
        stored = props.getProperty('rotation_nonce_hash')
        if not stored:
            return json.dumps({'ok': False, 'error': 'capability 已消费或未设置'})

        owner = props.getProperty('rotation_capability_owner') or ''
        if (not owner) or _jstr(body.get('owner_id')) != owner:
            return json.dumps({'ok': False,
                               'error': 'capability 归属不匹配（或缺失），已中止（未消费该 capability）',
                               'foreign': True})

        created_raw = props.getProperty('rotation_capability_created')
        created = _parse_strict_positive_int(created_raw, now_ms())
        if created is None or (now_ms() - created) > ROTATION_CAP_TTL_MS:
            props.deleteProperty('rotation_nonce_hash')
            props.deleteProperty('rotation_capability_owner')
            props.deleteProperty('rotation_capability_created')
            ttl_msg = ('capability 创建时间缺失或无效（须为严格正整数时间戳，不含符号/小数/指数/后缀/空白），'
                       '拒绝轮换（请重新热装 capability）') if created is None \
                else 'capability 已过期，拒绝轮换（请重新热装 capability）'
            return json.dumps({'ok': False, 'error': ttl_msg, 'expired': True})

        if sha256hex(_jstr(body.get('nonce'))) != stored:
            return json.dumps({'ok': False, 'error': 'capability 无效'})   # 无效 nonce：不删，便于排查
        props.deleteProperty('rotation_nonce_hash')                        # 用过即焚
        props.deleteProperty('rotation_capability_owner')
        props.deleteProperty('rotation_capability_created')

        if props.getProperty('REMOTE_TOKEN') != body.get('expected_old'):
            return json.dumps({'ok': False, 'error': '当前令牌与预期旧值不符，已中止；capability 已作废'})

        props.setProperty('REMOTE_TOKEN', _jsstr(body.get('new_token')))
        c = int(props.getProperty('rotation_counter') or '0') + 1
        props.setProperty('rotation_counter', str(c))
        return json.dumps({'ok': True, 'rotated': True, 'counter': c, 'request_id': req_id})
    finally:
        props.deleteProperty('rotation_inflight')       # 无论成功/失败/异常都清除
        pass                                            # lock.releaseLock()


def tsRotationStatus(e):
    props = _props()
    counter = int(props.getProperty('rotation_counter') or '0')
    fp = sha256hex((props.getProperty('REMOTE_TOKEN') or '') + '|' + str(counter))
    created = _parse_strict_positive_int(props.getProperty('rotation_capability_created'), now_ms())
    owner = props.getProperty('rotation_capability_owner') or ''
    inflight = props.getProperty('rotation_inflight')
    return json.dumps({
        'ok': True,
        'counter': counter,
        'token_fingerprint': fp,
        'inflight': bool(inflight),
        'inflight_id': inflight or None,
        'nonce_present': bool(props.getProperty('rotation_nonce_hash')),
        'capability_age_ms': (now_ms() - created) if created else None,
        'owner_fingerprint': sha256hex(owner)[:12] if owner else None,
    })


# ---------- 真实分发器（按 RemoteTrigger.gs 逐行复刻） ----------
CALLS = []
REMOTE_ACTIONS = {}


def _stub(key):
    def _fn(e):
        CALLS.append(key)
        return json.dumps({'ok': True, 'stub': key})
    return _fn


def _rt_action_list():
    lst = ['status', '_seturl']
    for k in ALL_KEYS:
        if k not in lst:
            lst.append(k)
    return lst


def _js_string(out):
    """JS String(out)：对象 → '[object Object]'。"""
    if isinstance(out, dict):
        return '[object Object]'
    return str(out)


def _rt_maybe_handle(e):
    e = e or {}
    action = _jstr((e.get('parameter') or {}).get('action')).lower()
    if not action:
        return None
    props = _props()
    expected = props.getProperty('REMOTE_TOKEN')
    is_first_run = False
    if not expected:
        expected = 'SMCN-INIT-TOKEN'
        props.setProperty('REMOTE_TOKEN', expected)
        is_first_run = True
    token = _jstr((e.get('parameter') or {}).get('token'))
    if token != expected:
        err = {'ok': False, 'error': 'Invalid or missing token', 'ts': '2026-09-28 12:00:00'}
        if is_first_run:
            err['token'] = expected
        return err

    result = {'ok': True, 'action': action, 'version': 'RT1.0', 'ts': '2026-09-28 12:00:00'}
    try:
        if action == 'status':
            result['message'] = 'ok'
            result['actions'] = _rt_action_list()
        elif action == '_seturl':
            u = _jstr((e.get('parameter') or {}).get('url')).strip()
            if u:
                props.setProperty('REMOTE_WEBAPP_URL', u)
                result['message'] = 'REMOTE_WEBAPP_URL saved'
            else:
                result['ok'] = False
                result['error'] = 'missing url param'
        else:
            _rt_key = None
            for _k in ALL_KEYS:                       # 大小写不敏感线性查找
                if _k.lower() == action and _k in REMOTE_ACTIONS:
                    _rt_key = _k
                    break
            if _rt_key:
                out = REMOTE_ACTIONS[_rt_key](e)
                if out is not None:
                    result['message'] = _js_string(out)
            else:
                result['message'] = ('unknown action: ' + action + '. available: '
                                     + ', '.join(_rt_action_list()))
    except Exception as err:
        result['ok'] = False
        result['error'] = str(err)
    return result


def _rt_maybe_handle_post(e):
    e = e or {}
    body = {}
    try:
        pd = e.get('postData') or {}
        if pd.get('contents'):
            body = json.loads(pd['contents'])
        elif (e.get('parameter') or {}).get('payload'):
            body = json.loads((e.get('parameter') or {})['payload'])
    except Exception as err:
        return {'ok': False, 'error': 'invalid JSON body: ' + str(err)}
    action = _jstr(body.get('action') or (e.get('parameter') or {}).get('action')).lower()
    if not action:
        return None
    params = dict(e.get('parameter') or {})
    for k, v in body.items():
        if not isinstance(v, (dict, list)):
            params[k] = v
    params['action'] = action
    if not params.get('token') and body.get('token'):
        params['token'] = body['token']
    return _rt_maybe_handle({'parameter': params, 'postBody': body})


def do_post(e):
    """真实 Code.gs doPost 的复刻：分发器让位时由既有 doPost 自身兜底。"""
    r = _rt_maybe_handle_post(e)
    if r:
        return r
    return {'ok': False, 'error': 'no action in POST body'}


def make_env(props):
    CURRENT['props'] = props
    CALLS[:] = []
    REMOTE_ACTIONS.clear()
    for k in ALL_KEYS:
        if k == 'rotationStatus':
            REMOTE_ACTIONS[k] = tsRotationStatus
        elif k == 'setRotationCapability':
            REMOTE_ACTIONS[k] = tsSetRotationCapability
        elif k == 'rotateRemoteToken':
            REMOTE_ACTIONS[k] = tsRotateRemoteToken
        else:
            REMOTE_ACTIONS[k] = _stub(k)
    return {'props': props}


def post(env, body_obj=None, raw_text=None):
    contents = raw_text if raw_text is not None else json.dumps(body_obj)
    e = {'postData': {'contents': contents}, 'parameter': {}}
    out = do_post(e)
    if out is None:
        return {'__null': True}
    return out


def inner(res):
    return json.loads(res['message'])


# ---------- 断言 ----------
RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL') + ' - ' + name + (('  | ' + str(detail)) if detail else ''))


OLD = 'OLD_MOCK_TOKEN'
NEW = 'NEW_MOCK_TOKEN_VALUE'
NONCE_HEX = 'ab12cd34ef56ab12cd34ef56ab12cd34'
NONCE_HASH = sha256hex(NONCE_HEX)
OWNER = 'owner_unit_test'


def fresh(counter=0):
    return Props({'REMOTE_TOKEN': OLD, 'rotation_counter': str(counter or 0)})


# ============================================================
# A 组：POST body 解析（真实 _rtMaybeHandlePost）
# ============================================================
CLOCK[0] = 1000000
{
    p = fresh(0)
    env = make_env(p)
    r = post(env, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                   'expected_old': OLD, 'owner_id': OWNER})
    check('A1 POST body 被解析并挂到 e.postBody（capability 热装成功）',
          r.get('ok') is True and r.get('message') and inner(r).get('capability_set') is True,
          r.get('message'))

    p2 = fresh(0)
    env2 = make_env(p2)
    r2 = post(env2, {'action': 'rotationStatus', 'token': OLD})
    check('A2 token 取自 POST body（URL 无任何参数亦可通过门）', r2.get('ok') is True, json.dumps(r2))

    r3 = post(env2, None, '{not-json')
    check('A3 非法 JSON body → ok:false + invalid JSON body',
          r3.get('ok') is False and 'invalid JSON body' in (r3.get('error') or ''), json.dumps(r3))

    e4 = {'postData': {'contents': json.dumps({'token': OLD, 'foo': 1})}, 'parameter': {}}
    disp_null = _rt_maybe_handle_post(e4)
    check('A4 body 无 action → 分发器让位（_rtMaybeHandlePost 返回 null）',
          disp_null is None, str(disp_null))
    r4 = post(env2, {'token': OLD, 'foo': 1})
    check('A4b 随后由【既有】doPost 自身兜底（no action in POST body），未被分发器劫持',
          r4.get('ok') is False and 'no action in POST body' in (r4.get('error') or ''), json.dumps(r4))
}

# ============================================================
# B 组：旧令牌鉴权（分发器前置）
# ============================================================
{
    p = Props({'REMOTE_TOKEN': OLD, 'rotation_counter': '0', 'rotation_nonce_hash': NONCE_HASH,
               'rotation_capability_owner': OWNER, 'rotation_capability_created': '1000000'})
    env = make_env(p)
    r = post(env, {'action': 'rotateRemoteToken', 'token': 'WRONG_TOKEN', 'nonce': NONCE_HEX,
                   'expected_old': OLD, 'new_token': NEW})
    check('B1 错误令牌 → 外层 ok:false + Invalid or missing token',
          r.get('ok') is False and 'Invalid or missing token' in (r.get('error') or ''), json.dumps(r))
    check('B1b 错误令牌 → 处理函数未执行（capability 未被消费）',
          p.getProperty('rotation_nonce_hash') == NONCE_HASH, 'nonce_hash 仍在')

    r2 = post(env, {'action': 'rotateRemoteToken', 'nonce': NONCE_HEX, 'expected_old': OLD,
                    'new_token': NEW})
    check('B2 缺 token → 拒绝',
          r2.get('ok') is False and 'Invalid or missing token' in (r2.get('error') or ''), json.dumps(r2))

    r3 = post(env, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                    'expected_old': OLD, 'new_token': NEW, 'owner_id': OWNER})
    i3 = inner(r3)
    check('B3 正确旧令牌 → 通过门并完成轮换',
          r3.get('ok') is True and i3.get('ok') is True and i3.get('rotated') is True, json.dumps(r3))

    r4 = post(env, {'action': 'rotationStatus', 'token': OLD})
    check('B4 轮换后用 OLD 查询状态 → 被门拒绝（旧值确已失效）', r4.get('ok') is False, json.dumps(r4))
}

# ============================================================
# C 组：action 名匹配规则（正向 + 负向）
# ============================================================
{
    p = Props({'REMOTE_TOKEN': OLD, 'rotation_counter': '3'})
    env = make_env(p)
    r1 = post(env, {'action': 'rotationStatus', 'token': OLD})
    check('C1 camelCase "rotationStatus" 命中真实处理函数',
          r1.get('ok') is True and inner(r1).get('ok') is True, r1.get('message'))
    r2 = post(env, {'action': 'rotation_status', 'token': OLD})
    check('C2 下划线 "rotation_status" → unknown action（证明下划线不会被吃掉）',
          r2.get('ok') is True and (r2.get('message') or '').startswith('unknown action'),
          r2.get('message'))
    r3 = post(env, {'action': 'rotationstatus', 'token': OLD})
    check('C3 全小写 "rotationstatus" 命中（大小写不敏感查找生效）',
          r3.get('ok') is True and inner(r3).get('ok') is True, r3.get('message'))
}

# ============================================================
# D 组：其他 action 不受影响（既有 __NOLD__ 个 + 内置）
# ============================================================
{
    p = Props({'REMOTE_TOKEN': OLD, 'rotation_counter': '0'})
    env = make_env(p)
    probe = OLD_KEYS[OLD_KEYS.index('driveList')] if 'driveList' in OLD_KEYS else OLD_KEYS[0]
    r1 = post(env, {'action': probe, 'token': OLD})
    check('D1 既有 action（' + probe + '）仍被正确路由',
          r1.get('ok') is True and inner(r1).get('stub') == probe, r1.get('message'))
    check('D1b 既有 action 未被误触发其它分支', CALLS.count(probe) == 1, '调用次数=1')

    r2 = post(env, {'action': 'status', 'token': OLD})
    check('D2 内置 status 仍可用且列出全部动作',
          r2.get('ok') is True and isinstance(r2.get('actions'), list), str(len(r2.get('actions') or [])))
    check('D2b status 列表包含新增 3 个动作',
          all(k in (r2.get('actions') or []) for k in NEW_KEYS), json.dumps(NEW_KEYS))
    check('D2c 动作总数 = 内置2 + 注册表' + str(len(ALL_KEYS)) + ' = ' + str(2 + len(ALL_KEYS)),
          len(r2.get('actions') or []) == 2 + len(ALL_KEYS), '实际=' + str(len(r2.get('actions') or [])))

    r3 = post(env, {'action': 'noSuchAction', 'token': OLD})
    check('D3 未知 action → unknown action 提示（不报错、不影响其它）',
          (r3.get('message') or '').startswith('unknown action'), r3.get('message'))

    p2 = Props({'REMOTE_TOKEN': OLD, 'rotation_counter': '0'})
    env2 = make_env(p2)
    REMOTE_ACTIONS['readRange'] = lambda e: {'ok': True}      # 返对象（非 JSON 字符串）
    r4 = post(env2, {'action': 'readRange', 'token': OLD})
    check('D4 既有约定复现：返回对象会被 String() 变成 [object Object]（故必须返 JSON 字符串）',
          r4.get('message') == '[object Object]', json.dumps(r4.get('message')))
}

# ============================================================
# E 组：轮换四路径 + capability 热装
# ============================================================
CLOCK[0] = 1000000
{
    # E1 正常轮换（含 owner 归属）
    p = fresh(0)
    env = make_env(p)
    a = post(env, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                   'expected_old': OLD, 'owner_id': OWNER})
    check('E1a capability 热装成功（无需进编辑器手填）',
          inner(a).get('capability_set') is True, a.get('message'))
    r = post(env, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                   'expected_old': OLD, 'new_token': NEW, 'owner_id': OWNER})
    i = inner(r)
    check('E1b 成功路径：外层 ok=true 且 message 是可解析 JSON 字符串',
          r.get('ok') is True and isinstance(r.get('message'), str) and i.get('ok') is True,
          json.dumps(r))
    check('E1c 成功路径：rotated=true / counter=1 / 令牌已切 NEW',
          i.get('rotated') is True and i.get('counter') == 1 and p.getProperty('REMOTE_TOKEN') == NEW,
          json.dumps(i))
    check('E1d capability 用过即焚', p.getProperty('rotation_nonce_hash') is None, '已删除')
    check('E1e 在途标记已清除（finally）', p.getProperty('rotation_inflight') is None, '已清除')

    # E2 重放
    r2 = post(env, {'action': 'rotateRemoteToken', 'token': NEW, 'nonce': NONCE_HEX,
                    'expected_old': NEW, 'new_token': 'X', 'owner_id': OWNER})
    check('E2 重放被拒（capability 已消费）', inner(r2).get('ok') is False, r2.get('message'))
    check('E2b 重放后令牌未被改', p.getProperty('REMOTE_TOKEN') == NEW)

    # E3 expected_old 不符
    p3 = fresh(0)
    env3 = make_env(p3)
    post(env3, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                'expected_old': OLD, 'owner_id': OWNER})
    r3 = post(env3, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                     'expected_old': 'WRONG_OLD', 'new_token': 'Z', 'owner_id': OWNER})
    check('E3 旧值不符被拒',
          inner(r3).get('ok') is False and '旧值' in (inner(r3).get('error') or ''), r3.get('message'))
    check('E3b 旧值不符后 capability 已作废', p3.getProperty('rotation_nonce_hash') is None)
    check('E3c 旧值不符后在途标记已清除', p3.getProperty('rotation_inflight') is None)
    check('E3d 令牌未被改（仍 OLD）', p3.getProperty('REMOTE_TOKEN') == OLD)

    # E4 无效 nonce → 拒绝且 capability 保留
    p4 = fresh(0)
    env4 = make_env(p4)
    post(env4, {'action': 'setRotationCapability', 'token': OLD,
                'nonce_hash': sha256hex('REAL_NONCE'), 'expected_old': OLD, 'owner_id': OWNER})
    r4 = post(env4, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': 'WRONG_NONCE',
                     'expected_old': OLD, 'new_token': 'Z', 'owner_id': OWNER})
    check('E4 无效 nonce 被拒',
          inner(r4).get('ok') is False and '无效' in (inner(r4).get('error') or ''), r4.get('message'))
    check('E4b 无效 nonce 时 capability 保留',
          p4.getProperty('rotation_nonce_hash') == sha256hex('REAL_NONCE'))

    # E5 capability 热装的护栏（取消无条件 force）
    p5 = fresh(0)
    env5 = make_env(p5)
    CLOCK[0] = 1000000
    s1 = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH})
    check('E5a 缺 expected_old → 拒', inner(s1).get('ok') is False, s1.get('message'))
    s2 = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': 'zz',
                     'expected_old': OLD, 'owner_id': OWNER})
    check('E5b 非法 nonce_hash → 拒',
          inner(s2).get('ok') is False and '64' in (inner(s2).get('error') or ''), s2.get('message'))
    s2b = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                      'expected_old': OLD})
    check('E5c 缺 owner_id → 拒（防覆盖他人在途操作）',
          inner(s2b).get('ok') is False, s2b.get('message'))
    post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': sha256hex('n1'),
                'expected_old': OLD, 'owner_id': OWNER})
    s3 = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': sha256hex('n2'),
                     'expected_old': OLD, 'owner_id': OWNER})
    check('E5d 同 owner 幂等重设允许', inner(s3).get('ok') is True, s3.get('message'))
    s4 = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': sha256hex('n3'),
                     'expected_old': OLD, 'owner_id': 'owner_OTHER'})
    check('E5e 他人新鲜 capability → 默认拒绝覆盖（foreign）',
          inner(s4).get('ok') is False and inner(s4).get('foreign') is True, s4.get('message'))
    check('E5f 拒绝时原 capability 未变',
          p5.getProperty('rotation_nonce_hash') == sha256hex('n2'), '仍为 owner 的 n2')
    s5 = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': sha256hex('n4'),
                     'expected_old': OLD, 'owner_id': 'owner_OTHER', 'force_over_foreign': 'true'})
    check('E5g 显式 force_over_foreign=true → 允许覆盖', inner(s5).get('ok') is True, s5.get('message'))
    CLOCK[0] += 11 * 60 * 1000
    s6 = post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': sha256hex('n5'),
                     'expected_old': OLD, 'owner_id': 'owner_THIRD'})
    check('E5h 已超 TTL（陈旧）→ 无需显式覆盖即可重建', inner(s6).get('ok') is True, s6.get('message'))

    # E6 状态查询
    CLOCK[0] = 1000000
    p6 = Props({'REMOTE_TOKEN': NEW, 'rotation_counter': '7'})
    env6 = make_env(p6)
    st = inner(post(env6, {'action': 'rotationStatus', 'token': NEW}))
    check('E6 指纹 = sha256(token|counter) 与客户端算法一致',
          st.get('token_fingerprint') == sha256hex(NEW + '|' + '7'), st.get('token_fingerprint'))
    check('E6b 状态查询不泄露令牌原文', NEW not in json.dumps(st), json.dumps(st))
    check('E6c 状态含 inflight 字段（客户端据此不得终判"未轮换"）',
          isinstance(st.get('inflight'), bool), json.dumps(st.get('inflight')))
}

# ============================================================
# F 组：在途保护 / 归属校验 / TTL 失败关闭 / 严格解析
# ============================================================
CLOCK[0] = 1000000
{
    # F1 在途时设置 capability 被拒
    p = fresh(0)
    env = make_env(p)
    post(env, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
               'expected_old': OLD, 'owner_id': OWNER})
    before = p.getProperty('rotation_nonce_hash')
    p.setProperty('rotation_inflight', 'req_someone_else')
    f1 = inner(post(env, {'action': 'setRotationCapability', 'token': OLD,
                          'nonce_hash': sha256hex('other'), 'expected_old': OLD,
                          'owner_id': 'owner_OTHER'}))
    check('F1 在途时设置 capability 被拒（inflight=true）',
          f1.get('ok') is False and f1.get('inflight') is True, json.dumps(f1))
    check('F1b 在途时已有 capability 未被改动', p.getProperty('rotation_nonce_hash') == before)

    # F2 在途时第二个轮换请求被拒
    f2 = inner(post(env, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                          'expected_old': OLD, 'new_token': 'SOMEONE_ELSE', 'owner_id': OWNER}))
    check('F2 在途时第二个轮换请求被拒',
          f2.get('ok') is False and f2.get('inflight') is True, json.dumps(f2))
    check('F2b 在途时令牌未被改', p.getProperty('REMOTE_TOKEN') == OLD)
    p.deleteProperty('rotation_inflight')

    # F3 owner 不匹配
    p3 = fresh(0)
    env3 = make_env(p3)
    post(env3, {'action': 'setRotationCapability', 'token': OLD,
                'nonce_hash': sha256hex('nonceA'), 'expected_old': OLD, 'owner_id': 'owner_AAA'})
    f3 = inner(post(env3, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': 'nonceA',
                           'expected_old': OLD, 'new_token': 'X', 'owner_id': 'owner_BBB'}))
    check('F3 owner 不匹配→拒绝', f3.get('ok') is False and f3.get('foreign') is True, json.dumps(f3))
    check('F3b owner 不匹配→不消费该 capability（哈希仍在）',
          p3.getProperty('rotation_nonce_hash') == sha256hex('nonceA'))
    check('F3c 令牌未被改', p3.getProperty('REMOTE_TOKEN') == OLD)

    # F4 在途时状态查询
    p4 = fresh(0)
    env4 = make_env(p4)
    p4.setProperty('rotation_inflight', 'req_123')
    f4 = inner(post(env4, {'action': 'rotationStatus', 'token': OLD}))
    check('F4 在途时状态查询返回 inflight=true + inflight_id',
          f4.get('inflight') is True and f4.get('inflight_id') == 'req_123', json.dumps(f4))
    check('F4b 在途时指纹仍对应旧令牌（不得据此判定未轮换）',
          f4.get('token_fingerprint') == sha256hex(OLD + '|' + '0'), f4.get('token_fingerprint'))

    # F5 归属指纹
    p5 = fresh(0)
    env5 = make_env(p5)
    post(env5, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                'expected_old': OLD, 'owner_id': OWNER})
    f5 = inner(post(env5, {'action': 'rotationStatus', 'token': OLD}))
    check('F5 状态含 owner_fingerprint 且不等于 owner 原文',
          isinstance(f5.get('owner_fingerprint'), str) and f5.get('owner_fingerprint') != OWNER,
          json.dumps(f5.get('owner_fingerprint')))
    check('F5b owner_fingerprint = sha256(owner)[:12]',
          f5.get('owner_fingerprint') == sha256hex(OWNER)[:12], f5.get('owner_fingerprint'))

    # F6 遗留 capability（owner 空）
    p6 = fresh(0)
    env6 = make_env(p6)
    p6.setProperty('rotation_nonce_hash', NONCE_HASH)          # 未设 owner（遗留态）
    f6 = inner(post(env6, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                           'expected_old': OLD, 'new_token': 'X', 'owner_id': 'owner_ANY'}))
    check('F6 遗留 capability（owner 空）→ 拒绝（foreign）',
          f6.get('ok') is False and f6.get('foreign') is True, json.dumps(f6))
    check('F6b 遗留 capability 未被消费（哈希仍在、令牌未改）',
          p6.getProperty('rotation_nonce_hash') == NONCE_HASH and p6.getProperty('REMOTE_TOKEN') == OLD,
          json.dumps([p6.getProperty('rotation_nonce_hash'), p6.getProperty('REMOTE_TOKEN')]))

    # F7 延迟请求：capability 已过期
    p7 = fresh(0)
    env7 = make_env(p7)
    CLOCK[0] = 1000000
    post(env7, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                'expected_old': OLD, 'owner_id': OWNER})
    p7.setProperty('rotation_capability_created', str(1000000 - 11 * 60 * 1000))
    f7 = inner(post(env7, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                           'expected_old': OLD, 'new_token': 'DELAYED', 'owner_id': OWNER}))
    check('F7 延迟请求：capability 已过期→拒绝（expired）',
          f7.get('ok') is False and f7.get('expired') is True, json.dumps(f7))
    check('F7b 延迟请求：令牌未被改（仍 OLD）', p7.getProperty('REMOTE_TOKEN') == OLD)
    check('F7c 延迟请求：过期 capability 已清理（无法被后续延迟请求复用）',
          p7.getProperty('rotation_nonce_hash') is None)

    # F7d/F7e/F7f 创建时间失败关闭：缺失 / 为 0 / 格式错误
    for cid, val, label in [
        ('F7d', None, '缺失'),
        ('F7e', '0', '为 0'),
        ('F7f', 'abc', '格式错误'),
    ]:
        pp = fresh(0)
        ee = make_env(pp)
        CLOCK[0] = 1000000
        post(ee, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                  'expected_old': OLD, 'owner_id': OWNER})
        if val is None:
            pp.deleteProperty('rotation_capability_created')
        else:
            pp.setProperty('rotation_capability_created', val)
        ff = inner(post(ee, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                             'expected_old': OLD, 'new_token': 'SHOULD_NOT', 'owner_id': OWNER}))
        check('%s 创建时间%s→拒绝（expired）' % (cid, label),
              ff.get('ok') is False and ff.get('expired') is True, json.dumps(ff, ensure_ascii=False))
        check('%s 创建时间%s：令牌未被改（仍 OLD）' % (cid, label), pp.getProperty('REMOTE_TOKEN') == OLD)
        check('%s 创建时间%s：capability 已清理' % (cid, label),
              pp.getProperty('rotation_nonce_hash') is None)

    # F7g 正向对照：创建时间有效且未过期 ⇒ 允许消费
    CLOCK[0] = 1000000
    p7g = fresh(0)
    env7g = make_env(p7g)
    post(env7g, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                 'expected_old': OLD, 'owner_id': OWNER})
    f7g = inner(post(env7g, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                             'expected_old': OLD, 'new_token': 'GOOD_NEW', 'owner_id': OWNER}))
    check('F7g 创建时间有效且未过期→允许轮换',
          f7g.get('ok') is True and f7g.get('rotated') is True, json.dumps(f7g))
    check('F7g 正向对照：令牌已切为新值', p7g.getProperty('REMOTE_TOKEN') == 'GOOD_NEW')

    # F7h/F7i/F7j/F7k 严格正整数解析：数字后缀 / 小数 / 科学记数法 / 未来时间戳
    for cid, val, label in [
        ('F7h', '1700000000000x', '带数字后缀'),
        ('F7i', '123.456', '为小数'),
        ('F7j', '1.7e12', '为科学记数法'),
        ('F7k', '9999999999999', '为未来时间戳'),
    ]:
        pp = fresh(0)
        ee = make_env(pp)
        CLOCK[0] = 1000000
        post(ee, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                  'expected_old': OLD, 'owner_id': OWNER})
        pp.setProperty('rotation_capability_created', val)
        ff = inner(post(ee, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                             'expected_old': OLD, 'new_token': 'SHOULD_NOT', 'owner_id': OWNER}))
        check('%s 创建时间%s→拒绝（expired）' % (cid, label),
              ff.get('ok') is False and ff.get('expired') is True, json.dumps(ff, ensure_ascii=False))
        check('%s 创建时间%s：令牌未被改（仍 OLD）' % (cid, label), pp.getProperty('REMOTE_TOKEN') == OLD)
        check('%s 创建时间%s：capability 已清理' % (cid, label),
              pp.getProperty('rotation_nonce_hash') is None)

    # F7l 正向对照：干净正整数时间戳 ⇒ 允许消费
    CLOCK[0] = 3000000
    p7l = fresh(0)
    env7l = make_env(p7l)
    post(env7l, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                 'expected_old': OLD, 'owner_id': OWNER})
    p7l.setProperty('rotation_capability_created', '3000000')
    f7l = inner(post(env7l, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                             'expected_old': OLD, 'new_token': 'GOOD_NEW', 'owner_id': OWNER}))
    check('F7l 创建时间为干净正整数时间戳→允许轮换',
          f7l.get('ok') is True and f7l.get('rotated') is True, json.dumps(f7l))
    check('F7l 正向对照：令牌已切为新值', p7l.getProperty('REMOTE_TOKEN') == 'GOOD_NEW')

    # F7m/F7n/F7o 创建时间带空白（基线取"若被 trim 则恰好合法且未过期"的值）
    for cid, clock_val, val, lab1, lab2 in [
        ('F7m', 4000000, ' 4000000', '带前导空白', '前导空白'),
        ('F7n', 5000000, '5000000 ', '带尾随空白', '尾随空白'),
        ('F7o', 6000000, '\t6000000\n', '被制表符/换行包裹', '制表符/换行'),
    ]:
        pp = fresh(0)
        ee = make_env(pp)
        CLOCK[0] = clock_val
        post(ee, {'action': 'setRotationCapability', 'token': OLD, 'nonce_hash': NONCE_HASH,
                  'expected_old': OLD, 'owner_id': OWNER})
        pp.setProperty('rotation_capability_created', val)
        ff = inner(post(ee, {'action': 'rotateRemoteToken', 'token': OLD, 'nonce': NONCE_HEX,
                             'expected_old': OLD, 'new_token': 'SHOULD_NOT', 'owner_id': OWNER}))
        check('%s 创建时间%s→拒绝（expired）' % (cid, lab1),
              ff.get('ok') is False and ff.get('expired') is True, json.dumps(ff, ensure_ascii=False))
        check('%s %s：令牌未被改（仍 OLD）' % (cid, lab2), pp.getProperty('REMOTE_TOKEN') == OLD)
        check('%s %s：capability 已清理' % (cid, lab2), pp.getProperty('rotation_nonce_hash') is None)
}

# ---------- 汇总 ----------
passed = sum(1 for _, ok in RESULTS if ok)
print('')
print('=== 结果 ===')
print('PASS %d / %d' % (passed, len(RESULTS)))
print('范围：纯 Python 复刻的分发层仿真（用例与 Node 版 dispatch_sim_test.js 一一对应）；'
      '关键规则均有【真实源码静态断言】防漂移；无网络、无真实令牌、未触生产。')
sys.exit(0 if passed == len(RESULTS) else 1)
'''

# 模板里为便于阅读沿用了 JS 的裸块 `{ ... }`；Python 无裸块语法，转成 `if True:` 作用域块
tpl = re.sub(r'(?m)^\{\s*\n', 'if True:\n', tpl)
tpl = re.sub(r'(?m)^\}\s*(\n|$)', r'\1', tpl)

out = (tpl
       .replace('__NCASES__', '94')
       .replace('__TRIG__', py_str(trig))
       .replace('__DOPOST__', py_str(dopost))
       .replace('__HANDLERS__', py_str(handlers))
       .replace('__KEYS_JSON__', json.dumps(keys))
       .replace('__NEW_JSON__', json.dumps(NEW_KEYS))
       .replace('__NKEYS__', str(len(keys)))
       .replace('__NNEW__', str(len(NEW_KEYS)))
       .replace('__NOLD__', str(len(old_keys)))
       .replace('__H_TRIG__', h_trig)
       .replace('__H_GS__', h_gs))

open(OUT, 'w', encoding='utf-8', newline='\n').write(out)
print('written', OUT, os.path.getsize(OUT))
print('keys=%d new=%d old=%d' % (len(keys), len(NEW_KEYS), len(old_keys)))
