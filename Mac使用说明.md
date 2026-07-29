# Mac 上怎么演示人力看板（无 Power BI Desktop）

Power BI Desktop **仅支持 Windows**。Mac 网页版（app.powerbi.com）也**连不上**你电脑上的 `localhost` CSV。

下面按「面试能不能讲清楚」排序。

---

## 方案 A（推荐）：浏览器看板 · 本机即可演示

已做好交互看板，数据与 SQLite/CSV 同源。

1. 确保本地服务在跑（在项目根目录）：

```bash
cd /Users/kennywang/app/interview_prepare
python3 -m http.server 8787
```

2. 浏览器打开：

**http://127.0.0.1:8787/dashboard/**

3. 页面含：**总览 / 离职分析 / 薪酬成本 / 指标口径**，可切换月份。

面试时按文档 2 分钟话术讲：口径 → 发现 → 建议即可。  
诚实说法：「Mac 环境用 Web 看板复刻了三页 PBI 信息架构；上岗 Windows 环境可迁到 Power BI，模型与口径一致。」

---

## 方案 B：OneDrive + Power BI 网页版（真·Power BI）

适合你有 Microsoft 365 / 公司账号时。

1. 把 `data/csv/` 里需要的表上传到 **OneDrive**（建议单独文件夹 `HR_Demo`）。  
2. 打开 [Power BI Service](https://app.powerbi.com)  
3. **创建** → **粘贴或手动输入数据** / **从 OneDrive 获取**（入口随租户略有不同）  
4. 或：先把多张 CSV 合并进一个 **Excel 工作簿多 Sheet** 上传，再「导入 Excel」做报表（网页版对 Excel 更友好）。

限制：网页版建模/DAX 能力弱于 Desktop，复杂度量可能做不全；能出卡片+图即可。

---

## 方案 C：云电脑 / 虚拟机（完整 Desktop）

- 公司 Windows 远程桌面  
- Parallels / VMware + Windows  
- Azure / AWS Windows 云桌面  

装 Power BI Desktop，导入 `data/csv/` 本地文件或 Web 源。

---

## 本地文件地址（服务开启时）

| 用途 | URL |
|------|-----|
| 看板 | http://127.0.0.1:8787/dashboard/ |
| CSV 目录 | http://127.0.0.1:8787/data/csv/ |
| 旧 CSV 端口（若仍在跑） | http://127.0.0.1:8765/ |

CSV 单表示例：http://127.0.0.1:8787/data/csv/dim_org.csv

---

## 相关文件

| 路径 | 说明 |
|------|------|
| `dashboard/index.html` | 浏览器看板 |
| `dashboard/data.json` | 看板聚合数据 |
| `data/csv/*.csv` | 明细 CSV |
| `PowerBI看板搭建与核心指标说明.md` | 指标与（Windows）PBI 步骤 |
| `scripts/generate_hr_sqlite.py` | 重生库 |
| `scripts/export_csv.py` | 重导 CSV |

更新数据后刷新看板聚合：

```bash
python3 scripts/generate_hr_sqlite.py   # 可选：重造库
python3 scripts/export_csv.py           # 重导 CSV
# 再跑一次生成 data.json 的聚合脚本，或让我帮你重跑
```
