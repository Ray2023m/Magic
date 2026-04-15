# 工作流使用说明：sync-loyalsoldier-geomrs.yml

本文说明工作流：
`Sync Loyalsoldier DAT -> Multi-format Rulesets`

## 最终产物
当前工作流只会生成并推送以下文件：

- `Rules/mihomo/geosite/*.mrs`
- `Rules/mihomo/geosite/*.list`
- `Rules/mihomo/geoip/*.mrs`
- `Rules/mihomo/geoip/*.list`

## 数据来源
- 基础数据：上游 DAT（由脚本下载）
- 手动扩展目录：
- `Manual_Site` 或 `Manual_site`
- `Manual_IP` 或 `Manual_ip`

## Tag 筛选规则
Tag = 文件名去掉后缀。

示例：
- `Rules/mihomo/geosite/Claude.mrs` -> tag 为 `Claude`
- `Rules/mihomo/geoip/Google.list` -> tag 为 `Google`

筛选顺序：
1. 先读取工作流中的预设白名单 `PRESET_INCLUDE_TAGS`。
2. 合并手动触发输入的 `include_tags`。
3. 自动把 `Manual_*` 目录中的 YAML 文件名加入包含集合。
4. 应用 `exclude_tags` 排除集合。
5. 如果包含集合非空，只保留包含集合中的 tag；再应用排除集合。

## 大小写敏感
Tag 匹配是大小写敏感的。

- `Claude` 和 `claude` 是两个不同 tag。

请确保输入大小写与实际文件名一致。

## 固定包含 Tag（推荐）
在工作流文件中修改：

- [sync-loyalsoldier-geomrs.yml](/Users/lazarus/文稿/GitHub/Magic/.github/workflows/sync-loyalsoldier-geomrs.yml:36)

把下面这行改成你的常用 tag（逗号分隔）：

```yaml
PRESET_INCLUDE_TAGS: "Claude,OpenAI,Google,Netflix,YouTube"
```

你可以直接放 10-20 个 tag。

## 手动运行时临时筛选
在 GitHub Actions 页面：

1. 打开工作流 `Sync Loyalsoldier DAT -> Multi-format Rulesets`
2. 点击 `Run workflow`
3. 可选填写：

- `include_tags`：本次临时追加包含（逗号分隔）
- `exclude_tags`：本次临时排除（逗号分隔）

示例：

- 仅保留两个 tag：
- `include_tags=Claude,OpenAI`
- `exclude_tags=`

- 保留预设/自动包含，但排除一个：
- `include_tags=`
- `exclude_tags=OpenAI`

## Manual_* 自动包含
以下目录中的 YAML 文件名会自动作为 tag 加入包含集合：

- `Manual_site/*.yaml`
- `Manual_Site/*.yaml`
- `Manual_ip/*.yaml`
- `Manual_IP/*.yaml`

示例：
- `Manual_Site/Claude.yaml` 会自动包含 tag `Claude`

## 触发方式
该工作流支持：

- 定时触发
- 手动触发（`workflow_dispatch`）
- 推送触发（workflow/脚本相关路径变更）

## 常见排查
1. 某个 tag 没有被推送。
优先检查大小写是否一致（如 `Claude` vs `claude`）。
2. 手动目录 tag 没生效。
检查文件是否为 `.yaml`，且目录在 `Manual_*` 变体内。
3. 有文件被意外删除。
检查 `exclude_tags` 是否包含该 tag，或该 tag 不在包含集合中。
