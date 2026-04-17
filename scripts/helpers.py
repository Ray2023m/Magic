#!/usr/bin/env python3
"""
helpers.py — sync_loy_geo_mrs.sh 的统一 Python 引擎
一次调用处理所有 tag，输出全部格式，消除数千次进程启动开销。

用法:
  python3 helpers.py batch_geosite  <geosite_txt_dir> <manual_rules_dir> <out_geosite> <mrs_tasks> <workdir>
  python3 helpers.py batch_geoip    <geoip_txt_dir> <manual_rules_dir> <manual_ip_cache_from_geosite> <out_geoip> <mrs_tasks> <workdir>
  python3 helpers.py batch_manual_ip <manual_rules_dir> <out_geoip> <mrs_tasks> <workdir>

  还保留单条命令供 shell 零星调用:
  python3 helpers.py parse_clash       <yaml> <out_dir> <tag>
  python3 helpers.py merge_dedup       <geo_file> <clash_file> <out_file> <bucket_type>
  python3 helpers.py diff_new_entries   <exist_file> <new_file> <out_file> <type>
"""

import sys
import os
import re
import glob

# ═══════════════════════════════════════════════════════════════════════════════
# 通用工具
# ═══════════════════════════════════════════════════════════════════════════════

def read_lines(path):
    """读取文件非空行，文件不存在返回空列表"""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except FileNotFoundError:
        return []


def write_lines(path, lines):
    """写入行列表"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def norm_value(rule_type, value):
    if rule_type == "DOMAIN-SUFFIX":
        return value.lstrip(".")
    if rule_type in ("IP-CIDR", "IP-CIDR6"):
        return value.lower()
    return value


RE_COMMENT = re.compile(r"\s+#.*$")


def list_rule_files_by_tag(rules_dir):
    """收集规则目录中的 <tag>.yaml / <tag>.list，返回 {tag: [files...]}"""
    by_tag = {}
    if not rules_dir or not os.path.isdir(rules_dir):
        return by_tag

    # 固定顺序：yaml -> list
    for ext in ("yaml", "list"):
        for p in sorted(glob.glob(os.path.join(rules_dir, f"*.{ext}"))):
            tag = os.path.basename(p).removesuffix(f".{ext}")
            by_tag.setdefault(tag, []).append(p)
    return by_tag

def parse_clash_rule_ops(yaml_path):
    """解析规则文件，返回 [(op, rule_type, value), ...]

    op: add/remove
    简化规则：
      - DOMAIN,example.com              -> add
      - DOMAIN,example.com,remove       -> remove
    """
    if not yaml_path or yaml_path == "" or not os.path.isfile(yaml_path):
        return []

    entries = []
    with open(yaml_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # 兼容 YAML 列表前缀 "- "
            if line.startswith("- "):
                line = line[2:].strip()

            entry = RE_COMMENT.sub("", line).strip()
            if not entry or "," not in entry:
                continue

            parts = [p.strip() for p in entry.split(",")]
            if len(parts) < 2:
                continue

            op = "add"
            rule_type = parts[0].upper()
            value = parts[1]

            if len(parts) >= 3 and parts[2].strip().lower() == "remove":
                op = "remove"

            if not rule_type or not value:
                continue

            entries.append((op, rule_type, value))

    return entries


def iter_rule_ops(rule_files):
    """遍历多个规则文件，按文件顺序输出 (op, type, value)"""
    for p in (rule_files or []):
        for item in parse_clash_rule_ops(p):
            yield item

def parse_clash_entries(yaml_path):
    """解析规则文件，返回 [(rule_type, value), ...]

    兼容两种写法：
    1) YAML 列表项：- DOMAIN-SUFFIX,example.com
    2) 纯规则行：DOMAIN-SUFFIX,example.com
    """
    return [(t, v) for op, t, v in parse_clash_rule_ops(yaml_path) if op == "add"]


TYPE_TO_BUCKET = {
    "DOMAIN-SUFFIX":       "suffix",
    "DOMAIN":              "domain",
    "DOMAIN-KEYWORD":      "keyword",
    "DOMAIN-REGEX":        "regexp",
    "DOMAIN-WILDCARD":     "wildcard",
    "IP-CIDR":             "ipcidr",
    "IP-CIDR6":            "ipcidr",
    "PROCESS-NAME":        "process",
    "PROCESS-NAME-REGEX":  "process_re",
    "IP-ASN":              "asn",
}

MRS_SKIP_TYPES = {"DOMAIN-WILDCARD"}

# ═══════════════════════════════════════════════════════════════════════════════
# 统一排序
# ═══════════════════════════════════════════════════════════════════════════════
# 排序优先级：
#   1. DOMAIN          2. DOMAIN-SUFFIX     3. DOMAIN-WILDCARD
#   4. DOMAIN-KEYWORD  5. IP-CIDR/IP-CIDR6  6. IP-ASN
#   7. PROCESS-NAME / PROCESS-NAME-REGEX    8. DOMAIN-REGEX

TYPE_ORDER = {
    "DOMAIN":              0,
    "DOMAIN-SUFFIX":       1,
    "DOMAIN-WILDCARD":     2,
    "DOMAIN-KEYWORD":      3,
    "IP-CIDR":             4,
    "IP-CIDR6":            4,
    "IP-ASN":              5,
    "PROCESS-NAME":        6,
    "PROCESS-NAME-REGEX":  6,
    "DOMAIN-REGEX":        7,
}

def sort_typed_lines(lines):
    """对 [(type, value), ...] 按 TYPE_ORDER 排序，相同类型保持原序"""
    return sorted(lines, key=lambda tv: TYPE_ORDER.get(tv[0], 99))


def parse_clash_to_buckets(yaml_path):
    """解析 clash yaml 并分桶返回 dict"""
    buckets = {k: [] for k in ("suffix", "domain", "keyword", "regexp", "wildcard",
                                "ipcidr", "process", "process_re", "asn")}
    for t, v in parse_clash_entries(yaml_path):
        bucket = TYPE_TO_BUCKET.get(t)
        if bucket is None:
            continue
        if bucket == "suffix":
            v = v.lstrip(".")
        buckets[bucket].append(v)
    return buckets


def parse_clash_to_buckets_ops(yaml_path):
    """解析 clash yaml 并按 add/remove 分桶返回 (add_buckets, remove_buckets)"""
    add_buckets = {k: [] for k in ("suffix", "domain", "keyword", "regexp", "wildcard",
                                   "ipcidr", "process", "process_re", "asn")}
    remove_buckets = {k: [] for k in ("suffix", "domain", "keyword", "regexp", "wildcard",
                                      "ipcidr", "process", "process_re", "asn")}

    for op, t, v in parse_clash_rule_ops(yaml_path):
        bucket = TYPE_TO_BUCKET.get(t)
        if bucket is None:
            continue
        if bucket == "suffix":
            v = v.lstrip(".")
        target = add_buckets if op == "add" else remove_buckets
        target[bucket].append(v)

    return add_buckets, remove_buckets


def parse_clash_to_buckets_ops_many(rule_files):
    """解析多个规则文件并聚合 add/remove 分桶"""
    add_buckets = {k: [] for k in ("suffix", "domain", "keyword", "regexp", "wildcard",
                                   "ipcidr", "process", "process_re", "asn")}
    remove_buckets = {k: [] for k in ("suffix", "domain", "keyword", "regexp", "wildcard",
                                      "ipcidr", "process", "process_re", "asn")}

    for p in (rule_files or []):
        a, r = parse_clash_to_buckets_ops(p)
        for k in add_buckets:
            add_buckets[k].extend(a.get(k, []))
            remove_buckets[k].extend(r.get(k, []))

    return add_buckets, remove_buckets


def remove_vals_from_list(values, remove_vals, bucket_type):
    """按 bucket 归一化删除条目，保持剩余顺序"""
    if not values or not remove_vals:
        return list(values)

    remove_keys = set()
    for rv in remove_vals:
        if bucket_type == "suffix":
            remove_keys.add(rv.lstrip("."))
        elif bucket_type == "ipcidr":
            remove_keys.add(rv.lower())
        else:
            remove_keys.add(rv)

    out = []
    for v in values:
        if bucket_type == "suffix":
            key = v.lstrip(".")
        elif bucket_type == "ipcidr":
            key = v.lower()
        else:
            key = v
        if key in remove_keys:
            continue
        out.append(v)
    return out


def merge_dedup_lists(geo_vals, clash_vals, bucket_type):
    """合并去重，返回合并后列表"""
    seen = set()
    order = []
    for val in geo_vals + clash_vals:
        if bucket_type == "suffix":
            key = val.lstrip(".")
        elif bucket_type == "ipcidr":
            key = val.lower()
        else:
            key = val
        if key not in seen:
            seen.add(key)
            order.append(val)
    return order


# ═══════════════════════════════════════════════════════════════════════════════
# 解析 v2dat 解包的 geosite txt
# ═══════════════════════════════════════════════════════════════════════════════

def parse_geosite_txt(filepath):
    """解析 v2dat 的 geosite txt，返回分桶 dict"""
    buckets = {"suffix": [], "domain": [], "keyword": [], "regexp": []}
    for line in read_lines(filepath):
        if line.startswith("keyword:"):
            buckets["keyword"].append(line[8:])
        elif line.startswith("regexp:"):
            buckets["regexp"].append(line[7:])
        elif line.startswith("full:"):
            buckets["domain"].append(line[5:])
        else:
            if line.startswith("."):
                buckets["suffix"].append(line)
            else:
                buckets["suffix"].append("." + line)
    return buckets


# ═══════════════════════════════════════════════════════════════════════════════
# 单 tag 全格式输出（内存中完成，不启动子进程）
# ═══════════════════════════════════════════════════════════════════════════════

def emit_geosite_tag(tag, buckets, clash_rule_files, out_geosite,
                     mrs_tasks, workdir):
    """
    为一个 geosite tag 输出全部格式。
    buckets: {"suffix":[], "domain":[], "keyword":[], "regexp":[],
              "wildcard":[], "process":[], "process_re":[]}
              注意：不含 ipcidr/asn（由 clash_extras 从 clash_yaml 中提取）
    clash_rule_files: 规则文件路径列表（.yaml/.list）
    返回 (extra_ipcidr_list, extra_asn_list) 供 geoip 阶段使用
    """
    suffix   = buckets.get("suffix", [])
    domain   = buckets.get("domain", [])
    keyword  = buckets.get("keyword", [])
    regexp   = buckets.get("regexp", [])
    wildcard = buckets.get("wildcard", [])
    process  = buckets.get("process", [])
    process_re = buckets.get("process_re", [])

    # 所有 geo 行（type, value）— 仅域名类 + 进程类，不含 IP
    geo_lines = (
        [("DOMAIN-SUFFIX", v.lstrip(".")) for v in suffix] +
        [("DOMAIN", v) for v in domain] +
        [("DOMAIN-KEYWORD", v) for v in keyword] +
        [("DOMAIN-REGEX", v) for v in regexp] +
        [("DOMAIN-WILDCARD", v) for v in wildcard] +
        [("PROCESS-NAME", v) for v in process] +
        [("PROCESS-NAME-REGEX", v) for v in process_re]
    )

    # remove 集合（同 yaml 内 remove 优先）
    remove_sets = {}
    for op, t, v in iter_rule_ops(clash_rule_files):
        if op != "remove":
            continue
        remove_sets.setdefault(t, set()).add(norm_value(t, v))

    # 先从 geo 基础数据中删除
    if remove_sets:
        geo_lines = [
            (t, v) for (t, v) in geo_lines
            if norm_value(t, v) not in remove_sets.get(t, set())
        ]

    # 构建 geo_seen 用于 clash 去重（不含 ipcidr/asn，让 IP 类条目通过 extras 输出）
    geo_seen = {}
    for t, v in geo_lines:
        geo_seen.setdefault(t, set()).add(norm_value(t, v))

    # clash extras（包含域名类 + IP 类 + 进程类，与 geo_seen 去重）
    clash_extras = []  # [(type, value), ...]
    clash_seen = {}
    for op, t, v in iter_rule_ops(clash_rule_files):
        if op != "add":
            continue
        nv = norm_value(t, v)
        if nv in remove_sets.get(t, set()):
            continue
        if nv in geo_seen.get(t, set()):
            continue
        if nv in clash_seen.get(t, set()):
            continue
        clash_seen.setdefault(t, set()).add(nv)
        clash_extras.append((t, v))

    # clash_extras 包含 IP-CIDR/IP-ASN 等，会被追加进 list
    all_lines = sort_typed_lines(geo_lines + clash_extras)

    # ── list（geosite 侧 IP 条目加 ,no-resolve）─────────────────────────
    list_out = []
    for t, v in all_lines:
        if t in ("IP-CIDR", "IP-CIDR6", "IP-ASN"):
            list_out.append(f"{t},{v},no-resolve")
        else:
            list_out.append(f"{t},{v}")
    write_lines(os.path.join(out_geosite, f"{tag}.list"), list_out)

    # ── mrs 源文件（suffix + domain，跳过 wildcard）─────────────────────
    # mrs 排序：domain 在前，suffix 在后
    mrs_src = os.path.join(workdir, "gs_mrs", f"{tag}.txt")
    os.makedirs(os.path.dirname(mrs_src), exist_ok=True)
    mrs_domain = [v for t, v in all_lines if t == "DOMAIN"]
    mrs_suffix = [v for t, v in all_lines if t == "DOMAIN-SUFFIX"]
    mrs_lines = list(mrs_domain) + [v if v.startswith(".") else "." + v for v in mrs_suffix]
    if mrs_lines:
        write_lines(mrs_src, mrs_lines)
        mrs_tasks.append(f"domain\t{mrs_src}\t{os.path.join(out_geosite, f'{tag}.mrs')}")

    # 返回 clash 带来的 IP 条目供 geoip 使用
    extra_ipcidr = []
    extra_asn = []
    for t, v in clash_extras:
        if t in ("IP-CIDR", "IP-CIDR6"):
            extra_ipcidr.append(v)
        elif t == "IP-ASN":
            extra_asn.append(v)
    return extra_ipcidr, extra_asn


def emit_geoip_tag(tag, ipcidr_lines, asn_lines, out_geoip,
                   mrs_tasks):
    """为一个 geoip tag 输出全部格式（纯 Loyalsoldier 数据）
    geoip 侧不加 no-resolve"""
    # 构建 typed lines 用于排序
    typed = []
    for v in ipcidr_lines:
        t = "IP-CIDR6" if ":" in v else "IP-CIDR"
        typed.append((t, v))
    for v in asn_lines:
        typed.append(("IP-ASN", v))
    typed = sort_typed_lines(typed)

    # ── list（geoip 不加 no-resolve）──
    list_out = [f"{t},{v}" for t, v in typed]
    write_lines(os.path.join(out_geoip, f"{tag}.list"), list_out)

    # mrs 先不登记，等 clash merge 后再登记（见 batch_geoip）


# ═══════════════════════════════════════════════════════════════════════════════
# batch_geosite：一次处理所有 geosite tag
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_batch_geosite(geosite_txt_dir, clash_dir, out_geosite,
                      mrs_tasks_file, workdir):
    os.makedirs(out_geosite, exist_ok=True)

    mrs_tasks = []
    processed = set()
    clash_ip_cache = {}  # tag -> (ipcidr_list, asn_list)

    ok = 0
    skip = 0
    clash_files_by_tag = list_rule_files_by_tag(clash_dir)

    # ── 1. 处理 Loyalsoldier geosite txt ─────────────────────────────────
    txt_files = sorted(glob.glob(os.path.join(geosite_txt_dir, "*.txt")))
    for f in txt_files:
        base = os.path.basename(f)
        tag = base
        if tag.startswith("geosite_"):
            tag = tag[8:]
        tag = tag.removesuffix(".txt")

        geo_buckets = parse_geosite_txt(f)

        # clash 融合（只融合域名/进程/通配类桶，ipcidr/asn 单独缓存）
        clash_rule_files = clash_files_by_tag.get(tag, [])
        clash_ipcidr = []
        if clash_rule_files:
            print(f"[MERGE] geosite/{tag} <- {', '.join(clash_rule_files)}")
            cb_add, cb_remove = parse_clash_to_buckets_ops_many(clash_rule_files)
            for btype in ("suffix", "domain", "keyword", "regexp",
                          "wildcard", "process", "process_re"):
                geo_buckets.setdefault(btype, [])
                geo_buckets[btype] = merge_dedup_lists(
                    geo_buckets[btype], cb_add.get(btype, []), btype)
                geo_buckets[btype] = remove_vals_from_list(
                    geo_buckets[btype], cb_remove.get(btype, []), btype)
            # ipcidr/asn 单独缓存，不放进 geo_buckets
            clash_ipcidr = remove_vals_from_list(
                cb_add.get("ipcidr", []), cb_remove.get("ipcidr", []), "ipcidr")

        geo_buckets.setdefault("wildcard", [])
        geo_buckets.setdefault("process", [])
        geo_buckets.setdefault("process_re", [])

        # 检查空
        has_data = any(geo_buckets.get(k) for k in
                       ("suffix", "domain", "keyword", "regexp", "wildcard",
                        "process", "process_re")) or clash_ipcidr
        if not has_data:
            skip += 1
            processed.add(tag)
            continue

        ci, ca = emit_geosite_tag(
            tag, geo_buckets, clash_rule_files,
            out_geosite,
            mrs_tasks, workdir)

        # 缓存 clash 带来的 IP 条目（extra_ipcidr 已去重，直接使用）
        all_ci = ci
        all_ca = ca
        if all_ci or all_ca:
            clash_ip_cache[tag] = (all_ci, all_ca)

        processed.add(tag)
        ok += 1

    print(f"[INFO] geosite geo pass: ok={ok}  skipped_empty={skip}")

    # ── 2. clash-only geosite ────────────────────────────────────────────
    clash_only_ok = 0
    if os.path.isdir(clash_dir):
        for tag in sorted(clash_files_by_tag):
            if tag in processed:
                continue

            rule_files = clash_files_by_tag.get(tag, [])
            print(f"[CLASH-ONLY] geosite/{tag} <- {', '.join(rule_files)}")
            cb_add, cb_remove = parse_clash_to_buckets_ops_many(rule_files)

            # 构建 buckets（不含 ipcidr/asn）
            buckets = {
                "suffix": remove_vals_from_list(cb_add.get("suffix", []), cb_remove.get("suffix", []), "suffix"),
                "domain": remove_vals_from_list(cb_add.get("domain", []), cb_remove.get("domain", []), "domain"),
                "keyword": remove_vals_from_list(cb_add.get("keyword", []), cb_remove.get("keyword", []), "keyword"),
                "regexp": remove_vals_from_list(cb_add.get("regexp", []), cb_remove.get("regexp", []), "regexp"),
                "wildcard": remove_vals_from_list(cb_add.get("wildcard", []), cb_remove.get("wildcard", []), "wildcard"),
                "process": remove_vals_from_list(cb_add.get("process", []), cb_remove.get("process", []), "process"),
                "process_re": remove_vals_from_list(cb_add.get("process_re", []), cb_remove.get("process_re", []), "process_re"),
            }
            clash_ipcidr = remove_vals_from_list(cb_add.get("ipcidr", []), cb_remove.get("ipcidr", []), "ipcidr")

            has_data = any(buckets.get(k) for k in
                           ("suffix", "domain", "keyword", "regexp", "wildcard",
                            "process", "process_re")) or clash_ipcidr
            if not has_data:
                continue

            ci, ca = emit_geosite_tag(
                tag, buckets, rule_files,
                out_geosite,
                mrs_tasks, workdir)

            all_ci = ci
            all_ca = ca
            if all_ci or all_ca:
                clash_ip_cache[tag] = (all_ci, all_ca)

            processed.add(tag)
            clash_only_ok += 1

    print(f"[INFO] geosite clash-only: ok={clash_only_ok}")

    # 写出编译任务
    with open(mrs_tasks_file, "a", encoding="utf-8") as f:
        for line in mrs_tasks:
            f.write(line + "\n")
    # 保存 clash_ip 缓存供 geoip 阶段使用
    clash_ip_dir = os.path.join(workdir, "clash_ip")
    os.makedirs(clash_ip_dir, exist_ok=True)
    for tag, (ci, ca) in clash_ip_cache.items():
        write_lines(os.path.join(clash_ip_dir, f"{tag}.ipcidr.txt"), ci)
        write_lines(os.path.join(clash_ip_dir, f"{tag}.asn.txt"), ca)


# ═══════════════════════════════════════════════════════════════════════════════
# batch_geoip：一次处理所有 geoip tag
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_batch_geoip(geoip_txt_dir, clash_dir, clash_ip_from_geosite_dir,
                    out_geoip, mrs_tasks_file, workdir):
    os.makedirs(out_geoip, exist_ok=True)

    mrs_tasks = []
    processed = set()
    clash_files_by_tag = list_rule_files_by_tag(clash_dir)

    ok = 0

    txt_files = sorted(glob.glob(os.path.join(geoip_txt_dir, "*.txt")))
    for f in txt_files:
        base = os.path.basename(f)
        tag = base
        if tag.startswith("geoip_"):
            tag = tag[6:]
        tag = tag.removesuffix(".txt")

        ipcidr_lines = read_lines(f)
        if not ipcidr_lines:
            continue

        # 生成 mihomo 规则格式（纯 Loyalsoldier 数据）
        emit_geoip_tag(tag, ipcidr_lines, [], out_geoip,
                       mrs_tasks)

        # clash 合并后的 mrs（用合并后数据覆盖纯 geo 数据）
        # 先收集所有需要合并的 IP 条目
        merged_cidr = list(ipcidr_lines)
        merged_cidr_seen = set(v.lower() for v in ipcidr_lines)

        # 从 geosite 阶段缓存的 clash IP 条目
        ci_cache_file = os.path.join(clash_ip_from_geosite_dir, f"{tag}.ipcidr.txt")
        for v in read_lines(ci_cache_file):
            nv = v.lower()
            if nv not in merged_cidr_seen:
                merged_cidr_seen.add(nv)
                merged_cidr.append(v)

        remove_cidr = set()

        # 直接以 geoip tag 命名的扩展规则文件（.yaml/.list）
        clash_rule_files = clash_files_by_tag.get(tag, [])
        if clash_rule_files:
            print(f"[MERGE] geoip/{tag} <- {', '.join(clash_rule_files)}")
            for op, t, v in iter_rule_ops(clash_rule_files):
                if t in ("IP-CIDR", "IP-CIDR6"):
                    nv = v.lower()
                    if op == "remove":
                        remove_cidr.add(nv)
                    else:
                        if nv not in merged_cidr_seen:
                            merged_cidr_seen.add(nv)
                            merged_cidr.append(v)

        if remove_cidr:
            merged_cidr = [v for v in merged_cidr if v.lower() not in remove_cidr]

        # mrs 用合并后数据（最终版本，覆盖 emit_geoip_tag 里可能登记的）
        if merged_cidr:
            mrs_src = os.path.join(workdir, "geoip_mrs", f"{tag}.txt")
            os.makedirs(os.path.dirname(mrs_src), exist_ok=True)
            write_lines(mrs_src, merged_cidr)
            mrs_tasks.append(f"ipcidr\t{mrs_src}\t{os.path.join(out_geoip, f'{tag}.mrs')}")

        processed.add(tag)
        ok += 1

    print(f"[INFO] geoip geo pass: ok={ok}")

    # ── clash-only geoip ─────────────────────────────────────────────────
    clash_only_ok = 0
    if os.path.isdir(clash_dir):
        for tag in sorted(clash_files_by_tag):
            if tag in processed:
                continue

            # 尝试从 geosite 缓存获取 IP 条目
            ci_file = os.path.join(clash_ip_from_geosite_dir, f"{tag}.ipcidr.txt")
            ipcidr = read_lines(ci_file) if os.path.isfile(ci_file) else []
            ipcidr_seen = set(v.lower() for v in ipcidr)
            remove_cidr = set()

            # 叠加当前 tag 的规则文件 add/remove
            for op, t, v in iter_rule_ops(clash_files_by_tag.get(tag, [])):
                if t not in ("IP-CIDR", "IP-CIDR6"):
                    continue
                nv = v.lower()
                if op == "remove":
                    remove_cidr.add(nv)
                else:
                    if nv not in ipcidr_seen:
                        ipcidr_seen.add(nv)
                        ipcidr.append(v)

            if remove_cidr:
                ipcidr = [v for v in ipcidr if v.lower() not in remove_cidr]

            if not ipcidr:
                continue

            print(f"[CLASH-ONLY] geoip/{tag} <- {', '.join(clash_files_by_tag.get(tag, []))} (mrs only)")
            mrs_src = os.path.join(workdir, "geoip_mrs", f"{tag}.txt")
            os.makedirs(os.path.dirname(mrs_src), exist_ok=True)
            write_lines(mrs_src, ipcidr)
            mrs_tasks.append(f"ipcidr\t{mrs_src}\t{os.path.join(out_geoip, f'{tag}.mrs')}")
            clash_only_ok += 1

    print(f"[INFO] geoip clash-only: ok={clash_only_ok}")

    with open(mrs_tasks_file, "a", encoding="utf-8") as f:
        for line in mrs_tasks:
            f.write(line + "\n")

# ═══════════════════════════════════════════════════════════════════════════════
# batch_manual_ip：处理 Manual_Rules/ 中的 IP 规则，合并进 Rules/mihomo/geoip
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_batch_manual_ip(clash_ip_dir, out_geoip,
                       mrs_tasks_file, workdir):
    if not os.path.isdir(clash_ip_dir):
        print("[INFO] Manual_Rules(IP): ok=0")
        return

    mrs_tasks = []
    ok = 0

    files_by_tag = list_rule_files_by_tag(clash_ip_dir)

    for tag in sorted(files_by_tag):
        rule_files = files_by_tag[tag]
        print(f"[MANUAL-IP] processing {tag} <- {', '.join(rule_files)}")

        cb_add, cb_remove = parse_clash_to_buckets_ops_many(rule_files)
        ci_ipcidr_add = cb_add.get("ipcidr", [])
        ci_asn_add = cb_add.get("asn", [])
        ci_ipcidr_remove = cb_remove.get("ipcidr", [])
        ci_asn_remove = cb_remove.get("asn", [])

        if not ci_ipcidr_add and not ci_asn_add and not ci_ipcidr_remove and not ci_asn_remove:
            print(f"[MANUAL-IP] {tag}: no IP entries, skip")
            continue

        # 现有数据（从已生成的 list 文件读取）
        exist_list = os.path.join(out_geoip, f"{tag}.list")
        exist_cidr_list = []
        exist_asn_list = []
        for line in read_lines(exist_list):
            if line.startswith("IP-CIDR6,"):
                exist_cidr_list.append(line[9:])
            elif line.startswith("IP-CIDR,"):
                exist_cidr_list.append(line[8:])
            elif line.startswith("IP-ASN,"):
                exist_asn_list.append(line[7:])

        # 先按 remove 删除
        remove_cidr_set = set(v.lower() for v in ci_ipcidr_remove)
        remove_asn_set = set(ci_asn_remove)

        kept_cidr = [v for v in exist_cidr_list if v.lower() not in remove_cidr_set]
        kept_asn = [v for v in exist_asn_list if v not in remove_asn_set]

        kept_cidr_seen = set(v.lower() for v in kept_cidr)
        kept_asn_seen = set(kept_asn)

        # 再按 add 补充
        add_cidr = []
        for v in ci_ipcidr_add:
            nv = v.lower()
            if nv not in kept_cidr_seen:
                kept_cidr_seen.add(nv)
                add_cidr.append(v)

        add_asn = []
        for v in ci_asn_add:
            if v not in kept_asn_seen:
                kept_asn_seen.add(v)
                add_asn.append(v)

        final_cidr = kept_cidr + add_cidr
        final_asn = kept_asn + add_asn

        if final_cidr == exist_cidr_list and final_asn == exist_asn_list:
            print(f"[MANUAL-IP] {tag}: no new entries, skip")
            continue

        print(f"[MANUAL-IP] {tag}: +{len(add_cidr)} CIDRs  +{len(add_asn)} ASNs  -{len(ci_ipcidr_remove)} CIDRs  -{len(ci_asn_remove)} ASNs")

        dst_list = os.path.join(out_geoip, f"{tag}.list")
        dst_mrs  = os.path.join(out_geoip, f"{tag}.mrs")

        # list 全量重写
        list_out = []
        for v in final_cidr:
            t = "IP-CIDR6" if ":" in v else "IP-CIDR"
            list_out.append(f"{t},{v}")
        for v in final_asn:
            list_out.append(f"IP-ASN,{v}")
        write_lines(dst_list, list_out)

        # mrs（全量重编译）
        all_cidr_list = list(final_cidr)
        if all_cidr_list:
            mrs_src = os.path.join(workdir, "ci_mrs", f"{tag}.txt")
            os.makedirs(os.path.dirname(mrs_src), exist_ok=True)
            write_lines(mrs_src, all_cidr_list)
            mrs_tasks.append(f"ipcidr\t{mrs_src}\t{dst_mrs}")
        elif os.path.exists(dst_mrs):
            os.remove(dst_mrs)

        ok += 1

    print(f"[INFO] Manual_Rules(IP): ok={ok}")

    with open(mrs_tasks_file, "a", encoding="utf-8") as f:
        for line in mrs_tasks:
            f.write(line + "\n")

# ═══════════════════════════════════════════════════════════════════════════════
# 兼容旧命令（shell 零星调用）
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_parse_clash(yaml_path, out_dir, tag):
    buckets = parse_clash_to_buckets(yaml_path)
    os.makedirs(out_dir, exist_ok=True)
    for bname, items in buckets.items():
        out_path = os.path.join(out_dir, f"{tag}.{bname}.clash.txt")
        write_lines(out_path, items)

def cmd_merge_dedup(geo_file, clash_file, out_file, bucket_type):
    result = merge_dedup_lists(read_lines(geo_file), read_lines(clash_file), bucket_type)
    write_lines(out_file, result)

def cmd_diff_new_entries(exist_file, new_file, out_file, entry_type):
    if entry_type == "cidr":
        exist = set(v.strip().lower() for v in read_lines(exist_file))
    else:
        exist = set(v.strip() for v in read_lines(exist_file))
    new = []
    seen = set()
    for v in read_lines(new_file):
        k = v.lower() if entry_type == "cidr" else v
        if k not in exist and k not in seen:
            seen.add(k)
            new.append(v)
    write_lines(out_file, new)

# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

COMMANDS = {
    "batch_geosite":    lambda a: cmd_batch_geosite(a[0], a[1], a[2], a[3], a[4]),
    "batch_geoip":      lambda a: cmd_batch_geoip(a[0], a[1], a[2], a[3], a[4], a[5]),
    "batch_manual_ip":  lambda a: cmd_batch_manual_ip(a[0], a[1], a[2], a[3]),
    "parse_clash":      lambda a: cmd_parse_clash(a[0], a[1], a[2]),
    "merge_dedup":      lambda a: cmd_merge_dedup(a[0], a[1], a[2], a[3]),
    "diff_new_entries":     lambda a: cmd_diff_new_entries(a[0], a[1], a[2], a[3]),
}

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <command> [args...]", file=sys.stderr)
        print(f"Commands: {', '.join(sorted(COMMANDS))}", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)

    COMMANDS[cmd](args)

if __name__ == "__main__":
    main()
