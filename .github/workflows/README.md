# 工作流使用说明：sync_meta-rules-dat_geomrs.yaml

本文说明工作流：
`Sync MetaCubeX DAT -> Custom Rulesets`

## 最终产物
当前工作流只会生成并推送以下文件：

- `Rules/mihomo/geosite/*.mrs`
- `Rules/mihomo/geosite/*.list`
- `Rules/mihomo/geoip/*.mrs`
- `Rules/mihomo/geoip/*.list`

## 数据来源
- 基础数据：上游 DAT（由脚本下载）
- 手动扩展目录：
- `Manual_Rules`

`Manual_Rules/<tag>.yaml` 和 `Manual_Rules/<tag>.list` 都支持，
并且同一个 tag 下两种文件会一起参与合并（读取顺序：`yaml -> list`）。

它们都支持在同一文件里混合域名规则和 IP 规则，
同时起到旧版 `Manual_Site/<tag>.yaml` + `Manual_IP/<tag>.yaml` 的作用。

## 扩展目录写法（.yaml / .list 通用）

### 1) 基础格式
- 每行一条规则：`规则类型,值[,附加参数...]`
- 兼容 YAML 列表前缀：`- DOMAIN,example.com`
- 以 `#` 开头或行内 `# 注释` 会被忽略

示例：

```yaml
- DOMAIN-SUFFIX,example.com
- DOMAIN,api.example.com
- DOMAIN-KEYWORD,google
- DOMAIN-REGEX,^.*\.example\.org$
- PROCESS-NAME,Telegram
- IP-CIDR,1.2.3.0/24
- IP-CIDR6,2408::/32
- IP-ASN,13335
```

### 2) add / remove 语义
- 默认是 `add`（新增）
- 当第 3 段及之后参数中出现以下动作关键字时，判定为 `remove`（删除）：
  - `remove`
  - `delete`
  - `exclude`

示例：

```yaml
DOMAIN,example.com
DOMAIN,example.com,remove
IP-CIDR,1.2.3.0/24,delete
DOMAIN-SUFFIX,ads.example,exclude
```

### 3) 其他参数不会触发删除
非动作关键字（如 `no-resolve`）不会改变操作语义，仍视为新增：

```yaml
IP-CIDR,8.8.8.0/24,no-resolve   # 仍是 add
```

## Tag 筛选规则
Tag = 文件名去掉后缀。

示例：
- `Rules/mihomo/geosite/Claude.mrs` -> tag 为 `Claude`
- `Rules/mihomo/geoip/Google.list` -> tag 为 `Google`

筛选顺序：
1. 先读取工作流中的预设白名单 `PRESET_INCLUDE_TAGS`。
2. 自动把手动规则目录中的 YAML/LIST 文件名加入包含集合（优先 `Manual_Rules`，兼容旧目录）。
3. 如果包含集合非空，只保留包含集合中的 tag。

## 大小写敏感
Tag 匹配是大小写敏感的。

- `Claude` 和 `claude` 是两个不同 tag。

请确保输入大小写与实际文件名一致。

## 固定包含 Tag（推荐）
在工作流文件中修改：

- [sync_meta-rules-dat_geomrs.yaml](/Users/lazarus/文稿/GitHub/Magic/.github/workflows/sync_meta-rules-dat_geomrs.yaml:36)

把下面这行改成你的常用 tag（逗号分隔）：

```yaml
PRESET_INCLUDE_TAGS: "Claude,OpenAI,Google,Netflix,YouTube"
```

你可以直接放 10-20 个 tag。

## 手动运行
在 GitHub Actions 页面：

1. 打开工作流 `Sync MetaCubeX DAT -> Custom Rulesets`
2. 点击 `Run workflow`

当前不提供手动输入 tag 参数，筛选仅由以下两部分决定：
- 工作流内置 `PRESET_INCLUDE_TAGS`
- 手动规则目录（`Manual_*`）自动识别到的 tag

## Manual_Rules 自动包含
以下目录中的 YAML / LIST 文件名会自动作为 tag 加入包含集合：

- `Manual_Rules/*.yaml`
- `Manual_Rules/*.list`
- `Manual_site/*.yaml`
- `Manual_site/*.list`
- `Manual_Site/*.yaml`
- `Manual_Site/*.list`
- `Manual_ip/*.yaml`
- `Manual_ip/*.list`
- `Manual_IP/*.yaml`
- `Manual_IP/*.list`

示例：
- `Manual_Rules/Claude.yaml` 会自动包含 tag `Claude`

## 触发方式
该工作流支持：

- 定时触发
- 手动触发（`workflow_dispatch`）
- 推送触发（workflow/脚本相关路径变更）

## 常见排查
1. 某个 tag 没有被推送。
优先检查大小写是否一致（如 `Claude` vs `claude`）。
2. 手动目录 tag 没生效。
检查文件是否为 `.yaml` 或 `.list`，且目录在 `Manual_Rules`（或兼容的 `Manual_*` 旧目录）内。
3. 有文件被意外删除。
检查该 tag 是否存在于 `PRESET_INCLUDE_TAGS`，或是否有对应的手动规则文件名（`Manual_*` 目录）。
