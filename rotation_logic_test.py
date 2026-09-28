# -*- coding: utf-8 -*-
"""rotation_logic_test.py —— REMOTE_TOKEN 轮换逻辑本地仿真测试 v5（脱敏，无真实凭据，不触生产）
修订：2026-09-28 第三轮（回应 Tom 复审 3 条阻断）

本版新增（第 5 组）：
  T17 竞态负向：轮换请求在途（rotation_inflight 置位）时，状态查询仍显示旧令牌 ⇒
      必须维持 UNKNOWN、保留暂存，**不得**判定"未轮换"、不得删除暂存。
  T18 终判门槛：判定"未轮换"必须连续两次稳定观测（同为 old、inflight 均 false、counter 相同）；
      终判后暂存只标记 abandoned 并保留，不静默删除。
  T19 在途保护：rotation_inflight 置位时 setRotationCapability 必须被拒，且不动已有 capability。
  T20 覆盖收紧：他人未过期的 capability 默认拒绝覆盖（foreign=True）；超 TTL 或显式
      force_over_foreign=true 才允许。
  T21 归属校验：owner 不匹配时轮换被拒，且**不消费**（不删除）他人在途的 capability。
  T22 权限：临时文件与最终凭证文件均显式 0600 并核验（POSIX 严格；Windows 如实标注）。
  T23 权限失败路径：核验失败 ⇒ 落到"服务端已换、本地写入失败"，暂存保留可恢复。

既有修正（前几轮）：部署断言读真实枚举产物（缺失 exit 2 不裁决）、状态查询严格走令牌门、
删除恒真条件、失败 exit 1。
范围：逻辑层仿真 + 源码静态断言，非生产执行。真实轮换须经 Rita / 生产负责人单独授权。
"""
import hashlib, json, os, re, sys, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), '-', name, ('| ' + detail) if detail else '')


def sha256s(s):
    return hashlib.sha256(str(s).encode('utf-8')).hexdigest()


# ============================================================
# 输入：真实只读枚举产物（fail-closed）
# ============================================================
DEP_FILE = os.path.join(HERE, 'deployment_evidence_20260926.json')
if not os.path.exists(DEP_FILE):
    print('FATAL: 缺少必需输入 deployment_evidence_20260926.json —— 无法裁决，退出码 2')
    sys.exit(2)
DEP = json.load(open(DEP_FILE, encoding='utf-8'))
if not DEP.get('deployments'):
    print('FATAL: 部署证据为空 —— 无法裁决，退出码 2')
    sys.exit(2)

SRC_GS = os.path.join(HERE, 'rotation_action_actual.gs')
SRC_PY = os.path.join(HERE, 'rotate_remote_token_client.py')
for p in (SRC_GS, SRC_PY):
    if not os.path.exists(p):
        print('FATAL: 缺少必需输入 %s —— 无法裁决，退出码 2' % os.path.basename(p))
        sys.exit(2)
SRC = open(SRC_GS, encoding='utf-8').read()
CLIENT_SRC = open(SRC_PY, encoding='utf-8').read()

# ============================================================
# 服务端仿真：ScriptProperties + 令牌门（严格复刻 RemoteTrigger.gs 第 40-61 行）
# ============================================================
CAP_TTL_MS = 10 * 60 * 1000
CLOCK = [1700000000000]          # 可控时钟（ms），初始设为真实纪元毫秒；capability 创建时间据此生成，恒为正数


def now_ms():
    return CLOCK[0]


class Props:
    def __init__(self, d=None): self.d = dict(d or {})
    def get(self, k): return self.d.get(k)
    def set(self, k, v): self.d[k] = str(v)
    def delete(self, k): self.d.pop(k, None)


P = Props({'REMOTE_TOKEN': 'OLD_MOCK', 'rotation_counter': '0'})

PENDING = {}                     # 延迟落地：模拟"请求已受理但尚未写入"


def srv_dispatch(body):
    token = body.get('token')
    if token != P.get('REMOTE_TOKEN'):
        return {'ok': False, 'error': 'Invalid or missing token'}
    action = str(body.get('action', '')).lower()
    fn = {'rotationstatus': tsRotationStatus,
          'setrotationcapability': tsSetRotationCapability,
          'rotateremotetoken': tsRotateRemoteToken}.get(action)
    if fn is None:
        return {'ok': True, 'message': 'unknown action: ' + action}
    return {'ok': True, 'action': action, 'message': fn(body)}


def strict_pos_int(raw, now):
    """严格解析正整数毫秒时间戳：仅纯数字串、>0、不超 safe-integer、非未来；否则 None。
    对应 gs 服务端 _parseStrictPositiveInt（v8 对 v7 的修正）。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if not re.fullmatch(r'[0-9]+', s):
        return None
    if len(s) > 16:
        return None
    n = int(s)
    if not (n > 0):
        return None
    if n > 2**53 - 1:
        return None
    if n > now:
        return None
    return n


def tsSetRotationCapability(body):
    if P.get('rotation_inflight'):
        return json.dumps({'ok': False, 'error': '有轮换请求在途，拒绝设置/覆盖 capability', 'inflight': True})
    if str(body.get('expected_old', '')) != str(P.get('REMOTE_TOKEN') or ''):
        return json.dumps({'ok': False, 'error': 'expected_old 与当前令牌不符，拒绝热装 capability'})
    h = str(body.get('nonce_hash', ''))
    if not re.fullmatch(r'[0-9a-f]{64}', h):
        return json.dumps({'ok': False, 'error': 'nonce_hash 必须是 64 位小写十六进制 SHA-256'})
    owner = str(body.get('owner_id', ''))
    if not owner:
        return json.dumps({'ok': False, 'error': '缺少 owner_id（用于防止覆盖他人在途操作）'})
    existing = P.get('rotation_nonce_hash')
    if existing:
        ex_owner = P.get('rotation_capability_owner') or ''
        created = strict_pos_int(P.get('rotation_capability_created'), now_ms())
        age = (now_ms() - created) if created is not None else (CAP_TTL_MS + 1)
        same_owner = bool(ex_owner) and ex_owner == owner
        stale = age > CAP_TTL_MS
        if not same_owner and not stale and str(body.get('force_over_foreign')) != 'true':
            return json.dumps({'ok': False,
                               'error': 'capability 已存在且属于另一笔操作，未覆盖',
                               'nonce_present': True, 'foreign': True, 'capability_age_ms': age})
    P.set('rotation_nonce_hash', h)
    P.set('rotation_capability_owner', owner)
    P.set('rotation_capability_created', str(now_ms()))
    return json.dumps({'ok': True, 'capability_set': True, 'nonce_present': True,
                       'nonce_hash_fingerprint': sha256s(h)[:12],
                       'owner_fingerprint': sha256s(owner)[:12]})


def tsRotateRemoteToken(body):
    if P.get('rotation_inflight'):
        return json.dumps({'ok': False, 'error': '已有轮换请求在途，本次未执行', 'inflight': True})
    req_id = str(body.get('request_id') or '') or ('req_' + str(now_ms()))
    P.set('rotation_inflight', req_id)
    try:
        stored = P.get('rotation_nonce_hash')
        if not stored:
            return json.dumps({'ok': False, 'error': 'capability 已消费或未设置'})
        # (b0) 归属：owner 必须存在且严格匹配（遗留 capability：哈希在、owner 空 ⇒ 拒绝）
        owner = P.get('rotation_capability_owner') or ''
        req_owner = str(body.get('owner_id', ''))
        if not owner or req_owner != owner:
            return json.dumps({'ok': False, 'error': 'capability 归属不匹配（或缺失），已中止（未消费该 capability）',
                               'foreign': True})
        # (b0b) TTL 消费校验：失败关闭——时间戳缺失/为0/无法解析 ⇒ 直接拒绝；
        #       仅当时间戳有效(正整数)且未过期才允许消费。过期 capability 一并清理。
        created_raw = P.get('rotation_capability_created')
        created = strict_pos_int(created_raw, now_ms())
        if created is None or (now_ms() - created) > CAP_TTL_MS:
            reason = 'capability 创建时间缺失或无效（须为严格正整数时间戳，不含符号/小数/指数/后缀）' if created is None else 'capability 已过期'
            P.delete('rotation_nonce_hash')
            P.delete('rotation_capability_owner')
            P.delete('rotation_capability_created')
            return json.dumps({'ok': False, 'error': reason + '，拒绝轮换（请重新热装 capability）',
                               'expired': True})
        if sha256s(str(body.get('nonce', ''))) != stored:
            return json.dumps({'ok': False, 'error': 'capability 无效'})
        P.delete('rotation_nonce_hash')
        P.delete('rotation_capability_owner')
        P.delete('rotation_capability_created')
        if P.get('REMOTE_TOKEN') != body.get('expected_old'):
            return json.dumps({'ok': False, 'error': '当前令牌与预期旧值不符，已中止；capability 已作废'})
        P.set('REMOTE_TOKEN', str(body.get('new_token')))
        c = int(P.get('rotation_counter') or '0') + 1
        P.set('rotation_counter', str(c))
        return json.dumps({'ok': True, 'rotated': True, 'counter': c, 'request_id': req_id})
    finally:
        P.delete('rotation_inflight')


def tsRotationStatus(body):
    counter = int(P.get('rotation_counter') or '0')
    fp = sha256s((P.get('REMOTE_TOKEN') or '') + '|' + str(counter))
    created = strict_pos_int(P.get('rotation_capability_created'), now_ms())
    owner = P.get('rotation_capability_owner') or ''
    inflight = P.get('rotation_inflight')
    return json.dumps({'ok': True, 'counter': counter, 'token_fingerprint': fp,
                       'inflight': bool(inflight), 'inflight_id': inflight or None,
                       'nonce_present': bool(P.get('rotation_nonce_hash')),
                       'capability_age_ms': (now_ms() - created) if created is not None else None,
                       'owner_fingerprint': (sha256s(owner)[:12] if owner else None)})


# --- 延迟落地：模拟"请求已受理、在途、尚未写入"（竞态场景用） ---
def srv_begin_deferred(body):
    """受理轮换：置位 inflight、消费 capability，但**暂不写入**新令牌。"""
    req_id = str(body.get('request_id') or 'req_deferred')
    P.set('rotation_inflight', req_id)
    P.delete('rotation_nonce_hash')
    P.delete('rotation_capability_owner')
    P.delete('rotation_capability_created')
    PENDING.clear()
    PENDING.update({'new_token': body.get('new_token'), 'expected_old': body.get('expected_old')})
    return req_id


def srv_complete_pending():
    """在途请求落地：写入新令牌、计数 +1、清除 inflight。"""
    if not PENDING:
        return False
    P.set('REMOTE_TOKEN', str(PENDING['new_token']))
    c = int(P.get('rotation_counter') or '0') + 1
    P.set('rotation_counter', str(c))
    PENDING.clear()
    P.delete('rotation_inflight')
    return True


# ============================================================
# T1–T6：服务端逻辑
# ============================================================
NONCE = 'ab12cd34ef56'
NEW = 'NEW_MOCK_TOKEN_xyz'
OWNER_A = 'owner_AAAA'
P.set('rotation_nonce_hash', sha256s(NONCE))
P.set('rotation_capability_owner', OWNER_A)
P.set('rotation_capability_created', str(now_ms()))

r1 = srv_dispatch({'action': 'rotateRemoteToken', 'token': 'OLD_MOCK', 'nonce': NONCE,
                   'expected_old': 'OLD_MOCK', 'new_token': NEW, 'owner_id': OWNER_A})
i1 = json.loads(r1['message'])
check('T1 正常轮换成功（内层载荷可解析）', r1['ok'] and i1.get('ok') and i1.get('rotated'), str(i1))
check('T1b 计数自增 0→1 / 令牌已切 NEW', P.get('rotation_counter') == '1' and P.get('REMOTE_TOKEN') == NEW)
check('T1c capability 用过即焚', P.get('rotation_nonce_hash') is None)
check('T1d 在途标记已清除（finally）', P.get('rotation_inflight') is None)

r2 = srv_dispatch({'action': 'rotateRemoteToken', 'token': NEW, 'nonce': NONCE,
  'expected_old': NEW, 'new_token': 'OTHER', 'owner_id': OWNER_A})
check('T2 重放被拒（capability 已消费）', json.loads(r2['message'])['ok'] is False, str(r2['message']))
check('T2b 重放后令牌未被改', P.get('REMOTE_TOKEN') == NEW)

NONCE3 = 'ff00aa11bb22'
P.set('rotation_nonce_hash', sha256s(NONCE3))
P.set('rotation_capability_owner', OWNER_A)
P.set('rotation_capability_created', str(now_ms()))
r3 = srv_dispatch({'action': 'rotateRemoteToken', 'token': NEW, 'nonce': NONCE3,
                   'expected_old': 'WRONG_OLD', 'new_token': 'Z', 'owner_id': OWNER_A})
check('T3 旧值不符被拒', '旧值' in json.loads(r3['message']).get('error', ''), str(r3['message']))
check('T3b 旧值不符后 capability 作废', P.get('rotation_nonce_hash') is None)
check('T3c 令牌未被改（仍 NEW）', P.get('REMOTE_TOKEN') == NEW)

NONCE4 = 'deadbeef0011'
P.set('rotation_nonce_hash', sha256s(NONCE4))
P.set('rotation_capability_owner', OWNER_A)
P.set('rotation_capability_created', str(now_ms()))
r4 = srv_dispatch({'action': 'rotateRemoteToken', 'token': NEW, 'nonce': 'WRONG_NONCE',
                   'expected_old': NEW, 'new_token': 'Z', 'owner_id': OWNER_A})
check('T4 无效 nonce 被拒', '无效' in json.loads(r4['message']).get('error', ''), str(r4['message']))
check('T4b 无效 nonce 时 capability 保留', P.get('rotation_nonce_hash') == sha256s(NONCE4))

r5 = srv_dispatch({'action': 'rotationStatus', 'token': NEW})
i5 = json.loads(r5['message'])
check('T5 用当前生效令牌查询状态 → 指纹匹配 NEW',
      r5['ok'] and i5['token_fingerprint'] == sha256s(NEW + '|' + str(i5['counter'])), str(i5))
check('T5b 用已失效的 OLD 查询 → 被令牌门拒绝（鉴权未跳过）',
      srv_dispatch({'action': 'rotationStatus', 'token': 'OLD_MOCK'})['ok'] is False)
check('T5c 无令牌查询 → 被令牌门拒绝', srv_dispatch({'action': 'rotationStatus'})['ok'] is False)

P.set('REMOTE_TOKEN', 'OLD_MOCK'); P.set('rotation_counter', '0')
r6 = srv_dispatch({'action': 'rotationStatus', 'token': 'OLD_MOCK'})
i6 = json.loads(r6['message'])
check('T6 未轮换时指纹匹配 OLD', i6['token_fingerprint'] == sha256s('OLD_MOCK|0'), str(i6))

# ============================================================
# T7：部署闭环（真实枚举产物）
# ============================================================
vers = [d.get('versionNumber') for d in DEP['deployments']]
heads = [d for d in DEP['deployments'] if d.get('isHead')]
check('T7 部署证据条目数 = %d（与枚举一致）' % DEP.get('count', -1),
      len(DEP['deployments']) == DEP.get('count'), '实际=%d' % len(DEP['deployments']))
check('T7b 无任何部署钉在临时版 v144', 144 not in vers, '版本列表=%s' % vers)
check('T7c 生产 Web App 在 HEAD 且 clean',
      len(heads) == 1 and heads[0].get('rotation_markers') == 'NONE (clean)')
check('T7d 证据含采集时点与只读方法', bool(DEP.get('capturedAt')) and 'read-only' in str(DEP.get('method', '')))

# ============================================================
# T8：源码层断言
# ============================================================
bad_log = [kw for kw in ('Logger.log', 'console.log', 'console.error') if kw in SRC]
check('T8 服务端代码无任何日志调用', not bad_log, '命中=%s' % bad_log)
check('T8b 服务端不含 64+ 位疑似真实令牌（真实正则扫描，非恒真）',
      re.search(r'[A-Za-z0-9_-]{64,}', SRC) is None)
check('T8c 处理函数按合约 return JSON.stringify（非 _rtResponse）',
      SRC.count('return JSON.stringify(') >= 4 and '_rtResponse(' not in SRC.split('// ====')[-1])
check('T8d 服务端置位/清除 rotation_inflight（finally 必清）',
      "setProperty('rotation_inflight'" in SRC and "deleteProperty('rotation_inflight')" in SRC)
check('T8e 服务端校验 capability 归属 owner（不匹配则拒绝且不消费）',
      'capability 归属不匹配' in SRC and 'rotation_capability_owner' in SRC)
check('T8f 取消无条件 force（仅同 owner / 超 TTL / 显式覆盖）',
      'force_over_foreign' in SRC and 'ROTATION_CAP_TTL_MS' in SRC)
check('T8g 客户端写【token】字段并同步历史别名',
      "TOKEN_FIELD = 'token'" in CLIENT_SRC and 'LEGACY_ALIASES' in CLIENT_SRC)
check('T8h 客户端无硬编码令牌/URL 常量',
      re.search(r"(OLD|WEBAPP)\s*=\s*['\"][A-Za-z0-9_-]{16,}", CLIENT_SRC) is None)
check('T8i 客户端按合约解析 message 内层载荷', 'json.loads(msg)' in CLIENT_SRC)
check('T8j 客户端终判需两次稳定观测（防竞态误判）',
      "obs_log[-2]" in CLIENT_SRC and 'settle_interval_sec' in CLIENT_SRC)
check('T8k 客户端显式收紧并核验文件权限（0300 相关符号齐全）',
      'PermissionHardeningError' in CLIENT_SRC and 'restrict_perms(tmp)' in CLIENT_SRC
      and 'restrict_perms(p)' in CLIENT_SRC)
check('T8l 服务端消费时强制校验 capability TTL（过期拒绝且不改令牌）',
      'capability 已过期' in SRC and 'rotation_capability_created' in SRC)
check('T8m 客户端 ACL 读回失败/空/无法解析统一按失败关闭',
      'icacls 读回失败' in CLIENT_SRC and 'PermissionHardeningError' in CLIENT_SRC)

# ============================================================
# 客户端（T9–T23）
# ============================================================
class _FakeResp:
    def __init__(self, d): self._d = d
    def json(self): return self._d


class _MockRequests:
    """严格走服务端分发与令牌门。可注入：未到达 / 已处理但响应丢失 / 延迟落地 / 动作后钩子。"""
    def __init__(self):
        self.fail_actions = set()
        self.fail_after_apply = set()
        self.defer_rotate = False
        self.hooks = {}

    def post(self, url, json=None, timeout=None):
        b = json or {}
        a = b.get('action')
        if a in self.fail_actions:
            raise RuntimeError('timeout')
        if a == 'rotateRemoteToken' and self.defer_rotate:
            srv_begin_deferred(b)           # 受理但尚未写入，inflight 置位
            raise RuntimeError('timeout (response lost)')
        resp = srv_dispatch(b)
        h = self.hooks.get(a)
        if h:
            h(b, resp)
        if a in self.fail_after_apply:
            raise RuntimeError('timeout (response lost)')
        return _FakeResp(resp)


_mock = _MockRequests()
sys.modules['requests'] = _mock
os.environ.setdefault('SMCN_ESCROW_DIR', os.path.join(tempfile.mkdtemp(), 'escrow'))
_spec = importlib.util.spec_from_file_location('client_mod', SRC_PY)
client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(client)

_tmpd = tempfile.mkdtemp()
STORE = os.path.join(_tmpd, 'cred.json')
URL = 'https://example.invalid/exec'
SETTLE = 0      # 测试期不真等；终判门槛由"两次观测"保证，不依赖墙钟


def reset_store(tok, legacy=False):
    d = {'_note': 'test', 'url': URL, 'token': tok}
    if legacy:
        d['REMOTE_TOKEN'] = tok
    with open(STORE, 'w', encoding='utf-8') as f:
        json.dump(d, f)


def store_tok():
    with open(STORE, encoding='utf-8') as f:
        return json.load(f).get('token')


def reset_server(tok, counter='0'):
    P.d = {'REMOTE_TOKEN': tok, 'rotation_counter': counter}
    PENDING.clear()


def purge_all_escrow():
    d = client.escrow_dir()
    for f in os.listdir(d):
        if f.startswith('escrow_'):
            client.escrow_purge(os.path.join(d, f))


client.secrets.token_bytes = lambda n: b'handoff_test_nonce_99'
client.secrets.token_urlsafe = lambda n: 'MOCKNEW_9f3a1c7e5b2d'

# T9 成功路径
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
r9 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
check('T9 成功路径→返回 rotated', r9.get('result') == 'rotated', str(r9))
check('T9b 本地配置 token 字段被写为 NEW', store_tok() == 'MOCKNEW_9f3a1c7e5b2d', str(r9))
check('T9c 服务端令牌已切 NEW', P.get('REMOTE_TOKEN') == 'MOCKNEW_9f3a1c7e5b2d')
check('T9d 暂存已清除', client.newest_escrow() is None)

# T10 历史别名同步
purge_all_escrow()
reset_store('OLD_MOCK', legacy=True); reset_server('OLD_MOCK', '0')
r10 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
cfg10 = json.load(open(STORE, encoding='utf-8'))
check('T10 历史别名一并同步（避免读旧字段）',
      cfg10['token'] == 'MOCKNEW_9f3a1c7e5b2d' and cfg10['REMOTE_TOKEN'] == 'MOCKNEW_9f3a1c7e5b2d')
check('T10b 本地配置无残留旧值', 'OLD_MOCK' not in json.dumps(cfg10))

# T11 响应丢失但服务端已生效 → confirmed_new
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_mock.fail_after_apply = {'rotateRemoteToken'}
r11 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
_mock.fail_after_apply = set()
check('T11 响应丢失→确认 NEW 已生效', r11.get('result') == 'confirmed_new', str(r11))
check('T11b confirmed_new→本地写入 NEW', store_tok() == 'MOCKNEW_9f3a1c7e5b2d')

# T12 拒绝路径
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_mock.hooks = {'setRotationCapability': lambda b, r: P.set('rotation_nonce_hash', sha256s('TAMPERED'))}
r12 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
_mock.hooks = {}
check('T12 拒绝路径→本地仍为 OLD', store_tok() == 'OLD_MOCK', str(r12))
check('T12b 拒绝路径→返回 rejected', r12.get('result') == 'rejected', str(r12))
check('T12c 服务端令牌未变', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T12d 暂存已清除（NEW 从未生效）', client.newest_escrow() is None)

# T13 全不可达 → still_unknown，暂存保留
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_mock.fail_actions = {'rotateRemoteToken', 'rotationStatus'}
r13 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
_mock.fail_actions = set()
check('T13 未知路径→本地仍为 OLD', store_tok() == 'OLD_MOCK')
check('T13b 返回 still_unknown', r13.get('result') == 'still_unknown', str(r13.get('reason')))
esc13 = r13.get('escrow')
check('T13c 暂存保留 NEW', bool(esc13) and os.path.exists(esc13) and
      json.load(open(esc13, encoding='utf-8'))['new_token'] == 'MOCKNEW_9f3a1c7e5b2d')

# T14/T15 持久化失败 → 暂存可恢复
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
BAD_STORE = os.path.join(_tmpd, 'no_such_dir', 'cred.json')
r14 = client.rotate(url=URL, old='OLD_MOCK', cfg=BAD_STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
check('T14 持久化失败→rotated_server_but_persist_failed',
      r14.get('result') == 'rotated_server_but_persist_failed', str(r14)[:120])
check('T14b 服务端确已切 NEW', P.get('REMOTE_TOKEN') == 'MOCKNEW_9f3a1c7e5b2d')
esc14 = r14.get('escrow')
check('T14c NEW 仍在受保护暂存', bool(esc14) and os.path.exists(esc14))
check('T14d 返回不含 NEW 明文', 'MOCKNEW_9f3a1c7e5b2d' not in
      json.dumps({k: v for k, v in r14.items() if k != 'escrow'}))
r15 = client.recover_from_escrow(esc=esc14, cfg=STORE)
check('T15 --recover 补写成功', r15.get('result') == 'recovered', str(r15))
check('T15b 恢复后本地 = NEW', store_tok() == 'MOCKNEW_9f3a1c7e5b2d')
check('T15c 恢复后暂存已清除', not os.path.exists(esc14))

# T16 恢复前校验
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
esc_bad = client.escrow_write('NOT_THE_LIVE_TOKEN')
ok16 = False
try:
    client.recover_from_escrow(esc=esc_bad, cfg=STORE)
except SystemExit:
    ok16 = True
check('T16 暂存值未生效时拒绝恢复', ok16 and store_tok() == 'OLD_MOCK')
client.escrow_purge(esc_bad)

# ============================================================
# 第 5 组：Tom 第三轮三条阻断
# ============================================================

# ---- T17 竞态：在途时不得判定"未轮换"、不得删除暂存 ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_mock.defer_rotate = True
r17 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
_mock.defer_rotate = False
check('T17 在途时→返回 still_unknown（reason=inflight）',
      r17.get('result') == 'still_unknown' and r17.get('reason') == 'inflight', str(r17)[:150])
check('T17b 在途时→绝不判定 confirmed_old_unrotated',
      r17.get('result') != 'confirmed_old_unrotated', str(r17.get('result')))
esc17 = r17.get('escrow')
check('T17c 在途时→暂存仍存在且为 armed（NEW 未被删）',
      bool(esc17) and os.path.exists(esc17) and
      json.load(open(esc17, encoding='utf-8')).get('state') == 'armed', str(esc17))
check('T17d 在途时→本地配置仍为 OLD（未交接）', store_tok() == 'OLD_MOCK')
check('T17e 观测记录含 inflight=True',
      bool(r17.get('observations')) and r17['observations'][0]['inflight'] is True,
      str(r17.get('observations')))
srv_complete_pending()                       # 在途请求随后落地
r17b = client.recover_from_escrow(esc=esc17, cfg=STORE)
check('T17f 在途请求落地后→可从暂存恢复 NEW', r17b.get('result') == 'recovered', str(r17b))
check('T17g 恢复后本地 = NEW', store_tok() == 'MOCKNEW_9f3a1c7e5b2d')

# ---- T18 终判门槛：需两次稳定观测；终判后暂存标记 abandoned 且保留 ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_mock.fail_actions = {'rotateRemoteToken'}          # 请求未到达服务端
r18 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
_mock.fail_actions = set()
check('T18 无在途且连续两次稳定观测仍为 OLD → confirmed_old_unrotated',
      r18.get('result') == 'confirmed_old_unrotated', str(r18)[:150])
check('T18b 终判前至少做过 2 次观测（单次不终判）',
      len(r18.get('observations', [])) >= 2, str(r18.get('observations')))
esc18 = r18.get('escrow')
check('T18c 终判后暂存**保留**且标记为 abandoned（不静默删除）',
      bool(esc18) and os.path.exists(esc18) and
      json.load(open(esc18, encoding='utf-8')).get('state') == 'abandoned', str(esc18))
check('T18d 本地配置仍为 OLD', store_tok() == 'OLD_MOCK')
client.escrow_purge(esc18)

# ---- T19 在途保护：inflight 置位时拒绝设置/覆盖 capability ----
purge_all_escrow()
reset_server('OLD_MOCK', '0')
CLOCK[0] = 1000000
ok_a, info_a = client.set_capability(URL, 'OLD_MOCK', sha256s('n1'), 'owner_AAA')
check('T19 基线：无在途时热装成功', ok_a is True, str(info_a))
before = P.get('rotation_nonce_hash')
P.set('rotation_inflight', 'req_someone_else')
ok_b, info_b = client.set_capability(URL, 'OLD_MOCK', sha256s('n2'), 'owner_BBB')
check('T19b 在途时热装被拒（inflight=True）',
      ok_b is False and info_b.get('inflight') is True, str(info_b))
check('T19c 在途时已有 capability 未被改动', P.get('rotation_nonce_hash') == before)
P.delete('rotation_inflight')

# ---- T20 覆盖收紧：他人未过期 capability 默认拒绝；超 TTL 或显式覆盖才允许 ----
CLOCK[0] = 2000000
ok_c, info_c = client.set_capability(URL, 'OLD_MOCK', sha256s('n3'), 'owner_CCC')   # 同 owner 幂等重设
check('T20 同 owner 幂等重设允许', ok_c is True, str(info_c))
ok_d, info_d = client.set_capability(URL, 'OLD_MOCK', sha256s('n4'), 'owner_DDD')   # 他人 + 新鲜
check('T20b 他人新鲜 capability → 默认拒绝覆盖（foreign）',
      ok_d is False and info_d.get('foreign') is True, str(info_d))
check('T20c 拒绝时原 capability 未变（仍是 owner_CCC 的哈希）',
      P.get('rotation_nonce_hash') == sha256s('n3') and P.get('rotation_capability_owner') == 'owner_CCC')
ok_e, info_e = client.set_capability(URL, 'OLD_MOCK', sha256s('n5'), 'owner_DDD',
                                     force_over_foreign=True)
check('T20d 显式 force_over_foreign=true → 允许覆盖',
      ok_e is True and P.get('rotation_nonce_hash') == sha256s('n5'), str(info_e))
CLOCK[0] = 2000000 + CAP_TTL_MS + 1                       # 推过 TTL → 陈旧
ok_f, info_f = client.set_capability(URL, 'OLD_MOCK', sha256s('n6'), 'owner_EEE')
check('T20e 已超 TTL（陈旧）→ 无需显式覆盖即可重建', ok_f is True, str(info_f))

# ---- T21 归属校验：owner 不匹配时拒绝且不消费他人 capability ----
reset_server('OLD_MOCK', '0')
CLOCK[0] = 5000000
client.set_capability(URL, 'OLD_MOCK', sha256s('nonce_ownerA'), 'owner_AAA')
r21 = srv_dispatch({'action': 'rotateRemoteToken', 'token': 'OLD_MOCK', 'nonce': 'nonce_ownerA',
                    'expected_old': 'OLD_MOCK', 'new_token': 'X', 'owner_id': 'owner_BBB'})
i21 = json.loads(r21['message'])
check('T21 owner 不匹配→拒绝', i21.get('ok') is False and i21.get('foreign') is True, str(i21))
check('T21b owner 不匹配→不消费该 capability（哈希仍在）',
      P.get('rotation_nonce_hash') == sha256s('nonce_ownerA'))
check('T21c 令牌未被改', P.get('REMOTE_TOKEN') == 'OLD_MOCK')

# ---- T22 权限：临时文件与最终文件均显式 0600 并核验 ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
seen = []
_orig_restrict = client.restrict_perms


def _spy_restrict(p):
    seen.append(p)
    return _orig_restrict(p)


client.restrict_perms = _spy_restrict
r22 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
client.restrict_perms = _orig_restrict
check('T22 轮换成功且本地已写入 NEW',
      r22.get('result') == 'rotated' and store_tok() == 'MOCKNEW_9f3a1c7e5b2d', str(r22)[:120])
check('T22b 临时文件与最终文件都被显式收紧过（含 .tmp）',
      any(x.endswith('.tmp') for x in seen) and any(x == STORE for x in seen),
      str([os.path.basename(x) for x in seen]))
check('T22c 无 .tmp 残留', not os.path.exists(STORE + '.tmp'))
mode = os.stat(STORE).st_mode & 0o777
if os.name == 'nt':
    ok22, detail22 = _orig_restrict(STORE)
    _user = os.environ.get('USERNAME') or os.environ.get('USER') or ''
    _foreign = client._nt_acl_foreign(STORE, _user)
    check('T22d Windows：chmod 0600 + ACL 收紧成功', ok22 is True, detail22)
    check('T22d2 Windows：读回 ACL 核验仅剩本用户（无 SYSTEM/Administrators/Everyone）',
          not _foreign, str(_foreign))
else:
    check('T22d 最终凭证文件权限 = 0600（group/other 无权限）', mode & 0o077 == 0, oct(mode))
esc_tmp = client.escrow_write('PERM_CHECK')
if os.name != 'nt':
    check('T22e 暂存文件权限 = 0600', (os.stat(esc_tmp).st_mode & 0o777) & 0o077 == 0,
          oct(os.stat(esc_tmp).st_mode & 0o777))
else:
    _u = os.environ.get('USERNAME') or os.environ.get('USER') or ''
    check('T22e 暂存文件 ACL 仅剩本用户（读回核验）',
          not client._nt_acl_foreign(esc_tmp, _u), str(client._nt_acl_foreign(esc_tmp, _u)))
client.escrow_purge(esc_tmp)

# ---- T23 权限失败路径：核验失败 → 落到可恢复交接 ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_orig_persist = client.persist_new_token


def _boom_perms(*a, **k):
    raise client.PermissionHardeningError('权限未收紧（模拟核验失败 0644）')


client.persist_new_token = _boom_perms
r23 = client.rotate(url=URL, old='OLD_MOCK', cfg=STORE, settle_interval_sec=SETTLE, owner_id=OWNER_A)
client.persist_new_token = _orig_persist
check('T23 权限核验失败→rotated_server_but_persist_failed',
      r23.get('result') == 'rotated_server_but_persist_failed', str(r23)[:150])
check('T23b 权限核验失败→本地配置未被写入 NEW（仍 OLD）', store_tok() == 'OLD_MOCK')
check('T23c 权限核验失败→NEW 仍在暂存（可 --recover）',
      bool(r23.get('escrow')) and os.path.exists(r23['escrow']))
check('T23d 服务端确已切 NEW（失败发生在本地持久化环节）',
      P.get('REMOTE_TOKEN') == 'MOCKNEW_9f3a1c7e5b2d')
r23b = client.recover_from_escrow(esc=r23['escrow'], cfg=STORE)
check('T23e 修正权限后可从暂存恢复', r23b.get('result') == 'recovered', str(r23b))

# ---- T24 ACL 读回失败必须按失败关闭（Tom 第四轮第 3 条） ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
_orig_princ = client._nt_acl_principals


def _boom_princ(p):
    raise client.PermissionHardeningError('icacls 读回失败（模拟 rc=1，stdout 为空）')


client._nt_acl_principals = _boom_princ               # 读回失败：应抛异常，而非返回空列表冒充"仅本用户"
_t24_ok = False
try:
    client._nt_acl_foreign(STORE, 'someuser')
except client.PermissionHardeningError:
    _t24_ok = True
client._nt_acl_principals = _orig_princ
check('T24 ACL 读回失败（rc!=0/空）→ 抛 PermissionHardeningError（失败关闭，绝不误判为仅本用户）', _t24_ok)

# T24b 端到端：restrict_perms 在 Windows 分支因 ACL 读回失败而抛异常（非 Windows 也可验证）
_orig_restrict = client._nt_restrict_acl
_orig_princ2 = client._nt_acl_principals
_orig_name = client.os.name
client._nt_restrict_acl = lambda p: True                # 模拟 icacls 收紧成功
client._nt_acl_principals = _boom_princ                # 但读回失败
client.os.name = 'nt'                                   # 强制进入 Windows 分支
_t24b_ok = False
try:
    client.restrict_perms(STORE)
except client.PermissionHardeningError:
    _t24b_ok = True
client.os.name = _orig_name
client._nt_restrict_acl = _orig_restrict
client._nt_acl_principals = _orig_princ2
check('T24b restrict_perms（Windows 分支）遇 ACL 读回失败→抛 PermissionHardeningError（留不下权限过宽文件）', _t24b_ok)

# T24c 读回 rc=0 但结果为空（无法解析）→ 同样失败关闭
_orig_princ3 = client._nt_acl_principals


def _empty_princ(p):
    raise client.PermissionHardeningError('icacls 读回失败（模拟 rc=0，stdout 为空）')


client._nt_acl_principals = _empty_princ
_t24c_ok = False
try:
    client._nt_acl_foreign(STORE, 'someuser')
except client.PermissionHardeningError:
    _t24c_ok = True
client._nt_acl_principals = _orig_princ3
check('T24c ACL 读回 rc=0 但结果为空→失败关闭（不误判为仅本用户）', _t24c_ok)

# ---- T25 遗留 capability（哈希在、owner 空）→ 拒绝且不消费 ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
P.set('rotation_nonce_hash', sha256s('legacy_nonce'))
P.delete('rotation_capability_owner')                    # 遗留：哈希在、owner 空
P.set('rotation_capability_created', str(now_ms()))
r25 = srv_dispatch({'action': 'rotateRemoteToken', 'token': 'OLD_MOCK', 'nonce': 'legacy_nonce',
                    'expected_old': 'OLD_MOCK', 'new_token': 'X', 'owner_id': 'owner_ZZZ'})
i25 = json.loads(r25['message'])
check('T25 遗留 capability（owner 空）→ 拒绝（foreign）', i25.get('ok') is False and i25.get('foreign') is True, str(i25))
check('T25b 遗留 capability 未被消费（哈希仍在、令牌未改）',
      P.get('rotation_nonce_hash') == sha256s('legacy_nonce') and P.get('REMOTE_TOKEN') == 'OLD_MOCK')

# ---- T26 消费时 TTL 校验：延迟到达的过期请求必须拒绝且不改令牌 ----
purge_all_escrow()
reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
CLOCK[0] = 1000000
client.set_capability(URL, 'OLD_MOCK', sha256s('delayed_nonce'), 'owner_AAA')
# 把已落地的 capability 创建时间推到 TTL 之前（模拟早已热装、请求延迟到达）
P.set('rotation_capability_created', str(CLOCK[0] - CAP_TTL_MS - 5000))
# 客户端已两观稳定旧值（inflight=false），延迟请求此刻才到
r26 = srv_dispatch({'action': 'rotateRemoteToken', 'token': 'OLD_MOCK', 'nonce': 'delayed_nonce',
                    'expected_old': 'OLD_MOCK', 'new_token': 'DELAYED_NEW', 'owner_id': 'owner_AAA'})
i26 = json.loads(r26['message'])
check('T26 延迟请求：capability 已过期→拒绝（expired）', i26.get('ok') is False and i26.get('expired') is True, str(i26))
check('T26b 延迟请求：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26c 延迟请求：过期 capability 已清理（无法被后续延迟请求复用）', P.get('rotation_nonce_hash') is None)

# ---- T26d/T26e/T26f 消费时创建时间失败关闭：缺失/为0/格式错误 ⇒ 拒绝且不消费（Tom 第五轮） ----
def _t26_try(mode):
    purge_all_escrow()
    reset_store('OLD_MOCK'); reset_server('OLD_MOCK', '0')
    CLOCK[0] = 1000000
    client.set_capability(URL, 'OLD_MOCK', sha256s('badts_nonce'), 'owner_BBB')
    if mode == 'missing':
        P.delete('rotation_capability_created')          # 创建时间属性完全缺失
    elif mode == 'zero':
        P.set('rotation_capability_created', '0')        # 创建时间为 0
    elif mode == 'garbage':
        P.set('rotation_capability_created', 'abc')      # 创建时间格式错误（非数字）
    elif mode == 'suffix':
        P.set('rotation_capability_created', '1700000000000x')   # 数字后追加字母（Tom 第六轮示例）
    elif mode == 'decimal':
        P.set('rotation_capability_created', '123.456')          # 小数
    elif mode == 'sci':
        P.set('rotation_capability_created', '1.7e12')           # 科学记数法
    elif mode == 'future':
        P.set('rotation_capability_created', str(now_ms() + 10 * 365 * 24 * 3600 * 1000))  # 未来时间戳
    # 'valid' 模式保留 set_capability 写入的有效时间戳
    r = srv_dispatch({'action': 'rotateRemoteToken', 'token': 'OLD_MOCK', 'nonce': 'badts_nonce',
                      'expected_old': 'OLD_MOCK', 'new_token': 'SHOULD_NOT', 'owner_id': 'owner_BBB'})
    return json.loads(r['message'])

r26d = _t26_try('missing')
check('T26d 创建时间缺失→拒绝（expired）', r26d.get('ok') is False and r26d.get('expired') is True, str(r26d))
check('T26d 创建时间缺失：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26d 创建时间缺失：capability 已清理（无法被复用）', P.get('rotation_nonce_hash') is None)

r26e = _t26_try('zero')
check('T26e 创建时间为 0→拒绝（expired）', r26e.get('ok') is False and r26e.get('expired') is True, str(r26e))
check('T26e 创建时间为 0：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26e 创建时间为 0：capability 已清理', P.get('rotation_nonce_hash') is None)

r26f = _t26_try('garbage')
check('T26f 创建时间格式错误→拒绝（expired）', r26f.get('ok') is False and r26f.get('expired') is True, str(r26f))
check('T26f 创建时间格式错误：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26f 创建时间格式错误：capability 已清理', P.get('rotation_nonce_hash') is None)

# T26h/T26i/T26j/T26k 消费时创建时间严格解析：数字后缀/小数/科学记数法/未来 ⇒ 拒绝且不消费（Tom 第六轮）
r26h = _t26_try('suffix')
check('T26h 创建时间带数字后缀(1700000000000x)→拒绝（expired）', r26h.get('ok') is False and r26h.get('expired') is True, str(r26h))
check('T26h 数字后缀：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26h 数字后缀：capability 已清理', P.get('rotation_nonce_hash') is None)

r26i = _t26_try('decimal')
check('T26i 创建时间为小数(123.456)→拒绝（expired）', r26i.get('ok') is False and r26i.get('expired') is True, str(r26i))
check('T26i 小数：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26i 小数：capability 已清理', P.get('rotation_nonce_hash') is None)

r26j = _t26_try('sci')
check('T26j 创建时间为科学记数法(1.7e12)→拒绝（expired）', r26j.get('ok') is False and r26j.get('expired') is True, str(r26j))
check('T26j 科学记数法：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26j 科学记数法：capability 已清理', P.get('rotation_nonce_hash') is None)

r26k = _t26_try('future')
check('T26k 创建时间为未来时间戳→拒绝（expired）', r26k.get('ok') is False and r26k.get('expired') is True, str(r26k))
check('T26k 未来时间戳：令牌未被改（仍 OLD_MOCK）', P.get('REMOTE_TOKEN') == 'OLD_MOCK')
check('T26k 未来时间戳：capability 已清理', P.get('rotation_nonce_hash') is None)

# T26g 正向对照：时间戳有效且未过期 ⇒ 允许消费（证明严格解析不误伤正常 capability）
r26g = _t26_try('valid')
check('T26g 创建时间有效且未过期→允许轮换', r26g.get('ok') is True and r26g.get('rotated') is True, str(r26g))
check('T26g 正向对照：令牌已切为新值', P.get('REMOTE_TOKEN') == 'SHOULD_NOT')


# ============================================================
# 汇总 + 退出码
# ============================================================
passed = sum(1 for _, c in results if c)
print('\n=== 结果 ===')
print('PASS %d / %d' % (passed, len(results)))
print('输入：deployment_evidence_20260926.json（真实只读枚举，count=%s，采集于 %s）'
      % (DEP.get('count'), DEP.get('capturedAt')))
print('范围：逻辑层仿真 + 源码静态断言 + 竞态/权限/并发负向用例；无网络、无真实令牌、未触生产。')
print('这不构成生产轮换放行；真实执行须经 Rita / 生产负责人单独授权。')
sys.exit(0 if passed == len(results) else 1)
