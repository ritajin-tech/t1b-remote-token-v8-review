# -*- coding: utf-8 -*-
"""下一次 REMOTE_TOKEN 轮换 —— 客户端 v5（脱敏，供审核；非直接执行）
修订（2026-09-28 第三轮，回应 Tom 复审 3 条阻断）：
  #1 竞态：结果未知时【禁止】据单次"状态查询仍显示旧令牌"就判定"未轮换"并删除暂存。
     · 服务端新增 rotation_inflight 在途标记；客户端只要看到 inflight=true 就维持 UNKNOWN 并保留暂存。
     · 判定"未轮换"需：连续两次观测均为 old、两次 inflight 均为 false、两次 counter 相同，
       且两次之间等待 settle_interval（默认 30s）。即便终判，也只把暂存标记为废弃，
       **不静默删除**（删除只能由操作员显式 --purge-escrow）。
  #2 权限：本地配置文件（含 .tmp 临时文件）显式创建/收紧为 0600 并【核验】；
     核验不通过即抛 PermissionHardeningError → 落到"服务端已换、本地写入失败"路径，暂存保留。
     不依赖系统默认权限；Windows 附加 icacls 收紧（并如实标注能否核验）。
  #3 并发/覆盖：capability 增加 owner_id。客户端不再无条件 force=true；
     仅在"同 owner 幂等重设 / 已超 TTL / 操作员显式 --force-over-foreign"三种情况才覆盖；
     轮换时带 owner_id，服务端校验归属，不匹配则拒绝且【不消费】他人在途的 capability。
前几轮已修：#A 服务端处理函数须 return JSON.stringify，客户端两层读 resp["message"]；
            #B 字段对齐真实配置 token（历史别名同步）；#C 写前暂存 write-ahead escrow。
红线：NONCE / NEW / OLD 仅存本进程内存与受保护暂存，绝不打印、绝不进 git/IMA/日志/URL。
"""
import argparse, hashlib, json, os, secrets, stat, subprocess, sys, time, uuid

try:
    import requests
except Exception:                      # 测试环境可注入 mock；真实执行需 requests
    requests = None

# ------------------------------------------------------------------
# 配置：运行期从本地凭证文件读取（脱敏，源码不含任何真值）
# ------------------------------------------------------------------
DEFAULT_CFG_REL = os.path.join('tools', '.ts_selfcheck.json')
TOKEN_FIELD = 'token'                       # 真实配置里的字段名
LEGACY_ALIASES = ('REMOTE_TOKEN', 'remote_token')
ACTION_ROTATE = 'rotateRemoteToken'         # camelCase（下划线形式分发器不命中）
ACTION_STATUS = 'rotationStatus'
ACTION_CAP = 'setRotationCapability'

ESCROW_DIRNAME = '.smcn_rotation_escrow'
DEFAULT_SETTLE_SEC = 30                     # 两次稳定观测之间的等待（防竞态误判）
DEFAULT_SETTLE_MAX_OBSERVATIONS = 3


def cfg_path():
    return os.environ.get('TS_SELFCHECK_CFG') or os.path.join(_repo_root(), DEFAULT_CFG_REL)


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    up2 = os.path.dirname(os.path.dirname(here))
    return up2 if os.path.isdir(os.path.join(up2, 'tools')) else os.getcwd()


def load_cfg(path=None):
    """读取本地凭证配置，返回 (url, old_token)。不做任何打印。"""
    p = path or cfg_path()
    with open(p, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    url = cfg.get('url')
    tok = cfg.get(TOKEN_FIELD)
    for k in LEGACY_ALIASES:
        if not tok and cfg.get(k):
            tok = cfg[k]
    if not url or not tok:
        raise SystemExit('配置缺少 url/token —— 请先在 %s 填好（内容不打印）' % p)
    return url, tok


def mask(s, head=3, tail=2):
    if s is None:
        return '<None>'
    s = str(s)
    if len(s) <= head + tail:
        return '*' * len(s)
    return '%s***%s(len=%d)' % (s[:head], s[-tail:], len(s))


def sha256_hex(s):
    return hashlib.sha256(str(s).encode('utf-8')).hexdigest()


# ------------------------------------------------------------------
# 权限加固（Tom 第三轮第 2 条）—— 显式设置 + 核验，不依赖系统默认权限
# ------------------------------------------------------------------
class PermissionHardeningError(RuntimeError):
    """凭证文件权限未达"仅本用户可读写"时抛出：绝不留下一个权限过宽的令牌文件。"""


def _nt_restrict_acl(p):
    """Windows：st_mode 无法反映 ACL，附加 icacls 收紧（去继承 + 仅本用户完全控制）。
    返回 True/False；失败仅记录，绝不冒充成功。"""
    try:
        user = os.environ.get('USERNAME') or os.environ.get('USER') or ''
        r1 = subprocess.run(['icacls', p, '/inheritance:r'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        ok = (r1.returncode == 0)
        if user:
            r2 = subprocess.run(['icacls', p, '/grant:r', user + ':F'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            ok = ok and (r2.returncode == 0)
        return ok
    except Exception:
        return False


def _nt_acl_principals(p):
    """读取 icacls 输出里的主体清单（Windows 输出为本地代码页，UTF-8/GBK 容错解码）。
    读回失败、结果为空或无法解析 ⇒ 一律按失败关闭（抛 PermissionHardeningError），
    绝不因解析为空而误判为"仅本用户可访问"。"""
    r = subprocess.run(['icacls', p], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    out = r.stdout.decode('utf-8', 'replace')
    if '\ufffd' in out:                       # 出现替换字符 ⇒ 不是 UTF-8，按 GBK 重试
        out = r.stdout.decode('gbk', 'replace')
    principals = []
    for line in out.splitlines():
        s = line.strip()
        if not s or s.startswith('已') or s.startswith('Successfully'):
            continue                          # 跳过中文/英文的"已成功处理…"状态行
        i = s.find(' ')
        if i > 0:
            principals.append(s[i + 1:].split(':')[0])
    if r.returncode != 0 or not principals:
        # 命令失败 / 结果空 / 无法解析：无法确认 ACL 已收紧，按失败关闭（绝不冒充成功）
        raise PermissionHardeningError(
            'icacls 读回失败（rc=%s，stdout 行数=%d）——无法确认 ACL 已收紧，按失败关闭'
            % (r.returncode, len(out.splitlines())))
    return principals, r.returncode


def _nt_acl_foreign(p, user):
    """返回 ACL 中**除本用户以外**的主体（空列表 = 已收紧到仅本用户）。
    读回无法核验（命令失败/为空/无法解析）时按失败关闭：抛 PermissionHardeningError，
    交由 restrict_perms 转成"权限未收紧"。"""
    principals, _rc = _nt_acl_principals(p)
    return [x for x in principals if not (user and (x == user or x.endswith('\\' + user)))]


def restrict_perms(p):
    """把 p 收紧为"仅本用户可读写"并**核验**。返回 (ok, detail)；核验不通过即抛异常。
    - POSIX：显式 chmod 0600 后核验 st_mode；group/other 仍可访问 ⇒ 抛 PermissionHardeningError。
    - Windows：chmod 0600 + `icacls /inheritance:r` + `/grant:r <user>:F`，
      随后**读回 ACL 核验**仅剩本用户；含其他主体或 icacls 失败 ⇒ 抛。
    """
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)      # 0600，显式设置
    except Exception as ex:
        raise PermissionHardeningError('chmod 0600 失败：%s' % ex)

    if os.name == 'nt':
        if not _nt_restrict_acl(p):
            raise PermissionHardeningError('Windows ACL 收紧失败（icacls 返回非 0 或不可用）')
        user = os.environ.get('USERNAME') or os.environ.get('USER') or ''
        foreign = _nt_acl_foreign(p, user)
        if foreign:
            raise PermissionHardeningError(
                'ACL 仍包含其他主体 %s ——拒绝保留该凭证文件' % foreign)
        return True, 'Windows：chmod 0600 + ACL 已核验（仅剩主体 %s）' % (user or '<unknown>')

    mode = os.stat(p).st_mode & 0o777
    if mode & 0o077:
        raise PermissionHardeningError(
            '权限未收紧（实际 %o，group/other 仍可访问）——拒绝保留该凭证文件' % mode)
    return True, '0600'


# ------------------------------------------------------------------
# 受保护暂存（write-ahead escrow）
# ------------------------------------------------------------------
def escrow_dir():
    d = os.environ.get('SMCN_ESCROW_DIR') or os.path.join(os.path.expanduser('~'), ESCROW_DIRNAME)
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, stat.S_IRWXU)              # 0700
    except Exception:
        pass
    return d


def _escrow_name(ts):
    # 用 os.urandom 而非 secrets.token_hex：后者复用 token_bytes，测试打桩时会重名
    return 'escrow_%s_pid%d_%s.json' % (ts, os.getpid(), os.urandom(4).hex())


def escrow_write(new_token, owner_id='', note=''):
    """轮换【发起前】先把 NEW 落受保护暂存（0600 + 核验）。返回路径。"""
    d = escrow_dir()
    ts = time.strftime('%Y%m%dT%H%M%S', time.gmtime())
    p = os.path.join(d, _escrow_name(ts))
    payload = {
        'created_utc': ts, 'token_field': TOKEN_FIELD, 'new_token': new_token,
        'new_token_sha256': sha256_hex(new_token), 'owner_id': owner_id,
        'state': 'armed', 'note': note,
    }
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(payload, f)
    restrict_perms(p)                      # 显式收紧 + 核验（失败即抛）
    return p


def escrow_mark_abandoned(path):
    """终判"未轮换"后：把暂存标记为废弃但**保留**（绝不静默删除，防误删仍可能生效的 NEW）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        d['state'] = 'abandoned'
        d['abandoned_utc'] = time.strftime('%Y%m%dT%H%M%S', time.gmtime())
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(d, f)
        restrict_perms(path)
        return True
    except Exception:
        return False


def newest_escrow(include_abandoned=True):
    d = escrow_dir()
    fs = sorted([x for x in os.listdir(d) if x.startswith('escrow_') and x.endswith('.json')])
    if not include_abandoned:
        keep = []
        for x in fs:
            try:
                if json.load(open(os.path.join(d, x), encoding='utf-8')).get('state') != 'abandoned':
                    keep.append(x)
            except Exception:
                pass
        fs = keep
    return os.path.join(d, fs[-1]) if fs else None


def escrow_read(path=None):
    p = path or newest_escrow()
    if not p:
        raise SystemExit('没有可用的暂存文件（escrow）')
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f), p


def escrow_purge(path):
    try:
        if os.path.exists(path):
            with open(path, 'r+', encoding='utf-8') as f:
                n = len(f.read())
                f.seek(0)
                f.write('\0' * n)
                f.truncate()
            os.remove(path)
            return True
    except Exception:
        return False
    return False


# ------------------------------------------------------------------
# 本地凭证持久化（字段对齐 + 权限加固）
# ------------------------------------------------------------------
def persist_new_token(new_token, path=None):
    """把 NEW 原子写入本地凭证配置的【token】字段；历史别名同步；权限显式收紧并核验。
    - 临时文件即以 0600 创建（不是先建默认权限再改）；
    - os.replace 后对最终文件【再次】收紧 + 核验（不依赖继承来的默认权限）；
    - 核验失败抛 PermissionHardeningError：不留一个权限过宽的令牌文件。
    """
    p = path or cfg_path()
    with open(p, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    cfg[TOKEN_FIELD] = new_token
    for k in LEGACY_ALIASES:
        if k in cfg:
            cfg[k] = new_token

    tmp = p + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # ← 创建即为 0600
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    restrict_perms(tmp)                     # 收紧 + 核验（失败即抛）
    os.replace(tmp, p)
    restrict_perms(p)                       # 替换后再次收紧 + 核验


# ------------------------------------------------------------------
# 传输（全部走 POST body；URL 不含任何令牌/参数）
# ------------------------------------------------------------------
def post_json(url, payload, timeout=15):
    """单次 POST。网络异常向上抛：由调用方按"结果未知"处理，绝不在此重试。"""
    r = requests.post(url, json=payload, timeout=timeout)
    return r.json(), r


def parse_payload(outer):
    """两层解析：outer["ok"] 判门；inner = json.loads(outer["message"]) 取业务载荷。"""
    if not isinstance(outer, dict) or not outer.get('ok'):
        return 'auth_failed', None, (outer or {}).get('error', 'outer ok=false')
    msg = outer.get('message')
    if isinstance(msg, str) and msg.startswith('unknown action'):
        return 'unknown_action', None, msg
    try:
        inner = json.loads(msg) if isinstance(msg, str) else (msg or {})
    except Exception:
        return 'server_error', None, 'message 不是可解析 JSON：%s' % str(msg)[:60]
    if not inner.get('ok'):
        return 'server_error', inner, inner.get('error', 'inner ok=false')
    return 'ok', inner, None


def set_capability(url, old, nonce_hash, owner_id, force_over_foreign=False):
    """热装 capability。**不再无条件 force**：仅同 owner / 已超 TTL / 显式覆盖三种情况服务端才放行。"""
    payload = {'action': ACTION_CAP, 'token': old, 'nonce_hash': nonce_hash,
               'expected_old': old, 'owner_id': owner_id}
    if force_over_foreign:
        payload['force_over_foreign'] = 'true'
    outer, _ = post_json(url, payload)
    kind, inner, err = parse_payload(outer)
    ok = (kind == 'ok' and inner.get('capability_set') is True)
    return ok, (inner if inner else {'error': err})


def rotation_status(url, candidate):
    """用【候选令牌本身】鉴权查询状态；令牌不对 ⇒ 外层 ok=false（真实门生效，非跳过）。
    网络异常不抛出，转成 (None, 错误串)。"""
    try:
        outer, _ = post_json(url, {'action': ACTION_STATUS, 'token': candidate})
    except Exception as ex:
        return None, 'query failed: %s' % type(ex).__name__
    if not outer.get('ok'):
        return None, outer.get('error', 'auth failed')
    kind, inner, err = parse_payload(outer)
    return (inner if kind == 'ok' else None), err


def _observe(url, NEW, old):
    """一次观测：用 NEW / OLD 分别鉴权查询，判断当前生效的是哪个 + 是否在途。
    返回 dict(observed, inflight, counter, err)；observed ∈ {'new','old',None}"""
    for cand, label in ((NEW, 'new'), (old, 'old')):
        st, err = rotation_status(url, cand)
        if not st:
            continue
        counter = st.get('counter')
        fp = st.get('token_fingerprint')
        if fp == sha256_hex(NEW + '|' + str(counter)):
            return {'observed': 'new', 'inflight': bool(st.get('inflight')),
                    'counter': counter, 'err': None}
        if fp == sha256_hex(str(old) + '|' + str(counter)):
            return {'observed': 'old', 'inflight': bool(st.get('inflight')),
                    'counter': counter, 'err': None,
                    'inflight_id': st.get('inflight_id')}
    return {'observed': None, 'inflight': None, 'counter': None, 'err': 'no candidate authenticated'}


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------
def rotate(url=None, old=None, cfg=None, force_over_foreign=False,
           settle_interval_sec=DEFAULT_SETTLE_SEC,
           max_observations=DEFAULT_SETTLE_MAX_OBSERVATIONS, owner_id=None):
    cfgp = cfg or cfg_path()
    if url is None or old is None:
        url, old = load_cfg(cfgp)

    OWNER = owner_id or uuid.uuid4().hex        # 本笔操作归属标识（防覆盖/消费他人在途准备）
    NONCE = secrets.token_bytes(32)
    NEW = secrets.token_urlsafe(48)
    nonce_hash = sha256_hex(NONCE.hex())
    req_id = 'req_' + OWNER[:12]

    # (0) write-ahead escrow：NEW 先落受保护暂存（0600）
    esc = escrow_write(NEW, owner_id=OWNER, note='rotation write-ahead')

    # (1) 一次性能力热装（受限覆盖；不再无条件 force）
    okc, info = set_capability(url, old, nonce_hash, OWNER, force_over_foreign=force_over_foreign)
    if not okc:
        escrow_purge(esc)
        if info.get('foreign'):
            return {'result': 'capability_conflict', 'error': info.get('error'),
                    'capability_age_ms': info.get('capability_age_ms'),
                    'next': '另一笔操作已热装 capability 且未过期。请等其过期（TTL 10 分钟）或'
                            '确认其确已作废后，由操作员显式加 --force-over-foreign 重跑；'
                            '本轮 NEW 作废，暂存已清除'}
        return {'result': 'capability_setup_failed', 'error': info.get('error'),
                'inflight': info.get('inflight', False),
                'next': '若 inflight=true 说明有轮换在途，稍后重跑；本轮 NEW 作废，暂存已清除'}

    # (2) 发起轮换
    try:
        outer, _ = post_json(url, {
            'action': ACTION_ROTATE, 'token': old, 'nonce': NONCE.hex(),
            'expected_old': old, 'new_token': NEW, 'owner_id': OWNER, 'request_id': req_id,
        })
    except Exception:
        outer = None
    if outer is None:
        return _resolve_unknown(url, NEW, old, esc, cfgp, settle_interval_sec, max_observations)

    kind, inner, err = parse_payload(outer)
    if kind == 'ok' and inner.get('rotated'):
        try:
            persist_new_token(NEW, cfgp)
        except Exception as ex:
            return {'result': 'rotated_server_but_persist_failed',
                    'counter': inner.get('counter'), 'escrow': esc,
                    'new_token_sha256': sha256_hex(NEW),
                    'error': '%s: %s' % (type(ex).__name__, ex),
                    'next': '用 python rotate_remote_token_client.py --recover 从暂存补写本地配置；'
                            '切勿重发轮换请求（capability 已焚毁，重发必被拒）'}
        escrow_purge(esc)
        return {'result': 'rotated', 'counter': inner.get('counter'),
                'new_token_sha256': sha256_hex(NEW)}

    if kind == 'server_error':
        escrow_purge(esc)                    # 明确拒绝：NEW 从未生效
        return {'result': 'rejected', 'error': (inner or {}).get('error') or err,
                'foreign': bool((inner or {}).get('foreign'))}

    return _resolve_unknown(url, NEW, old, esc, cfgp, settle_interval_sec, max_observations)


def _resolve_unknown(url, NEW, old, esc, cfg=None,
                     settle_interval_sec=DEFAULT_SETTLE_SEC,
                     max_observations=DEFAULT_SETTLE_MAX_OBSERVATIONS):
    """结果未知（超时/响应丢失/异常）：独立确认，**绝不据单次观测终判"未轮换"**（Tom 第三轮第 1 条）。
    规则：
      · 任一观测 inflight=true  ⇒ 维持 UNKNOWN、保留暂存（原请求可能稍后才生效）；
      · 观测到 NEW 生效且 inflight=false ⇒ confirmed_new（可交接）；
      · 判定"未轮换"需连续两次观测均为 old、inflight 均 false、counter 相同，且中间等待 settle；
        终判后仍**保留**暂存（标记 abandoned），删除只能由操作员显式 --purge-escrow。
    """
    obs_log = []
    for i in range(max(2, max_observations)):
        o = _observe(url, NEW, old)
        obs_log.append({'observed': o['observed'], 'inflight': o['inflight'], 'counter': o['counter']})

        if o['inflight']:
            return {'result': 'still_unknown', 'reason': 'inflight',
                    'escrow': esc, 'new_token_sha256': sha256_hex(NEW), 'observations': obs_log,
                    'next': '原轮换请求仍在途（rotation_inflight 置位），不得判定未轮换、不得删除暂存；'
                            '稍后重跑 --status-only 或 --recover 再确认'}

        if o['observed'] == 'new':
            try:
                persist_new_token(NEW, cfg or cfg_path())
                escrow_purge(esc)
                return {'result': 'confirmed_new', 'counter': o['counter'],
                        'new_token_sha256': sha256_hex(NEW), 'observations': obs_log}
            except Exception as ex:
                return {'result': 'confirmed_new_persist_failed', 'counter': o['counter'],
                        'escrow': esc, 'new_token_sha256': sha256_hex(NEW),
                        'error': '%s: %s' % (type(ex).__name__, ex),
                        'next': '用 --recover 从暂存补写；切勿重发轮换请求'}

        if o['observed'] == 'old':
            # 需要【连续两次稳定观测】才允许终判
            if len(obs_log) >= 2:
                prev = obs_log[-2]
                stable = (prev['observed'] == 'old' and not prev['inflight']
                          and prev['counter'] == o['counter'])
                if stable:
                    escrow_mark_abandoned(esc)      # 保留但标记废弃：绝不静默删除
                    return {'result': 'confirmed_old_unrotated', 'counter': o['counter'],
                            'escrow': esc, 'escrow_state': 'abandoned',
                            'observations': obs_log,
                            'next': '已连续两次稳定观测仍为旧令牌且无在途请求 ⇒ 判定未轮换。'
                                    '暂存已标记废弃并保留（不自动删除），确认无用后 --purge-escrow；'
                                    '可清 rotation_nonce_hash 残值后重跑'}
            if settle_interval_sec:
                time.sleep(settle_interval_sec)
            continue

        # observed=None：两个候选都鉴权失败
        if settle_interval_sec:
            time.sleep(settle_interval_sec)

    return {'result': 'still_unknown', 'reason': 'no_stable_observation',
            'escrow': esc, 'new_token_sha256': sha256_hex(NEW), 'observations': obs_log,
            'next': '间隔后重跑 --status-only 或 --recover 再确认；暂存保留 NEW，勿删'}


def recover_from_escrow(esc=None, cfg=None):
    """从受保护暂存取回 NEW：先真实鉴权 + 指纹比对，确认其确为当前生效令牌后才写入。"""
    data, p = escrow_read(esc)
    NEW = data['new_token']
    cfgp = cfg or cfg_path()
    url, cur = load_cfg(cfgp)
    st, err = rotation_status(url, NEW)
    if not st:
        raise SystemExit('暂存里的令牌无法通过服务端鉴权（可能未生效或已被再次轮换）：%s' % err)
    if st.get('inflight'):
        raise SystemExit('服务端仍有轮换在途，暂不恢复（稍后重试）')
    counter = st.get('counter')
    if st.get('token_fingerprint') != sha256_hex(NEW + '|' + str(counter)):
        raise SystemExit('指纹不匹配，拒绝写入（暂存值不是当前生效令牌）')
    persist_new_token(NEW, cfgp)
    escrow_purge(p)
    return {'result': 'recovered', 'counter': counter, 'new_token_sha256': sha256_hex(NEW)}


def status_only(url=None, old=None, cfg=None):
    cfgp = cfg or cfg_path()
    if url is None or old is None:
        url, old = load_cfg(cfgp)
    st, err = rotation_status(url, old)
    return {'reachable': st is not None, 'status': st, 'error': err,
            'using_token_sha256': sha256_hex(old)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='REMOTE_TOKEN 轮换客户端 v5（脱敏；执行须授权）')
    ap.add_argument('--rotate', action='store_true', help='执行轮换（需 Rita/生产负责人授权）')
    ap.add_argument('--recover', action='store_true', help='从受保护暂存取回 NEW 并补写本地配置')
    ap.add_argument('--status-only', action='store_true', help='只读查询当前轮换状态（不写入）')
    ap.add_argument('--purge-escrow', action='store_true', help='清除全部受保护暂存（确认不再需要后）')
    ap.add_argument('--force-over-foreign', action='store_true',
                    help='操作员显式确认后，覆盖属于另一笔操作且未过期的 capability（默认拒绝）')
    ap.add_argument('--settle-interval', type=int, default=DEFAULT_SETTLE_SEC,
                    help='两次稳定观测之间的等待秒数（默认 30；测试可设 0）')
    ap.add_argument('--cfg', default=None, help='本地凭证配置路径（默认 tools/.ts_selfcheck.json）')
    args = ap.parse_args(argv)

    if args.purge_escrow:
        d = escrow_dir()
        n = 0
        for f in os.listdir(d):
            if f.startswith('escrow_') and f.endswith('.json'):
                n += 1 if escrow_purge(os.path.join(d, f)) else 0
        print('已清除暂存文件 %d 个' % n)
        return 0
    if args.recover:
        print(json.dumps(recover_from_escrow(cfg=args.cfg), ensure_ascii=False))
        return 0
    if args.status_only:
        print(json.dumps(status_only(cfg=args.cfg), ensure_ascii=False))
        return 0
    if args.rotate:
        print(json.dumps(rotate(cfg=args.cfg, force_over_foreign=args.force_over_foreign,
                                settle_interval_sec=args.settle_interval), ensure_ascii=False))
        return 0

    print('DRY-STRUCTURE-ONLY：实际轮换须经授权后运行；不输出任何令牌值。')
    print('用法：--status-only / --rotate [--force-over-foreign] / --recover / --purge-escrow')
    return 0


if __name__ == '__main__':
    sys.exit(main())
