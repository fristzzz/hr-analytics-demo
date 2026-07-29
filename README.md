# 人力数据分析演示数据（面试用）

模拟约 4000 人、12 个月人事/成本数据，供 **Power BI 网页版** 通过 GitHub Raw 链接取数，或本地练习。

> 数据为 **完全模拟**，不含真实个人信息。

## Power BI 网页版：用 Web 连接 CSV

仓库公开后，在 Power BI Service：**获取数据 → Web**，粘贴下方 Raw 地址（每个表一次）。

将 `fristzzz` / 仓库名 换成你的实际地址；默认分支为 `main` 时格式为：

```text
https://raw.githubusercontent.com/<用户名>/<仓库名>/main/data/csv/<文件名>.csv
```

### 推荐导入清单

| 表 | 用途 |
|----|------|
| dim_date.csv | 日期维度（可选） |
| dim_org.csv | 部门 |
| dim_level.csv | 职级 |
| dim_employee.csv | 员工 |
| dim_leave_reason.csv | 离职原因 |
| fact_snapshot.csv | 月末在职快照 |
| fact_event.csv | 人事事件 |
| fact_cost.csv | 月度成本 |
| fact_hc_budget.csv | 编制 |
| agg_monthly_kpi.csv | 仅校验，可不进模型 |

### 建模型要点

1. 新建 `dim_month`：对 `fact_cost[month]` 去重（每月一行）  
2. 所有事实表的「月」字段 → `dim_month`  
3. `fact_event[event_date]` / `fact_snapshot[snapshot_date]` → `dim_date[date_key]`（可选）  
4. 组织/职级/员工/原因按星型连接  

详见：`PowerBI看板搭建与核心指标说明.md`

## 本地浏览器看板（Mac 友好）

```bash
cd /path/to/this/repo
python3 -m http.server 8787
# 打开 http://127.0.0.1:8787/dashboard/
```

## 重新生成数据

```bash
python3 scripts/generate_hr_sqlite.py
python3 scripts/export_csv.py
# 然后重新生成 dashboard/data.json（可选）
git add data/csv && git commit -m "refresh demo data" && git push
```

## 说明文档

| 文件 | 内容 |
|------|------|
| 招银金服-人力数据分析岗-分析报告规范.md | 报告体系 |
| 人力数据分析-PowerBI与看板概念速查.md | 概念 |
| PowerBI看板搭建与核心指标说明.md | 建模与 DAX |
| Mac使用说明.md | Mac 演示路径 |
