#!/usr/bin/env python3
"""
helpers.py（已增强）：
- 支持 --mihomo-bin 参数（也会读取 MIHOMO_BIN 环境变量）
- 用 subprocess 调用 mihomo convert-ruleset（行为 ipcidr/domain）
- 在无法找到 mihomo 时仍会产出 mrs_tasks.txt 供后续编译

用法示例：
python3 scripts/helpers.py \
  --geosite-dir geosite_txt --geoip-dir geoip_txt \
  --manual-site-dir Manual_site --manual-ip-dir Manual_ip \
  --tags-file tags.txt --out-dir geo --out-qx-dir QX \
  --compile-mrs true --mihomo-bin ./mihomo
"""
import argparse
import os
import glob
import shutil
import subprocess
from pathlib import Path

def read_lines(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f if l.strip()]

def write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")

def norm_geosite_line(line):
    line = line.strip()
    if not line:
        return None
    if line.startswith("keyword:"):
        return ("DOMAIN-KEYWORD", line[len("keyword:"):])
    if line.startswith("regexp:"):
        return ("DOMAIN-REGEX", line[len("regexp:"):])
    if line.startswith("full:"):
        return ("DOMAIN", line[len("full:"):])
    return ("DOMAIN-SUFFIX", line.lstrip("."))

def geosite_txt_tag_to_name(fname):
    return Path(fname).stem

def process_geosite(geosite_dir, manual_site_dir, tags, out_dir, out_qx_dir, mrs_tasks):
    files = sorted(glob.glob(os.path.join(geosite_dir, "*.txt")))
    tag_map = {}
    for f in files:
        tag = geosite_txt_tag_to_name(f)
        tag_map[tag] = f

    manual_files = sorted(glob.glob(os.path.join(manual_site_dir, "*.txt")))

    tags_to_process = tags if tags else sorted(set(list(tag_map.keys()) + [Path(p).stem for p in manual_files]))

    for tag in tags_to_process:
        lines = []
        if tag in tag_map:
            lines += read_lines(tag_map[tag])
        mfn = os.path.join(manual_site_dir, f"{tag}.txt")
        if os.path.isfile(mfn):
            lines += read_lines(mfn)

        if not lines:
            continue

        out_lines = []
        qx_lines = []
        seen = set()
        for l in lines:
            parsed = norm_geosite_line(l)
            if not parsed:
                continue
            t, v = parsed
            key = f"{t}:{v}"
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(f"{t},{v}")
            if t == "DOMAIN-SUFFIX":
                qx_lines.append(f"HOST-SUFFIX, {v}")
            elif t == "DOMAIN":
                qx_lines.append(f"HOST, {v}")
            elif t == "DOMAIN-KEYWORD":
                qx_lines.append(f"HOST-KEYWORD, {v}")

        out_list = os.path.join(out_dir, "geosite", f"{tag}.list")
        write_lines(out_list, out_lines)

        out_yaml = os.path.join(out_dir, "geosite", f"{tag}.yaml")
        yaml_lines = ["payload:"] + [f"  - {l}" for l in out_lines]
        write_lines(out_yaml, yaml_lines)

        qx_out = os.path.join(out_qx_dir, "geosite", f"{tag}.list")
        write_lines(qx_out, qx_lines)

        mrs_dst = os.path.join(out_dir, "geosite", f"{tag}.mrs")
        mrs_tasks.append(("domain", out_list, mrs_dst))

def process_geoip(geoip_dir, manual_ip_dir, tags, out_dir, out_qx_dir, mrs_tasks):
    files = sorted(glob.glob(os.path.join(geoip_dir, "*.txt")))
    tag_map = {}
    for f in files:
        tag = Path(f).stem
        tag_map[tag] = f

    manual_files = sorted(glob.glob(os.path.join(manual_ip_dir, "*.txt")))

    tags_to_process = tags if tags else sorted(set(list(tag_map.keys()) + [Path(p).stem for p in manual_files]))

    for tag in tags_to_process:
        lines = []
        if tag in tag_map:
            lines += read_lines(tag_map[tag])
        mfn = os.path.join(manual_ip_dir, f"{tag}.txt")
        if os.path.isfile(mfn):
            lines += read_lines(mfn)

        cidrs = [l for l in (x.strip() for x in lines) if l and not l.startswith("#")]
        if not cidrs:
            continue

        out_list = os.path.join(out_dir, "geoip", f"{tag}.list")
        write_lines(out_list, [f"IP-CIDR,{c}" for c in cidrs])

        out_yaml = os.path.join(out_dir, "geoip", f"{tag}.yaml")
        yaml_lines = ["payload:"] + [f"  - IP-CIDR,{c}" for c in cidrs]
        write_lines(out_yaml, yaml_lines)

        qx_out = os.path.join(out_qx_dir, "geoip", f"{tag}.list")
        write_lines(qx_out, cidrs)

        mrs_dst = os.path.join(out_dir, "geoip", f"{tag}.mrs")
        mrs_tasks.append(("ipcidr", out_list, mrs_dst))

def try_compile_mrs(mrs_tasks, mihomo_bin):
    failures = []
    if not mihomo_bin:
        print("[WARN] mihomo_bin not provided")
        return [dst for _, _, dst in mrs_tasks]
    if not os.path.isfile(mihomo_bin) or not os.access(mihomo_bin, os.X_OK):
        print(f"[WARN] mihomo not found or not executable at: {mihomo_bin}")
        return [dst for _, _, dst in mrs_tasks]

    for behavior, src, dst in mrs_tasks:
        tmp = dst + ".tmp"
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        cmd = [mihomo_bin, "convert-ruleset", behavior, "text", src, tmp]
        print(f"[RUN] {' '.join(cmd)}")
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
            if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                os.replace(tmp, dst)
                print(f"[OK] compiled {dst}")
            else:
                if os.path.isfile(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
                print(f"[ERR] failed compile {dst}, rc={r.returncode}")
                print(r.stderr or r.stdout)
                failures.append(dst)
        except Exception as e:
            print(f"[EXC] exception running mihomo: {e}")
            failures.append(dst)
    return failures

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geosite-dir", required=True)
    p.add_argument("--geoip-dir", required=True)
    p.add_argument("--manual-site-dir", required=True)
    p.add_argument("--manual-ip-dir", required=True)
    p.add_argument("--tags-file", default="")
    p.add_argument("--out-dir", default="geo")
    p.add_argument("--out-qx-dir", default="QX")
    p.add_argument("--compile-mrs", default="false")
    p.add_argument("--mihomo-bin", default="")
    args = p.parse_args()

    tags = []
    if args.tags_file and os.path.isfile(args.tags_file):
        tags = [l.strip() for l in read_lines(args.tags_file) if l.strip()]

    mrs_tasks = []
    for sub in ("geosite", "geoip"):
        d = os.path.join(args.out_dir, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
        qx_d = os.path.join(args.out_qx_dir, sub)
        os.makedirs(qx_d, exist_ok=True)

    process_geosite(args.geosite_dir, args.manual_site_dir, tags, args.out_dir, args.out_qx_dir, mrs_tasks)
    process_geoip(args.geoip_dir, args.manual_ip_dir, tags, args.out_dir, args.out_qx_dir, mrs_tasks)

    mrs_tasks_file = "mrs_tasks.txt"
    with open(mrs_tasks_file, "w", encoding="utf-8") as f:
        for b, s, d in mrs_tasks:
            f.write("\t".join([b, s, d]) + "\n")
    print(f"[INFO] wrote {mrs_tasks_file} ({len(mrs_tasks)} tasks)")

    if args.compile_mrs.lower() in ("true", "1", "yes"):
        mihomo_bin = args.mihomo_bin or os.environ.get("MIHOMO_BIN") or shutil.which("mihomo") or "./mihomo"
        fails = try_compile_mrs(mrs_tasks, mihomo_bin)
        if fails:
            print(f"[WARN] Some mrs failed: {len(fails)}; see above messages. Failures: {fails}")
            # 保留 mrs_tasks.txt 以便后续并行/重试
        else:
            print("[INFO] all mrs compiled ok")

if __name__ == "__main__":
    main()