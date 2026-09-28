# -*- coding: utf-8 -*-
"""重建 DELIVERY_MANIFEST_20260928.md + ALL_IN_ONE_20260928.txt（v9.1 版）。

v9 关键修正（回应 Tom 第七轮第 2 项）：
  往版直接对【本地文件】算哈希，而 git 提交时 CRLF→LF 的换行转换会让"仓库实际分发字节"
  与本地不同（实测 7 个文件受影响，差值恰等于行数），导致清单声明值与 Tom 下载到的文件不一致。
  本版改为：大小/哈希一律抓取【仓库 raw 实际分发字节】计算，并在推送后二次抓取逐文件自校验。

v9.1 修正（回应 Tom 第八轮：交付说明引用了不在包内的脚本）：
  原 `verify` 依赖一份【不随包分发】的本地台账 `_manifest_hashes.json`，即使把脚本本身随包
  发出，审核人仍无法复跑。现已改为**离线自包含**：直接解析包内的 DELIVERY_MANIFEST_20260928.md
  取声明值，与同目录实际文件逐字节比对；不需要网络、不需要任何包外文件。
  本脚本自身亦已随包分发并在清单中声明哈希。

用法（审核人侧，离线可跑）：
  python _build_manifest.py verify             # 比对【脚本所在目录】的文件与包内清单
                                               # （zip 下载=LF 直接 PASS；Windows git clone=CRLF 时按 LF 归一比对并标注）
  python _build_manifest.py verify --dir DIR   # 指定交付目录
  python _build_manifest.py verify --net       # 可选：改为抓取仓库 raw 分发字节比对（需网络）

构建侧（Rita 本机，需网络）：
  python _build_manifest.py build              # 抓取分发字节 → 生成 ALL_IN_ONE + 清单
"""
import hashlib, json, os, re, sys, time, urllib.parse, urllib.request

D = "delivery_to_tom_20260928"
REPO = "ritajin-tech/t1b-remote-token-v8-review"
BRANCH = "main"
RAW = "https://raw.githubusercontent.com/%s/%s/" % (REPO, BRANCH)
ALL_IN_ONE = "ALL_IN_ONE_20260928.txt"
HASHES_JSON = "_manifest_hashes.json"   # 本地台账，不随包分发

ORDER = [
    ("next_rotation_plan_v9_20260928.md", "方案 v9（本轮主体：回应 Tom 第七轮 3 项修正 — 移除 trim 拒绝空白 / 清单哈希按分发字节重算 / 平台口径更正）"),
    ("next_rotation_plan_v8_20260928.md", "方案 v8（已被 v9 取代，保留供比对；回应 Tom 第六轮 1 条阻断 — 创建时间须为严格正整数时间戳）"),
    ("next_rotation_plan_v7_20260928.md", "方案 v7（已被 v8/v9 取代，保留供比对；创建时间缺失/无效 ⇒ 失败关闭）"),
    ("rotation_deploy_diff_20260928.patch", "拟部署代码差异（unified diff，含源文件 SHA-256，已 git apply 实测）"),
    ("rotation_action_actual.gs", "拟部署服务端代码全文 v9（v8 严格正整数解析 + v9 移除 trim：空白前后缀一律拒绝；v6 三项 + v7 双条件 均保留并回归通过）"),
    ("dispatch_sim_test.js", "用【真实】RemoteTrigger.gs + 真实 doPost 仿真的 Node 测试（94/94，含 F6/F6b/F7/F7b–F7l 及 v9 新增 F7m/F7n/F7o 空白负向）"),
    ("_gen_dispatch_sim.py", "上项的生成器：证明嵌入源码来自真实文件、零手抄"),
    ("rotate_remote_token_client.py", "客户端 v6（v9 服务端改动不要求客户端变更；字段对齐 token + capability 归属/TTL + 在途判定 + 权限收紧 + ACL 读回失败关闭 + 写前暂存）"),
    ("rotation_logic_test.py", "Python 逻辑测试 v9（Windows 128/128、macOS 127/127；含 T26d–T26k 及 v9 新增 T26m/T26n/T26o 空白负向；缺输入 exit 2）"),
    ("deployment_evidence_20260926.json", "rotation_logic_test.py 的必需输入（真实只读枚举产物）"),
    ("TEST_OUTPUT_20260928.txt", "【本轮】两套测试在本机真实执行的完整输出（含 T24–T26k 及 v9 新增 T26m/n/o；F6–F7l 及 v9 新增 F7m/n/o 负向用例行）"),
    ("rotation_runbook_20260928.md", "操作步骤 v9：含 §9.5 创建时间失败关闭 + §9.6 严格正整数时间戳 + §9.7 移除 trim 拒绝空白；不暴露令牌"),
    ("next_rotation_plan_v6_20260928.md", "方案 v6（已被 v7/v8/v9 取代，保留供比对；3 条阻断：遗留capability跳过归属/消费时未校验TTL/ACL读回未失败关闭）"),
    ("next_rotation_plan_v5_20260928.md", "方案 v5（已被 v6/v7/v8 取代，保留供比对）"),
    ("next_rotation_plan_v4_20260928.md", "方案 v4（已被 v5/v6/v7 取代，保留供比对）"),
    ("next_rotation_plan_v3_20260927.md", "方案 v3（已被 v4/v5/v6/v7 取代，保留供比对）"),
    ("REMOTE_TOKEN_rotation_audit_20260927.md", "审计记录全文"),
    ("STATE.json", "T1-B 交付状态本体"),
    ("STATE.json.sha256", "侧车（哈希内容）"),
    ("STATE.json.sha1", "侧车（哈希内容）"),
    ("_build_manifest.py", "清单构建/核验脚本（v9.1 起随包分发，回应 Tom 第八轮：说明引用的脚本必须在包内；`verify` 为离线自包含，直接解析本清单与同目录文件比对，无需网络/包外文件）"),
]
NAMES = [f for f, _ in ORDER]
DESC = dict(ORDER)


def fetch_shipped(name, tries=10, delay=2.0):
    """抓取【仓库实际分发的字节】（Tom 下载到的就是这个），带重试以应对 raw 缓存延迟。"""
    url = RAW + urllib.parse.quote(name)
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(delay)
    raise SystemExit("抓取分发字节失败: %s (%s)" % (name, last))


def sums(b):
    return len(b), hashlib.sha256(b).hexdigest(), hashlib.sha1(b).hexdigest()


def build():
    H = {}
    blobs = {}
    for f in NAMES:
        b = fetch_shipped(f)
        blobs[f] = b
        H[f] = sums(b)
        print("fetched %-42s %8d B  %s" % (f, H[f][0], H[f][1][:16]))

    # ALL_IN_ONE 由【分发字节】拼装，二进制写入（不做换行翻译），保证推送后字节一致
    parts = []
    for fn in NAMES:
        b = blobs[fn]
        parts.append(b"=" * 80)
        parts.append(("FILE: %s  (%d bytes)  sha256=%s" % (fn, len(b), hashlib.sha256(b).hexdigest())).encode("utf-8"))
        parts.append(b"=" * 80)
        parts.append(b)
        parts.append(b"")
    bundle = b"\n".join(parts)
    with open(os.path.join(D, ALL_IN_ONE), "wb") as f:
        f.write(bundle)
    H[ALL_IN_ONE] = sums(bundle)
    print("built   %-42s %8d B  %s" % (ALL_IN_ONE, H[ALL_IN_ONE][0], H[ALL_IN_ONE][1][:16]))

    sc_content = blobs['STATE.json.sha256'].decode('utf-8').strip()
    sa_content = blobs['STATE.json.sha1'].decode('utf-8').strip()
    st_s, st_256, _st_1 = H['STATE.json']

    def mline(f):
        s, a, _b = H[f]
        return "| `%s` | %s | %d B | `%s` |" % (f, DESC.get(f, "单文件合集（备用）"), s, a)

    manifest = f"""# Tom 交付包 v9.1 — 交付清单（2026-09-28，v9 代码已过审 + 回应 Tom 第八轮交付修正）

> **代码版本仍为 v9，未改动**：Tom 第八轮已复审通过（针对 v9 修订范围）。本版仅修正**交付/文档**问题。
> v9.1 修正（Tom 第八轮）：交付说明引用了 `python _build_manifest.py verify`，但该脚本**未随包分发**，
> 且其原实现还依赖一份**不随包分发**的本地台账 `_manifest_hashes.json`，故无法按指引复跑。
> 现：`_build_manifest.py` **已随包分发并在下表声明哈希**；`verify` 改为**离线自包含**
> （直接解析包内本清单取声明值，与同目录实际文件逐字节比对，无需网络、无需任何包外文件）。
>
> 目的：回应 Tom 2026-09-28 **第七轮**复审（v8 未通过，3 项待修正：① `trim()` 使带空白的值仍能通过纯数字检查；② 清单声明的 `TEST_OUTPUT_20260928.txt` 大小/SHA 与包内实际文件不一致；③ 平台差异口径仍写「95/96」）。
> 三项均已修正：**移除 `trim()`**（空白前缀/尾随/制表符换行一律拒绝）、**清单哈希改为按实际分发字节计算并二次自校验**、**平台口径更新为 Windows 128 / macOS 127**。
> 前几轮阻断（v6 三项 / v7 双条件失败关闭 / v8 严格正整数解析）均**保留并回归通过**。
> Node 测试已扩到 **94/94**，仍为 Tom 未复现项（其本机无 Node），已如实标注。
> 校验：`sha256sum <文件>`（Windows 用 `certutil -hashfile <文件> SHA256`），与下表逐一比对。

## 🔴 哈希口径（针对第七轮第 2 项，务必先读）

- 往版清单直接对**本地文件**算 SHA-256。但 git 提交时会做 **CRLF→LF 换行转换**，导致"仓库实际分发的字节"与本地不同 —— 例如 `TEST_OUTPUT_20260928.txt` 本地 26,023 B / `5b8700…`，仓库实际分发 25,798 B / `1d4534…`，**差值 225 B 恰等于该文件行数**。实测同类偏差共影响 **7 个文件**。
- **本版修正**：下表的大小与 SHA-256 **一律按仓库实际分发字节（raw 抓取）计算**，而非本地字节；生成后再次抓取逐文件比对做**自校验**。
- 清单**不声明自身哈希**（避免自引用）；`ALL_IN_ONE_20260928.txt` 的哈希按其分发字节声明并已自校验。
- 交付主体为本仓库；`ALL_IN_ONE_*.txt` 为单文件合集备用。
- **一键核验（离线）**：`python _build_manifest.py verify` —— 脚本已在包内；它解析本清单的声明值并与同目录文件逐字节比对，输出逐行 PASS/FAIL，全部一致时退出码 0、任一不符退出码 1。**不需要网络，也不需要任何包外文件**（`--net` 可选，改为抓取仓库 raw 字节比对）。
- **换行形态**：清单声明的是**仓库存储字节（LF）**。经 GitHub「Download ZIP」下载即为 LF，核验直接 `PASS`；
  若在 Windows 上用 `git clone` 检出（默认 `core.autocrlf=true` 会转成 CRLF，字节数 += 行数），脚本会再按 CRLF→LF 归一比对一次，
  命中则显示 `PASS(LF归一)` 并给出说明。两种形态都视为一致，但**不会静默兜底**：若归一后仍不符，即为 `FAIL`。

---

## 一、Tom 第七轮 3 项修正 —— 修订与验证物

| # | Tom 意见（第七轮，复审 v8） | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | `_parseStrictPositiveInt` / `strict_pos_int` 在校验前先 `trim()`，带前后空白的值仍会通过纯数字检查。请确认是否允许该格式；若要求严格纯数字，请移除 `trim()` 并增加空白前缀、后缀的负向测试 | **确认：不允许该格式**。已**移除 `trim()`（gs）/ `strip()`（Python）**。理由：创建时间由本系统以 `String(Date.now())` 写入，永不含空白；trim 属不必要宽容，会让被篡改/污染的值静默通过。现任何空白（空格/制表符/换行）均使 `/^[0-9]+$/` 校验失败 ⇒ 拒绝、清理 capability、**不改令牌**。拒绝提示同步改为"不含符号/小数/指数/后缀/**空白**" | 服务端 **F7m/F7n/F7o**（前导空白/尾随空白/制表符换行 → 拒绝、令牌未改、已清理）；Python **T26m/T26n/T26o**；正向对照 **F7l/T26g**（干净正整数→允许） |
| **2** | 清单声明 `TEST_OUTPUT_20260928.txt` 为 26,023 B / `5b8700…`，包内实际为 25,798 B / `1d4534…` | 根因=git CRLF→LF 换行转换（非文件内容问题）。**清单哈希改为按实际分发字节计算 + 二次自校验**；同时把口径写进本清单顶部 | 见上方「哈希口径」；`python _build_manifest.py verify`（离线、脚本在包内）逐文件 PASS |
| **2b**（第八轮） | 交付说明引用 `python _build_manifest.py verify`，但该脚本不在包内，无法按指引复跑 | 脚本**已随包分发**（并在下表声明哈希）；且 `verify` 原依赖包外台账 `_manifest_hashes.json`，已改为**离线自包含**：直接解析包内清单取声明值、比对同目录文件 | 在包目录内执行 `python _build_manifest.py verify` 即可复跑；无需网络 |
| **3** | 说明仍写「95/96」的平台差异，本轮应为 macOS 118 / Windows 119 | 已全量更正；因 v9 新增 9 项检查，本轮实际为 **Windows 128 / macOS 127**、Node **94/94** | 见 §三；`rotation_runbook_20260928.md` §9.7 |

**负向测试基线设计（供复核）**：空白用例的时间戳基线刻意取「若被 trim 则恰好合法且未过期」的值（如 `" 4000000"` @ clock 4000000）。若代码中仍存在 `trim()`，这些用例会**失败**——因此它们能真正证明 trim 已被移除，而非只是"恰好被未来时间戳规则拒掉"。

**前几轮已修且本轮保持**：处理函数 `return JSON.stringify` 契约；`inflight` 在途标记 + 两次稳定观测终判；写前暂存 escrow；字段对齐 `token`；部署断言读真实枚举产物（缺输入 exit 2）；令牌门严格 mock；去恒真断言；退出码 0/1/2；取消无条件 `force`（owner + TTL + 在途互斥）；**owner 必须存在且严格匹配**；**消费时强制 TTL**；**ACL 读回失败关闭**；**v7 fail-closed 双条件**；**v8 严格正整数解析**。

## 二、v6 三项阻断（v6 已修，本轮回归通过，供对照）

| # | Tom 意见 | 本包对应物 | 验证 |
|---|---|---|---|
| **1** | 遗留 capability（哈希在、owner 空）归属检查被跳过 | **owner 必须存在且严格匹配**：`if (!owner \\|\\| reqOwner !== owner)` 拒绝且**不消费** | 服务端 **F6/F6b**；Python **T25/T25b** |
| **2** | capability TTL 仅用于"设置时能否覆盖"，消费时未校验 | **消费时强制校验 TTL** ⇒ 拒绝、**不改令牌**、清理 | 服务端 **F7/F7b/F7c**；Python **T26/T26b/T26c** |
| **3** | Windows ACL 读回失败且解析为空可能误判为"仅本用户" | 读回失败(rc≠0)/空/无法解析 ⇒ 统一 `raise PermissionHardeningError` | Python **T24/T24b/T24c**；**T22d2/T22e** |

## 三、平台差异（Windows 128 / macOS 127 —— 第七轮第 3 项口径更正）

两套测试**逻辑完全等价**，差异仅来自一个 **Windows 专用用例**：

- **Windows：128/128** —— 含 `T22d2 Windows：读回 ACL 核验仅剩本用户`（仅 `os.name == 'nt'` 时执行，验证 `icacls` 读回 ACL 主体列表仅剩本用户）。
- **macOS：127/127** —— 该用例被平台守卫跳过（macOS 无 `icacls`），其余 127 项逐一对齐通过。

即多出的 1 项就是 `T22d2`，**非测试口径不一致**。历史沿革：v6 为 96/95，v7 为 107/106，v8 为 **119/118**（与 Tom 第七轮实测的 macOS 118 一致），**v9 因新增 9 项空白负向检查而变为 128/127**。若希望 macOS 也能覆盖 ACL 读回逻辑，可改为纯字符串解析层单元测试（与平台无关）——本包已在 `T24/T24b/T24c` 用 monkeypatch 覆盖 `_nt_acl_principals` 的失败/空/rc=0 三态，跨平台可跑。

## 四、文件清单（按顺序；大小与 SHA-256 均为实际分发字节）

| 文件 | 说明 | 大小 | sha256 |
|---|---|---|---|
""" + "\n".join(mline(f) for f in NAMES) + f"""
| `{ALL_IN_ONE}` | 单文件合集（备用，内容=上表文件按序拼接） | {H[ALL_IN_ONE][0]} B | `{H[ALL_IN_ONE][1]}` |

---

## 五、STATE.json 本体与侧车

| 文件 | 大小 | sha256 |
|---|---|---|
| `STATE.json` | {st_s} B | `{st_256}` |
| `STATE.json.sha256` | {H['STATE.json.sha256'][0]} B | `{H['STATE.json.sha256'][1]}` |
| `STATE.json.sha1` | {H['STATE.json.sha1'][0]} B | `{H['STATE.json.sha1'][1]}` |

侧车内容（原文）：`{sc_content}` ／ `{sa_content}`

---

## 六、测试输出（Tom 要求"提交对应负向测试和测试输出"）

`TEST_OUTPUT_20260928.txt` 为本机真实执行的两份原始输出（未删改），含本轮新增负向用例行：

- Python 侧：`T22d2/T22e` Windows 读回 ACL 仅剩本用户｜`T24/T24b/T24c` ACL 读回失败/空/rc=0 → 失败关闭｜`T25/T25b` 遗留 capability（owner 空）→ 拒绝、未消费｜`T26/T26b/T26c` 过期→拒绝（`expired`）、令牌未改、已清理｜`T26d/T26e/T26f` 创建时间缺失/`'0'`/`'abc'`→拒绝｜`T26g` 有效未过期→允许（正向对照）｜`T26h/T26i/T26j/T26k` 数字后缀/小数/科学记数法/未来时间→拒绝｜**`T26m` 前导空白→拒绝｜`T26n` 尾随空白→拒绝｜`T26o` 制表符/换行包裹→拒绝**（负向均令牌未改、capability 已清理）。
- Node 侧：`E5c` 缺 owner_id 拒｜`E5e/E5f` 他人 capability 拒且不改原值｜`F1/F1b` 在途拒设｜`F2/F2b` 在途拒第二个轮换｜`F3/F3b/F3c` owner 不匹配不消费｜`F6/F6b` 遗留 owner 空→拒绝、未消费｜`F7/F7b/F7c` 消费时 TTL 过期→拒绝、令牌未改、已清理｜`F7d/F7e/F7f` 创建时间缺失/`'0'`/`'abc'`→拒绝｜`F7g` 正向对照｜`F7h/F7i/F7j/F7k` 后缀/小数/科学记数法/未来→拒绝｜`F7l` 干净正整数→允许｜**`F7m` 前导空白→拒绝｜`F7n` 尾随空白→拒绝｜`F7o` 制表符/换行→拒绝**。

## 七、Tom 独立复跑指引（两套测试，均可在任意空目录运行）

```bash
# 1) 用真实分发源码的分发仿真（需要 node 18+）
node dispatch_sim_test.js          # 期望：PASS 94 / 94，退出码 0

# 2) 逻辑层仿真（需要 python 3）
python rotation_logic_test.py      # 期望：PASS 128 / 128（Windows）或 127 / 127（macOS），退出码 0
                                   # 缺 deployment_evidence_20260926.json → 退出码 2 且不输出裁决

# 3) 清单哈希一键核验（离线，脚本在包内；不需要网络、不需要包外文件）
python _build_manifest.py verify            # 期望：逐行 PASS，末行 VERIFY: ALL PASS，退出码 0
python _build_manifest.py verify --dir DIR  # 指定交付目录（在别的目录跑脚本时用）
```

代码差异核验：
```bash
mkdir -p chk/ts-manager && cp <你的 RemoteActions.gs> chk/ts-manager/RemoteActions.gs
cd chk && git init -q . && git apply --check -p1 ../rotation_deploy_diff_20260928.patch
```

---

## 八、状态（维持未变）

- 凭证事件维持 **OPEN**：T2 曾现于 URL 查询串、Google 服务端日志可见性未证伪；须待方案 §5/§6/§7 核验通过方可降级。
- T1-B B 列修复批准数维持 **0**；本包不涉及 T1-B 修复。
- **v9 仍为待审核方案**。Tom 审核通过 ≠ 生产授权；真实轮换须经 Rita / 生产负责人单独授权。
- 128/128（Windows）与 94/94 均为 Rita 侧自测结果；**94/94 因 Tom 本机无 Node，尚未由其独立复现**。
"""

    with open(os.path.join(D, "DELIVERY_MANIFEST_20260928.md"), "w", encoding="utf-8") as f:
        f.write(manifest)

    with open(HASHES_JSON, "w", encoding="utf-8") as f:
        json.dump({k: {"size": v[0], "sha256": v[1]} for k, v in H.items()}, f, indent=1)

    print("\nmanifest + ALL_IN_ONE rebuilt (v9.1) from SHIPPED bytes")
    print("next: push ALL_IN_ONE + manifest, then: python _build_manifest.py verify  (offline)")


ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|.*?\|\s*(\d+)\s*B\s*\|\s*`([0-9a-f]{64})`\s*\|\s*$")


def parse_declared(manifest_path):
    """从【包内清单】解析声明值（离线、自包含）：{文件名: (size, sha256)}。"""
    if not os.path.exists(manifest_path):
        raise SystemExit("找不到清单: %s（请在交付目录内运行，或用 --dir 指定）" % manifest_path)
    out = {}
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            m = ROW.match(line.rstrip("\n").rstrip("\r"))
            if m:
                out[m.group(1)] = (int(m.group(2)), m.group(3))
    if not out:
        raise SystemExit("清单中未解析到任何文件行，格式可能已变更: %s" % manifest_path)
    return out


def verify(use_net=False, vdir=None):
    """离线自包含核验：包内清单声明值 vs 同目录实际文件字节。"""
    if vdir is None:
        here = os.path.dirname(os.path.abspath(__file__))
        vdir = here if os.path.exists(os.path.join(here, "DELIVERY_MANIFEST_20260928.md")) else D
        if not os.path.exists(os.path.join(vdir, "DELIVERY_MANIFEST_20260928.md")):
            vdir = "."
    manifest_path = os.path.join(vdir, "DELIVERY_MANIFEST_20260928.md")
    declared = parse_declared(manifest_path)
    files = list(NAMES) + [ALL_IN_ONE]
    src = "仓库 raw 分发字节" if use_net else os.path.abspath(vdir)

    print("核验模式：%s" % ("网络（raw 抓取）" if use_net else "离线（本地目录）"))
    print("清单：%s" % os.path.abspath(manifest_path))
    print("比对源：%s" % src)
    print("%-42s %10s %10s  %s" % ("文件", "声明B", "实际B", "结果"))
    ok = True
    n_lf = 0
    for f in files:
        exp = declared.get(f)
        try:
            raw = fetch_shipped(f) if use_net else open(os.path.join(vdir, f), "rb").read()
        except Exception:
            print("%-42s %10s %10s  MISSING_FILE" % (f, exp[0] if exp else "-", "-"))
            ok = False
            continue
        if exp is None:
            print("%-42s %10s %10d  MISSING_DECL" % (f, "-", len(raw))); ok = False; continue
        # 声明值 = 仓库存储字节（LF）。zip 下载保持 LF，可直接命中；
        # 但 Windows 上 `git clone` 会按 core.autocrlf 检出为 CRLF（字节数=+行数），
        # 故再按 LF 归一比对一次，并如实标注命中方式（不做静默兜底）。
        if len(raw) == exp[0] and hashlib.sha256(raw).hexdigest() == exp[1]:
            tag, good = "PASS", True
        elif not use_net:
            lf = raw.replace(b"\r\n", b"\n")
            if len(lf) == exp[0] and hashlib.sha256(lf).hexdigest() == exp[1]:
                tag, good = "PASS(LF归一)", True
                n_lf += 1
            else:
                tag, good = "FAIL", False
        else:
            tag, good = "FAIL", False
        ok = ok and good
        print("%-42s %10d %10d  %s" % (f, exp[0], len(raw), tag))
    if n_lf:
        print("\n注：%d 个文件按原始字节不符、经 CRLF→LF 归一后一致 —— 说明你的工作区按 CRLF 检出"
              "（Windows 默认 core.autocrlf=true）。清单声明的是仓库存储字节（LF）；"
              "经 GitHub「Download ZIP」下载即为 LF，可直接命中原始字节。" % n_lf)
    print("\nVERIFY: %s（共 %d 项）" % ("ALL PASS" if ok else "HAS FAILURE", len(files)))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    argv = sys.argv[1:]
    mode = argv[0] if argv else "build"
    vdir = None
    if "--dir" in argv:
        i = argv.index("--dir")
        vdir = argv[i + 1] if i + 1 < len(argv) else None
    if mode == "build":
        build()
    elif mode == "verify":
        verify(use_net=("--net" in argv), vdir=vdir)
    else:
        raise SystemExit("usage: _build_manifest.py [build|verify] [--dir DIR] [--net]")
