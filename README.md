# ⚓️ Magic - OpenClash 覆写与规则合集

适用于 Homelab / 家庭网络场景的 OpenClash 配置集合，目标是**快速部署、易于维护、可按需扩展**。

> 本项目聚焦作者个人高频使用场景。维护自己可控,快速,稳定规则源.项目来源 github 各位大神智慧!

---

## ✨ 项目特性

- 提供可直接使用的 OpenClash 覆写配置（`SmartFlux / SmartFluxPro`）
- 提供较完整的应用分流策略（AI、社交、流媒体、游戏、常见服务）
- 内置图标资源（策略组图标、国家/地区图标）
- 提供 `Manual_Rules` 手动规则扩展目录
- 提供规则同步脚本，可将上游规则转换为 `mihomo` 使用的 `.mrs/.list`

---

## 📁 目录结构（核心）

```text
Magic
├── Openclash/
│   ├── Overwrite/                    # .conf 覆写模板
│   │                                 
│   └── Yaml/                         # 主配置 YAML（如 SmartFluxPro.yaml）
├── Rules/
│   ├── mihomo/geosite/               # 域名规则（.mrs/.list）
│   └── mihomo/geoip/                 # IP 规则（.mrs/.list）
├── Manual_Rules/                     # 手动补充规则（yaml）
├── icon/                             # 图标资源
└── scripts/
    └── sync_loy_geo_mrs.sh           # 规则同步与编译脚本
```

---

## 🚀 快速使用

### 1) OpenClash 覆写链接（推荐）

将以下地址填入 OpenClash 覆写模块（或在线覆写地址）：
```bash
https://gcore.jsdelivr.net/gh/Ray2023m/Magic@main/Openclash/Overwrite/SmartFluxPro.conf
```

```bash
https://gcore.jsdelivr.net/gh/Ray2023m/Magic@main/Openclash/Overwrite/SmartFlux.conf
```
### 2) 订阅变量说明

`SmartFluxPro.conf` 通过环境变量注入订阅地址，默认使用 `KEY1 ~ KEY6`：

- `KEY1` → `Sub1-猫猫`
- `KEY2` → `Sub2-糖果`
- `KEY3` → `Sub3-69云`
- `KEY4` → `Sub4-魔戒`
- `KEY5` → `Sub5-RE`
- `KEY6` → `Sub6-Oracle`

你可以只填常用的 KEY，其余留空后在 YAML 中手动删除对应 provider。

---

## ⚙️ 配置文件说明

### `Openclash/Overwrite/overwrite/SmartFluxPro.conf`

- 控制 OpenClash 运行参数（DNS、IPv6、TUN、规则模式等）
- 自动下载并指定 `SmartFluxPro.yaml` 为默认配置
- 通过 Ruby 映射函数将 `KEY1~KEY6` 注入 YAML 订阅地址

---

## 🧩 手动规则扩展

你可以在 `Manual_Rules/` 中新增或维护规则文件（如 `custom.yaml`、`github.yaml` 等），用于补充项目默认规则。


---

## 🔄 规则同步脚本（进阶）

脚本：`scripts/sync_loy_geo_mrs.sh`

用途：
- 从 `MetaCubeX/meta-rules-dat` 下载 `geoip.dat / geosite.dat`
- 解包并转换输出到 `Rules/mihomo/geosite` 与 `Rules/mihomo/geoip`
- 融合 `Manual_Rules` 中的规则
- 并行编译 `.mrs`

运行前请确保系统已安装：

- `v2dat`
- `python3`
- 可执行的 `mihomo` 二进制（默认 `./mihomo`）

执行示例：

```bash
bash scripts/sync_loy_geo_mrs.sh
```


---

## 🙌 致谢,排名不分先后!

- [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)
- [vernesong/mihomo](https://github.com/vernesong/mihomo)
- [bgpeer/rules](https://github.com/bgpeer/rules) 获取规则脚本来源,Codex 修改而来!🙏
- [Rabbit-Spec/Surge](https://github.com/Rabbit-Spec/Surge) Surge 规则获取来源!感谢!
