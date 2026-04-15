#!/usr/bin/env bash
# sync_loy_geo_mrs.sh
# 从 Loyalsoldier 下载 geoip/geosite .dat，拆分并输出四种格式：
#   Rules/mihomo/geosite/ -> .mrs  .yaml  .list  .json
#   Rules/mihomo/geoip/   -> .mrs  .yaml  .list  .json
#
# 并将 clash/<n>.yaml 中的规则融合进同名输出（宽松去重）：
#   支持规则类型：DOMAIN-SUFFIX / DOMAIN / DOMAIN-KEYWORD / DOMAIN-REGEX
#                IP-CIDR / IP-CIDR6
#                PROCESS-NAME / PROCESS-NAME-REGEX / IP-ASN
#   融合策略：
#     yaml / list           -> 保留所有规则类型
#     mrs                   -> 仅 domain/suffix 和 IP-CIDR/IP-CIDR6，其余跳过
#     json                  -> 跳过 PROCESS-NAME / PROCESS-NAME-REGEX / IP-ASN
#   若 clash/<n>.yaml 存在但 geo 无同名文件，则纯从 clash 数据建档。
#
# 性能优化：
#   - Python 批处理：一次 python3 调用处理所有 tag 的全部文本格式（消除 6000+ 次进程启动）
#   - 并行编译：mrs 用 xargs -P 多核并行
set -euo pipefail

GEOIP_URL='https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geoip.dat'
GEOSITE_URL='https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geosite.dat'

OUT_GEOSITE='Rules/mihomo/geosite'
OUT_GEOIP='Rules/mihomo/geoip'
LEGACY_GEO_ROOT='geo'
LEGACY_MIHOMO_ROOT='mihomo'

CLASH_DIR="${CLASH_DIR:-Manual_Site}"
CLASH_IP_DIR="${CLASH_IP_DIR:-Manual_IP}"

MIHOMO_BIN="${MIHOMO_BIN:-./mihomo}"

PARALLEL="${PARALLEL:-$(nproc 2>/dev/null || echo 2)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HELPERS="${SCRIPT_DIR}/helpers.py"
cd "$REPO_ROOT"

echo "[INFO] repo root: $(pwd)"
echo "[INFO] parallel jobs: $PARALLEL"

# 输出目录名冲突保护（例如仓库里已有同名文件 mihomo）
if [ -f "$(dirname "$OUT_GEOSITE")" ]; then
  echo "ERROR: output root '$(dirname "$OUT_GEOSITE")' exists as a file, cannot create directory."
  echo "       Please move/rename that file (or change MIHOMO_BIN path in workflow)."
  exit 1
fi

# ── 前置检查 ──────────────────────────────────────────────────────────────────
command -v v2dat       >/dev/null 2>&1 || { echo "ERROR: v2dat not found";      exit 1; }
[ -x "$MIHOMO_BIN"  ]                  || { echo "ERROR: mihomo not executable"; exit 1; }
command -v python3     >/dev/null 2>&1 || { echo "ERROR: python3 not found";     exit 1; }
[ -f "$HELPERS"      ]                 || { echo "ERROR: helpers.py not found at $HELPERS"; exit 1; }

echo "[INFO] mihomo version:"; "$MIHOMO_BIN" -v || true

# ── 工作目录 ──────────────────────────────────────────────────────────────────
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

MRS_TASKS="${WORKDIR}/mrs_tasks.txt"
: > "$MRS_TASKS"

# ══════════════════════════════════════════════════════════════════════════════
# 1. 下载
# ══════════════════════════════════════════════════════════════════════════════
echo "[1/7] Download dat files..."
curl -fsSL --retry 3 --retry-delay 2 "$GEOIP_URL"   -o "$WORKDIR/geoip.dat"
curl -fsSL --retry 3 --retry-delay 2 "$GEOSITE_URL" -o "$WORKDIR/geosite.dat"

# ══════════════════════════════════════════════════════════════════════════════
# 2. 解包
# ══════════════════════════════════════════════════════════════════════════════
echo "[2/7] Unpack dat -> txt..."
mkdir -p "$WORKDIR/geoip_txt" "$WORKDIR/geosite_txt"
v2dat unpack geoip   -o "$WORKDIR/geoip_txt"   "$WORKDIR/geoip.dat"
v2dat unpack geosite -o "$WORKDIR/geosite_txt" "$WORKDIR/geosite.dat"

GEOIP_TXT_COUNT="$(find   "$WORKDIR/geoip_txt"   -type f -name '*.txt' | wc -l | tr -d ' ')"
GEOSITE_TXT_COUNT="$(find "$WORKDIR/geosite_txt" -type f -name '*.txt' | wc -l | tr -d ' ')"
echo "[DEBUG] geoip txt=$GEOIP_TXT_COUNT  geosite txt=$GEOSITE_TXT_COUNT"

if [ "$GEOIP_TXT_COUNT" -eq 0 ] || [ "$GEOSITE_TXT_COUNT" -eq 0 ]; then
  echo "ERROR: unpack produced 0 txt files"; exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
# 3. 清空旧输出（增删同步）
# ══════════════════════════════════════════════════════════════════════════════
echo "[3/7] Clean output dirs (full sync)..."
rm -rf "$OUT_GEOSITE" "$OUT_GEOIP"
# 迁移：清理旧目录，避免 geo/ 与 mihomo/ 并存
rm -rf "$LEGACY_GEO_ROOT"
rm -rf "$LEGACY_MIHOMO_ROOT"
mkdir -p "$OUT_GEOSITE" "$OUT_GEOIP"

# ══════════════════════════════════════════════════════════════════════════════
# 4. Python 批处理 geosite（一次调用处理所有 tag，输出 yaml/list/json）
# ══════════════════════════════════════════════════════════════════════════════
echo "[4/7] Batch process geosite (Python)..."
python3 "$HELPERS" batch_geosite \
  "$WORKDIR/geosite_txt" \
  "$CLASH_DIR" \
  "$OUT_GEOSITE" \
  "$MRS_TASKS" \
  "$WORKDIR"

# ══════════════════════════════════════════════════════════════════════════════
# 5. Python 批处理 geoip（一次调用处理所有 tag）
# ══════════════════════════════════════════════════════════════════════════════
echo "[5/7] Batch process geoip (Python)..."
python3 "$HELPERS" batch_geoip \
  "$WORKDIR/geoip_txt" \
  "$CLASH_DIR" \
  "$WORKDIR/clash_ip" \
  "$OUT_GEOIP" \
  "$MRS_TASKS" \
  "$WORKDIR"

# ── Python 批处理 Manual_IP/ ─────────────────────────────────────────────────
echo "[5b/7] Batch process Manual_IP (Python)..."
python3 "$HELPERS" batch_manual_ip \
  "$CLASH_IP_DIR" \
  "$OUT_GEOIP" \
  "$MRS_TASKS" \
  "$WORKDIR"

# ══════════════════════════════════════════════════════════════════════════════
# 6. 并行编译 mrs
# ══════════════════════════════════════════════════════════════════════════════
echo "[6/7] Parallel compile mrs (jobs=$PARALLEL)..."

# mrs 去重（同一 dst 只保留最后一条）
MRS_DEDUP="${WORKDIR}/mrs_tasks_dedup.txt"
if [[ -s "$MRS_TASKS" ]]; then
  awk -F'\t' '{ last[$3] = $0 } END { for (k in last) print last[k] }' \
    "$MRS_TASKS" > "$MRS_DEDUP"
else
  : > "$MRS_DEDUP"
fi

mrs_total="$(wc -l < "$MRS_DEDUP" | tr -d ' ')"
echo "[INFO] mrs tasks: $mrs_total"

# ── 并行编译 mrs ─────────────────────────────────────────────────────────────
mrs_fail_log="${WORKDIR}/mrs_failures.log"
: > "$mrs_fail_log"

if [[ "$mrs_total" -gt 0 ]]; then
  export MIHOMO_BIN mrs_fail_log
  compile_one_mrs() {
    local line="$1"
    local behavior src dst tmp
    behavior="$(printf '%s' "$line" | cut -f1)"
    src="$(printf '%s' "$line" | cut -f2)"
    dst="$(printf '%s' "$line" | cut -f3)"
    tmp="${dst}.tmp"
    rm -f "$tmp" 2>/dev/null || true
    if "$MIHOMO_BIN" convert-ruleset "$behavior" text "$src" "$tmp" 2>/dev/null \
       && [ -s "$tmp" ]; then
      mv -f "$tmp" "$dst"
    else
      rm -f "$tmp" 2>/dev/null || true
      echo "FAIL: $dst" >> "$mrs_fail_log"
    fi
  }
  export -f compile_one_mrs
  cat "$MRS_DEDUP" | xargs -P "$PARALLEL" -I{} bash -c 'compile_one_mrs "$@"' _ {}
  echo "[INFO] mrs compile done"
fi

mrs_fail="$(grep -c "^FAIL:" "$mrs_fail_log" 2>/dev/null || echo 0)"

# ══════════════════════════════════════════════════════════════════════════════
# 7. 统计
# ══════════════════════════════════════════════════════════════════════════════
echo "[7/7] Final counts:"
echo "  Rules/mihomo/geosite mrs  : $(find "$OUT_GEOSITE"    -name '*.mrs'  | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geosite yaml : $(find "$OUT_GEOSITE"    -name '*.yaml' | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geosite list : $(find "$OUT_GEOSITE"    -name '*.list' | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geosite json : $(find "$OUT_GEOSITE"    -name '*.json' | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geoip   mrs  : $(find "$OUT_GEOIP"      -name '*.mrs'  | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geoip   yaml : $(find "$OUT_GEOIP"      -name '*.yaml' | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geoip   list : $(find "$OUT_GEOIP"      -name '*.list' | wc -l | tr -d ' ')"
echo "  Rules/mihomo/geoip   json : $(find "$OUT_GEOIP"      -name '*.json' | wc -l | tr -d ' ')"

if [[ $mrs_fail -gt 0 ]]; then
  echo "[WARN] compilation failures: mrs=$mrs_fail"
  [[ $mrs_fail -gt 0 ]] && cat "$mrs_fail_log"
fi

echo "Done."
