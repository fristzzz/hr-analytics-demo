# Power BI 看板搭建步骤与核心指标说明

> 配套数据：`data/hr_analytics_demo.db`（约 4000 人期末在职 · 12 个月模拟）  
> 再生数据：`python3 scripts/generate_hr_sqlite.py`  
> 用途：面试演示 / 自学建模 / 口径对齐练习（**非真实人事数据**）

---

## 目录

1. [交付物一览](#1-交付物一览)
2. [数据模型说明](#2-数据模型说明)
3. [Power BI 搭建步骤（从零到可演示）](#3-power-bi-搭建步骤从零到可演示)
4. [核心指标口径与 DAX](#4-核心指标口径与-dax)
5. [三页看板规格](#5-三页看板规格)
6. [演示话术（约 2 分钟）](#6-演示话术约-2-分钟)
7. [常见问题与口径陷阱](#7-常见问题与口径陷阱)
8. [附录：表字段字典](#8-附录表字段字典)

---

## 1. 交付物一览

| 路径 | 说明 |
|------|------|
| `data/hr_analytics_demo.db` | SQLite 星型模型数据 |
| `scripts/generate_hr_sqlite.py` | 可复现造数脚本（seed=42） |
| 本文档 | 搭建步骤 + 指标口径 + 推荐 DAX |

**规模（seed=42 时大致量级，以库内 `agg_monthly_kpi` 为准）：**

- 期末在职约 **4000** 人  
- 累计员工（含已离职）约 **4.5k–5.5k**  
- 月末快照约 **4.5 万+** 行  
- 人事事件、月度成本明细齐备  

**时间范围：** 2025-01 ~ 2025-12（可按脚本改 `START_MONTH`）

---

## 2. 数据模型说明

### 2.1 星型模型（推荐进 Power BI 的表）

```text
                    dim_date
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
 fact_snapshot    fact_event     fact_cost
        │              │              │
        ├──────── dim_employee ───────┤
        │              │              │
        ▼              ▼              ▼
     dim_org       dim_level    dim_leave_reason
        │
        ▼
  fact_hc_budget
```

| 表 | 角色 | 粒度 |
|----|------|------|
| `fact_snapshot` | 事实：月末在职快照 | 员工 × 月 |
| `fact_event` | 事实：入职/离职/调动/晋升/调薪 | 事件一行 |
| `fact_cost` | 事实：人工成本（脱敏月薪结构） | 员工 × 月 |
| `fact_hc_budget` | 事实：编制 | 部门 × 职级 × 月 |
| `dim_date` | 维度：日期 | 日 |
| `dim_org` | 维度：组织 | 部门 |
| `dim_level` | 维度：职级 | 职级 |
| `dim_employee` | 维度：员工主数据 | 员工 |
| `dim_leave_reason` | 维度：离职原因 | 原因码 |
| `agg_monthly_kpi` | **校验表**（可不进模型） | 月 |

### 2.2 关系设计（Power BI 模型视图）

| 从（多） | 到（一） | 字段 | 交叉筛选 |
|----------|----------|------|----------|
| `fact_snapshot` | `dim_employee` | `employee_id` | 单方向：维度 → 事实 |
| `fact_snapshot` | `dim_org` | `dept_id` | 单方向 |
| `fact_snapshot` | `dim_level` | `level_code` | 单方向 |
| `fact_snapshot` | `dim_date` | `snapshot_date` = `date_key` | 单方向 |
| `fact_event` | `dim_employee` | `employee_id` | 单方向 |
| `fact_event` | `dim_leave_reason` | `reason_code` | 单方向 |
| `fact_event` | `dim_date` | `event_date` = `date_key` | 单方向 |
| `fact_cost` | `dim_employee` | `employee_id` | 单方向 |
| `fact_cost` | `dim_org` | `dept_id` | 单方向 |
| `fact_cost` | `dim_level` | `level_code` | 单方向 |
| `fact_hc_budget` | `dim_org` | `dept_id` | 单方向 |
| `fact_hc_budget` | `dim_level` | `level_code` | 单方向 |

**注意：**

1. **慎用双向过滤**。部门切片同时筛离职与在职时，优先统一用 `dim_org` 连到各事实表，而不是靠双向。  
2. `fact_event` 的部门：入职看 `to_dept`，离职看 `from_dept`。若要做「按部门统计入离职」，可在 Power Query 增加计算列 `dept_id_for_analysis`，或做两张关系 + `USERELATIONSHIP`（进阶）。  
3. **月度筛选**建议统一用 `dim_date[month_key]` 或 `year_month_label`，不要混用各事实表裸字段做主切片器（可作备用）。

### 2.3 本库「月」字段约定

| 字段 | 示例 | 用途 |
|------|------|------|
| `month` / `snapshot_month` / `event_month` | `2025-03` | 月粒度汇总 |
| `snapshot_date` | `2025-03-31` | 连日期维度 |
| `event_date` | `2025-03-12` | 连日期维度 |
| `dim_date.month_index` | 1–12 | 演示期排序 |

---

## 3. Power BI 搭建步骤（从零到可演示）

### 步骤 0：环境

1. 安装 [Power BI Desktop](https://powerbi.microsoft.com/desktop/)（Windows；Mac 需虚拟机/云桌面/同事机）。  
2. 确认本机有 `data/hr_analytics_demo.db`。若无：

```bash
cd /path/to/interview_prepare
python3 scripts/generate_hr_sqlite.py
```

### 步骤 1：连接 SQLite

1. **获取数据** → **更多** → 搜索 **SQLite**（若列表无 SQLite）：  
   - 方式 A：安装官方/社区 SQLite 连接器；  
   - 方式 B（稳妥）：用 **ODBC** 或先导出 CSV（见步骤 1b）。  
2. 连接数据库文件：`hr_analytics_demo.db`。  
3. 勾选表：

```text
必选：dim_date, dim_org, dim_level, dim_employee, dim_leave_reason,
      fact_snapshot, fact_event, fact_cost, fact_hc_budget
可选：agg_monthly_kpi（仅用于核对数字）
不要：meta（或只作说明文本）
```

4. 点 **转换数据** 进入 Power Query（不要直接加载）。

#### 步骤 1b：无 SQLite 连接器时 — 导出 CSV

```bash
cd /path/to/interview_prepare
python3 - <<'PY'
import sqlite3, csv
from pathlib import Path
db = Path("data/hr_analytics_demo.db")
out = Path("data/csv")
out.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
)]
for t in tables:
    rows = conn.execute(f"SELECT * FROM {t}").fetchall()
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {t} LIMIT 0").description]
    with open(out / f"{t}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(t, len(rows))
conn.close()
print("→ data/csv/")
PY
```

Power BI：**获取数据 → 文件夹** 或分别 **文本/CSV** 导入 `data/csv/`。

### 步骤 2：Power Query 轻清洗

对每张表：

1. 检查类型：  
   - 日期列 → **日期**（`hire_date` / `leave_date` / `event_date` / `snapshot_date` / `date_key`）  
   - `month_key` 类 → **文本**  
   - 金额、人数 → **小数/整数**  
2. `dim_employee[leave_date]` 空值保留（在职）。  
3. 可选：给 `fact_event` 增加列（M 或自定义列）：

```text
部门分析键 =
if [event_type] = "hire" then [to_dept]
else if [event_type] = "leave" then [from_dept]
else if [to_dept] <> null then [to_dept]
else [from_dept]
```

4. **关闭并应用**。

### 步骤 3：模型视图建关系

按 [2.2](#22-关系设计power-bi-模型视图) 拖拽关系，全部 **一对多**、**单方向**。

建议：

- 将 `dim_date` 标记为 **日期表**（表工具 → 标记为日期表 → `date_key`）。  
- `dim_level[sort_order]`、`dim_org[sort_order]` 用于排序：列工具 → 按另一列排序。

### 步骤 4：新建度量值表

1. **输入数据** 建空表 `Metrics`（一列任意），或 **新建表**：`Metrics = {BLANK()}`。  
2. 在 `Metrics` 下创建下文 DAX（见第 4 章）。  
3. 隐藏度量宿主表中无用列。

### 步骤 5：做切片器面板（各页共用）

| 切片器 | 字段 |
|--------|------|
| 年月 | `dim_date[year_month_label]` 或 `month_key` |
| 部门 | `dim_org[dept_name]` |
| 部门组 | `dim_org[dept_group]` |
| 职级 | `dim_level[level_name]` |
| 性别 | `fact_snapshot[gender]` 或 `dim_employee[gender]` |

建议切片器默认选中 **最近一个月**（2025年12月），讲趋势时改成全年或 YTD。

### 步骤 6：按第 5 章搭三页视觉对象

页面命名建议：

1. `01_总览`  
2. `02_离职分析`  
3. `03_薪酬成本`  
4. （加分）`00_指标口径` — 文本框粘贴本文第 4 章摘要  

### 步骤 7：美化与面试演示设置

- 主题：简洁商务（深蓝 + 灰 + 一条强调色）。  
- KPI 卡：大数字 + 小字环比。  
- 关闭无关字段（在模型中 **隐藏** 技术键）。  
- 另存：`HR_Analytics_Demo.pbix`。  
- 练习：不看稿讲 2 分钟（第 6 章）。

### 步骤 8：数字核对（必做）

用 SQL 或 Excel 打开 `agg_monthly_kpi`，与 Power BI 卡片对照：

```sql
SELECT * FROM agg_monthly_kpi ORDER BY month;
```

| 核对项 | PBI 度量 | 校验表字段 |
|--------|----------|------------|
| 期末在职 | `[期末在职人数]` | `headcount_end` |
| 入职 | `[入职人数]` | `hires` |
| 离职 | `[离职人数]` | `leaves` |
| 离职率 | `[离职率]` | `turnover_rate` |
| 编制占用 | `[编制占用率]` | `occupancy_rate` |
| 总成本 | `[人工成本合计]` | `total_cost` |

误差应在 **四舍五入级**；若差一大截，优先查：筛选器是否含全月、日期表是否筛掉月末、离职是否重复计算。

---

## 4. 核心指标口径与 DAX

> **口径原则（面试必说）**  
> 先对齐统计时点（月末快照）、分子分母是否同源、是否含试用期/实习生；同比环比前确认历史口径一致。

符号：\(E^{begin}/E^{end}/E^{avg}\)、\(H\) 入职、\(L\) 离职、\(C\) 成本、\(HC^{budget}\) 编制。

### 4.1 人数与流动

#### （1）期末在职人数

**口径：** 选定月份（或日期上下文）下，`fact_snapshot` 中 `status = active` 的人数。本库每月仅有一条月末快照。

```dax
期末在职人数 =
CALCULATE (
    COUNTROWS ( fact_snapshot ),
    fact_snapshot[status] = "active"
)
```

#### （2）期初在职人数

**口径：** 上一自然月期末在职。演示期第一个月用「当月末 − 当月入职 + 当月离职」在校验表中近似。

```dax
期初在职人数 =
VAR CurMonth = SELECTEDVALUE ( dim_date[month_key] )
VAR PrevMonth =
    FORMAT (
        DATE (
            VALUE ( LEFT ( CurMonth, 4 ) ),
            VALUE ( RIGHT ( CurMonth, 2 ) ) - 1,
            1
        ),
        "YYYY-MM"
    )
-- 注意：1 月减 1 需更严谨写法，见下方推荐版
RETURN
    CALCULATE (
        [期末在职人数],
        REMOVEFILTERS ( dim_date ),
        fact_snapshot[snapshot_month] = PrevMonth
    )
```

**更稳妥（推荐）——用日期表平移：**

```dax
期初在职人数 =
CALCULATE (
    [期末在职人数],
    DATEADD ( dim_date[date_key], -1, MONTH )
)
```

> 因快照在月末，需保证日期筛选落到上月月末；若切片器是「月」，可改为按 `snapshot_month` 排序取上一月（见下）。

```dax
-- 按 month_key 排序的备选
期初在职人数_按月 =
VAR ThisIdx = SELECTEDVALUE ( dim_date[month_index] )
VAR PrevMonth =
    CALCULATE (
        MAX ( dim_date[month_key] ),
        REMOVEFILTERS ( dim_date ),
        dim_date[month_index] = ThisIdx - 1,
        dim_date[is_month_end] = 1
    )
RETURN
    CALCULATE (
        [期末在职人数],
        REMOVEFILTERS ( dim_date ),
        fact_snapshot[snapshot_month] = PrevMonth
    )
```

#### （3）平均在职人数

$$
E^{avg} = \frac{E^{begin} + E^{end}}{2}
$$

```dax
平均在职人数 =
DIVIDE ( [期初在职人数] + [期末在职人数], 2 )
```

#### （4）入职人数 / 离职人数

```dax
入职人数 =
CALCULATE (
    COUNTROWS ( fact_event ),
    fact_event[event_type] = "hire"
)

离职人数 =
CALCULATE (
    COUNTROWS ( fact_event ),
    fact_event[event_type] = "leave"
)

主动离职人数 =
CALCULATE (
    [离职人数],
    dim_leave_reason[leave_category] = "vol"
)

被动离职人数 =
CALCULATE (
    [离职人数],
    dim_leave_reason[leave_category] = "invol"
)
```

#### （5）离职率（推荐：平均在职口径）

$$
\text{Turnover} = \frac{L}{E^{avg}}
$$

```dax
离职率 =
DIVIDE ( [离职人数], [平均在职人数] )

离职率_显示 =
FORMAT ( [离职率], "0.00%" )

主动离职率 =
DIVIDE ( [主动离职人数], [平均在职人数] )
```

**面试一句话：**  
「我默认用平均在职作分母，避免分子用全月离职、分母用期末造成扩招月偏低、收缩月偏高；若公司历史报表用期初口径，我会先对齐再比。」

#### （6）净增员

```dax
净增员 = [入职人数] - [离职人数]
```

### 4.2 编制

本库 `fact_hc_budget` 已按 部门×职级×月 给出 `hc_budget` / `hc_actual`。

```dax
编制人数 =
SUM ( fact_hc_budget[hc_budget] )

编制实际在职 =
SUM ( fact_hc_budget[hc_actual] )
-- 应与同期「期末在职」接近；职级拆分场景用预算表更方便

编制占用率 =
DIVIDE ( [编制实际在职], [编制人数] )

空编率 =
1 - [编制占用率]

空编人数 =
[编制人数] - [编制实际在职]
```

$$
\text{Occupancy} = \frac{HC^{actual}}{HC^{budget}},\quad
\text{Vacancy} = 1 - \text{Occupancy}
$$

### 4.3 人工成本与人效（成本侧）

> 本演示库 **无营收表**，人效中的「人均营收」面试口述公式即可；看板做 **人均成本 / 成本结构 / 预算感（环比）**。

```dax
人工成本合计 =
SUM ( fact_cost[total_cost] )

固定工资合计 =
SUM ( fact_cost[base_salary] )

奖金合计 =
SUM ( fact_cost[bonus] )

加班费合计 =
SUM ( fact_cost[overtime_pay] )

企业社保合计 =
SUM ( fact_cost[social_security_co] )

公积金企业合计 =
SUM ( fact_cost[housing_fund_co] )

其他成本合计 =
SUM ( fact_cost[other_cost] )

人均人工成本 =
DIVIDE ( [人工成本合计], [平均在职人数] )

奖金占现金薪酬比 =
DIVIDE (
    [奖金合计],
    [固定工资合计] + [奖金合计] + [加班费合计]
)
```

**结构占比示例：**

```dax
社保公积金占成本比 =
DIVIDE (
    [企业社保合计] + [公积金企业合计],
    [人工成本合计]
)
```

### 4.4 环比 / 同比（时间智能）

前提：`dim_date` 已标记为日期表，且视觉对象上有连续日期/月上下文。

```dax
期末在职_上月 =
CALCULATE ( [期末在职人数], DATEADD ( dim_date[date_key], -1, MONTH ) )

期末在职_环比 =
DIVIDE ( [期末在职人数] - [期末在职_上月], [期末在职_上月] )

离职率_上月 =
CALCULATE ( [离职率], DATEADD ( dim_date[date_key], -1, MONTH ) )

离职率_环比点差 =
[离职率] - [离职率_上月]
-- 率的变化优先用「百分点」，面试时说明

人工成本_上月 =
CALCULATE ( [人工成本合计], DATEADD ( dim_date[date_key], -1, MONTH ) )

人工成本_环比 =
DIVIDE ( [人工成本合计] - [人工成本_上月], [人工成本_上月] )
```

演示数据仅 12 个月，**同比**可写但去年为空：

```dax
期末在职_去年同期 =
CALCULATE ( [期末在职人数], SAMEPERIODLASTYEAR ( dim_date[date_key] ) )
```

### 4.5 结构与质量类（离职页）

```dax
关键人才离职人数 =
CALCULATE (
    [离职人数],
    dim_employee[is_key_talent] = 1
)

试用期离职人数 =
CALCULATE (
    COUNTROWS ( fact_event ),
    fact_event[event_type] = "leave",
    fact_event[reason_code] = "R06"
)
-- 更严谨可用：离职日 <= probation_end（需关系 + 筛选器）

离职原因占比 =
DIVIDE (
    COUNTROWS ( fact_event ),
    CALCULATE (
        COUNTROWS ( fact_event ),
        REMOVEFILTERS ( dim_leave_reason ),
        fact_event[event_type] = "leave"
    )
)
```

### 4.6 调薪相关（加分）

```dax
调薪人次 =
CALCULATE (
    COUNTROWS ( fact_event ),
    fact_event[event_type] = "salary_adjust"
)

晋升人次 =
CALCULATE (
    COUNTROWS ( fact_event ),
    fact_event[event_type] = "promotion"
)
```

### 4.7 指标速查表

| 指标 | 公式 | 本库数据源 |
|------|------|------------|
| 期末在职 | 月末快照计数 | `fact_snapshot` |
| 平均在职 | \((E^{begin}+E^{end})/2\) | 快照推算 |
| 离职率 | \(L / E^{avg}\) | `fact_event` + 快照 |
| 主动/被动离职率 | \(L^{vol/invol}/E^{avg}\) | + `dim_leave_reason` |
| 编制占用率 | \(HC^{actual}/HC^{budget}\) | `fact_hc_budget` |
| 空编率 | \(1-\)占用率 | 同上 |
| 人均人工成本 | \(C / E^{avg}\) | `fact_cost` |
| 净增员 | \(H-L\) | `fact_event` |

---

## 5. 三页看板规格

### 5.1 页面一：总览 Dashboard

**决策问题：** 组织人效健康吗？人是进是出？编占用得怎样？成本是否在抬升？

| 区域 | 视觉对象 | 字段/度量 |
|------|----------|-----------|
| 顶栏 KPI | 卡片 × 6 | 期末在职、净增员、离职率、编制占用率、人工成本合计、人均人工成本 |
| 次行 | 卡片小字 | 各 KPI 环比 |
| 左 | 折线+柱 | 月：在职（线）+ 入职/离职（柱） |
| 中 | 折线 | 月离职率趋势 |
| 右 | 条形 | 部门组或部门：期末在职 |
| 底 | 矩阵 | 部门 × 在职 / 离职率 / 占用率 / 人均成本 |

**切片器：** 年月（可多选看区间）、部门组。

### 5.2 页面二：离职分析

**决策问题：** 谁在走？为什么走？是结构问题还是个案？

| 区域 | 视觉对象 | 字段/度量 |
|------|----------|-----------|
| KPI | 卡片 | 离职人数、主动离职率、被动离职率、关键人才离职 |
| 趋势 | 折线 | 月 × 离职率 / 主动离职率 |
| 对比 | 条形 | 部门 × 离职率（注意小分母标注） |
| 结构 | 堆叠条/柱 | 司龄段 `tenure_band`、职级、是否试用 |
| 原因 | 环图/条形 | `dim_leave_reason[reason_name]` × 离职人数 |
| 明细 | 表（脱敏） | 员工号、部门、职级、离职日、原因（**勿放真实姓名薪资**） |

**分析路径（口述）：** 口径 → 部门/职级/司龄 → 是否试用期与入职批次 → 原因标签 → 结构性 vs 个案 → 建议。

### 5.3 页面三：薪酬 / 成本

**决策问题：** 钱花在哪？结构是否健康？哪有异常抬升？

| 区域 | 视觉对象 | 字段/度量 |
|------|----------|-----------|
| KPI | 卡片 | 人工成本合计、人均成本、奖金合计、社保公积金合计 |
| 趋势 | 折线 | 月 × 总成本、人均成本（1 月含年终奖会跳升——**演示时主动解释**） |
| 构成 | 堆叠柱 | 月 × base/bonus/ot/ss/hf/other |
| 对比 | 条形 | 部门 × 人均成本 |
| 职级 | 矩阵 | 职级 × 人数、平均基本工资、总成本 |
| 动作 | 卡片 | 调薪人次、晋升人次 |

**合规表述：** 演示仅用 `name_mask` 与聚合薪资；真实环境薪酬明细需 RLS + 最小权限。

### 5.4 （可选）口径说明页

文本框列出：

- 离职率 = 当期离职 ÷ 平均在职  
- 在职 = 月末快照  
- 成本含企业社保公积金与奖金分摊  
- 数据为模拟、seed=42  

---

## 6. 演示话术（约 2 分钟）

> 我用模拟的 4000 人、12 个月人事与成本数据，按星型模型搭了三页看板。  
>  
> **建模上**：月末在职进快照事实表，入离职进事件事实表，成本与编制分开；维度是日期、组织、职级、员工和离职原因。  
>  
> **离职率**我用平均在职作分母：`DIVIDE(离职人数, 平均在职)`，避免和期末人数错配。  
>  
> **总览页**看在职、净流入、离职率、编制占用和人均成本，先回答管理层「人多了还是少了、编满不满、钱有没有顶穿」。  
>  
> **离职页**按部门、司龄、原因下钻；主动和被动分开，试用期与关键人才单独看。  
>  
> **成本页**看结构（工资/奖金/社保公积金）和部门人均成本；1 月若有年终奖，我会标注季节性，而不是直接说成本失控。  
>  
> 上岗后第一件事不是急着画图，而是和 HR、财务对齐口径与数据源，再固化成可复用的看板与月报节奏。

---

## 7. 常见问题与口径陷阱

| 问题 | 处理 |
|------|------|
| 离职率与校验表不一致 | 查是否用了平均在职；切片器是否只筛了部分部门却分母未同步 |
| 入职+期初−离职 ≠ 期末 | 存在调动当月、或期初定义不同；本库以快照为准对账事件 |
| 1 月成本暴涨 | 脚本把年终奖计入 1 月 `bonus`，演示时说明 |
| 小部门离职率 50% | 分母过小；图表加「离职人数」辅助，或设最小样本 |
| 多事实表日期冲突 | 各页明确主日期关系；或拆「在职分析」「事件分析」书签 |
| 薪酬明细权限 | 面试强调 RLS、聚合展示、脱敏字段 |

---

## 8. 附录：表字段字典

### 8.1 `dim_employee`

| 字段 | 说明 |
|------|------|
| employee_id | 员工主键 E00001… |
| name_mask | 脱敏姓名 |
| gender | 男/女/未披露 |
| birth_year | 出生年（用于年龄段） |
| hire_date / leave_date | 入职/离职日 |
| leave_type | vol / invol / other |
| leave_reason_code | 关联 dim_leave_reason |
| current_dept_id / current_level_code | 期末（或最后快照）组织职级 |
| is_key_talent | 1=关键人才标签 |
| probation_end | 试用结束日 |
| status_end | active / left |

### 8.2 `fact_snapshot`

月末一行一员工：部门、职级、年龄段、司龄段、是否试用、当月基本工资等。

### 8.3 `fact_event`

| event_type | 含义 |
|------------|------|
| hire | 入职 |
| leave | 离职 |
| transfer | 部门调动 |
| promotion | 晋升 |
| salary_adjust | 调薪 |

### 8.4 `fact_cost`

`total_cost = base_salary + bonus + overtime_pay + social_security_co + housing_fund_co + other_cost`  
（企业承担口径的简化模型。）

### 8.5 `fact_hc_budget`

`hc_budget` ≥ `hc_actual`，空编率一般为数个点到十余个点，研发/销售前半年空编略高。

### 8.6 离职原因

| 编码 | 名称 | 类别 |
|------|------|------|
| R01 | 个人发展 | vol |
| R02 | 薪酬福利 | vol |
| R03 | 工作强度/平衡 | vol |
| R04 | 家庭原因 | vol |
| R05 | 管理/团队氛围 | vol |
| R06 | 试用不合格 | invol |
| R07 | 绩效淘汰 | invol |
| R08 | 组织调整/裁员 | invol |
| R09 | 合同到期不续 | invol |
| R10 | 其他 | other |

---

## 9. 相关文件

| 文件 | 说明 |
|------|------|
| `人力资源专员-薪酬数据分析-面试准备.md` | 完整面试知识与公式 |
| `data/hr_analytics_demo.db` | 演示数据库 |
| `scripts/generate_hr_sqlite.py` | 造数脚本 |

---

*指标口径以目标公司制度为准；本文与模拟库仅用于面试准备与学习。*
