#!/usr/bin/env python3
"""
生成人力资源（薪酬/数据分析）面试演示用 SQLite 数据库。

目标规模：约 4000 名在职峰值 + 12 个月滚动数据
星型模型表：dim_date / dim_org / dim_level / dim_employee /
            fact_snapshot / fact_event / fact_cost / fact_hc_budget /
            dim_leave_reason（辅助）
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SEED = 42
START_MONTH = date(2025, 1, 1)
N_MONTHS = 12
TARGET_ACTIVE_END = 4000  # 第 12 月末目标在职人数

DEPTS = [
    ("D01", "研发中心", "P"),
    ("D02", "产品中心", "P"),
    ("D03", "销售部", "S"),
    ("D04", "市场部", "S"),
    ("D05", "运营部", "S"),
    ("D06", "客户成功", "S"),
    ("D07", "人力资源", "F"),
    ("D08", "财务部", "F"),
    ("D09", "行政部", "F"),
    ("D10", "法务合规", "F"),
    ("D11", "供应链", "O"),
    ("D12", "质量部", "O"),
]

# 部门编制权重（相对）
DEPT_WEIGHT = {
    "D01": 28, "D02": 10, "D03": 14, "D04": 6, "D05": 8, "D06": 7,
    "D07": 4, "D08": 4, "D09": 3, "D10": 2, "D11": 8, "D12": 6,
}

LEVELS = [
    # code, name, band, base_mid (元/月), 权重
    ("L1", "专员", "IC", 8000, 28),
    ("L2", "高级专员", "IC", 11000, 22),
    ("L3", "专家/主管", "IC", 16000, 18),
    ("L4", "资深/经理", "M", 22000, 14),
    ("L5", "高级经理", "M", 30000, 10),
    ("L6", "总监", "M", 42000, 6),
    ("L7", "VP/总经理", "E", 65000, 2),
]

GENDERS = [("男", 0.52), ("女", 0.47), ("未披露", 0.01)]

LEAVE_REASONS = [
    ("R01", "个人发展", "vol", 0.28),
    ("R02", "薪酬福利", "vol", 0.18),
    ("R03", "工作强度/平衡", "vol", 0.12),
    ("R04", "家庭原因", "vol", 0.10),
    ("R05", "管理/团队氛围", "vol", 0.08),
    ("R06", "试用不合格", "invol", 0.08),
    ("R07", "绩效淘汰", "invol", 0.07),
    ("R08", "组织调整/裁员", "invol", 0.05),
    ("R09", "合同到期不续", "invol", 0.02),
    ("R10", "其他", "other", 0.02),
]

SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻")
GIVEN = list("伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀英华慧巧美娜静淑惠珠翠雅芝玉萍红娥玲芬芳燕彩春菊兰凤洁梅琳素云莲真环雪荣爱妹霞香月莺媛艳瑞凡佳嘉怡欣")


def weighted_choice(items_weights, rng: random.Random):
    items, weights = zip(*items_weights)
    return rng.choices(items, weights=weights, k=1)[0]


def month_starts(start: date, n: int) -> list[date]:
    out = []
    y, m = start.year, start.month
    for _ in range(n):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def add_months(d: date, k: int) -> date:
    y = d.year + (d.month - 1 + k) // 12
    m = (d.month - 1 + k) % 12 + 1
    return date(y, m, 1)


def days_in_month(d: date) -> int:
    return month_end(d).day


def random_day_in_month(ms: date, rng: random.Random) -> date:
    return date(ms.year, ms.month, rng.randint(1, days_in_month(ms)))


def age_band_from_age(age: int) -> str:
    if age < 25:
        return "25岁以下"
    if age < 30:
        return "25-29"
    if age < 35:
        return "30-34"
    if age < 40:
        return "35-39"
    if age < 45:
        return "40-44"
    return "45岁及以上"


def tenure_band_from_days(days: int) -> str:
    if days < 90:
        return "0-3月"
    if days < 365:
        return "3-12月"
    if days < 365 * 3:
        return "1-3年"
    if days < 365 * 5:
        return "3-5年"
    return "5年+"


def mask_name(rng: random.Random) -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN) + ("*" if rng.random() < 0.55 else rng.choice(GIVEN))


def level_mid(code: str) -> int:
    for c, _, _, mid, _ in LEVELS:
        if c == code:
            return mid
    return 12000


@dataclass
class Employee:
    employee_id: str
    name_mask: str
    gender: str
    birth_year: int
    hire_date: date
    leave_date: date | None
    leave_type: str | None  # vol / invol / other
    leave_reason: str | None
    dept_id: str
    level_code: str
    base_salary: float
    is_key_talent: int
    probation_end: date


def build_db(db_path: Path, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    months = month_starts(START_MONTH, N_MONTHS)
    end_month = months[-1]
    end_of_period = month_end(end_month)

    # ---------- 初始在职：约 3600，再通过 12 个月招聘净增到 ~4000 ----------
    n_initial = 3600
    # 历史入职分布：过去 0–8 年
    employees: list[Employee] = []
    emp_seq = 1

    def new_emp_id() -> str:
        nonlocal emp_seq
        eid = f"E{emp_seq:05d}"
        emp_seq += 1
        return eid

    def pick_dept() -> str:
        return weighted_choice([(d[0], DEPT_WEIGHT[d[0]]) for d in DEPTS], rng)

    def pick_level() -> str:
        return weighted_choice([(c, w) for c, _, _, _, w in LEVELS], rng)

    def make_employee(hire: date, dept: str | None = None, level: str | None = None) -> Employee:
        gender = weighted_choice(GENDERS, rng)
        age0 = int(rng.gauss(31, 6))
        age0 = max(22, min(55, age0))
        birth_year = hire.year - age0
        lv = level or pick_level()
        mid = level_mid(lv)
        # 薪酬在带宽 80%–120%
        base = round(mid * rng.uniform(0.82, 1.18) / 100) * 100
        # 试用期 3 或 6 个月
        prob_m = 3 if rng.random() < 0.75 else 6
        probation_end = hire + timedelta(days=30 * prob_m)
        return Employee(
            employee_id=new_emp_id(),
            name_mask=mask_name(rng),
            gender=gender,
            birth_year=birth_year,
            hire_date=hire,
            leave_date=None,
            leave_type=None,
            leave_reason=None,
            dept_id=dept or pick_dept(),
            level_code=lv,
            base_salary=float(base),
            is_key_talent=1 if (lv in ("L4", "L5", "L6", "L7") and rng.random() < 0.35) or rng.random() < 0.08 else 0,
            probation_end=probation_end,
        )

    # 初始在职：入职日在 2025-01-01 之前
    for _ in range(n_initial):
        years_back = rng.random() ** 1.4 * 8  # 偏新人
        hire = START_MONTH - timedelta(days=int(years_back * 365) + rng.randint(0, 20))
        if hire >= START_MONTH:
            hire = START_MONTH - timedelta(days=rng.randint(30, 400))
        employees.append(make_employee(hire))

    # 事件与成本、快照累积
    events: list[dict] = []
    event_seq = 1

    def add_event(
        emp: Employee,
        etype: str,
        edate: date,
        from_dept=None,
        to_dept=None,
        from_level=None,
        to_level=None,
        reason_code=None,
        note=None,
    ):
        nonlocal event_seq
        events.append(
            {
                "event_id": f"EV{event_seq:06d}",
                "employee_id": emp.employee_id,
                "event_type": etype,
                "event_date": edate.isoformat(),
                "from_dept": from_dept,
                "to_dept": to_dept,
                "from_level": from_level,
                "to_level": to_level,
                "reason_code": reason_code,
                "note": note,
            }
        )
        event_seq += 1

    for e in employees:
        add_event(e, "hire", e.hire_date, to_dept=e.dept_id, to_level=e.level_code)

    # 按月模拟：入职、离职、调岗、晋升、调薪
    # 目标：12 月末约 4000 在职；月度主动离职率约 1.2–2.0%，被动 0.3–0.6%
    active = list(employees)

    snapshots: list[dict] = []
    costs: list[dict] = []
    hc_rows: list[dict] = []

    # 各月业务季节性：Q2/Q4 招聘更猛，3 月、9 月离职略高
    hire_mult = [1.0, 0.9, 1.3, 1.4, 1.1, 1.0, 0.85, 0.9, 1.2, 1.15, 1.0, 0.7]
    leave_mult = [1.1, 0.9, 1.35, 1.0, 0.95, 1.05, 0.9, 0.85, 1.25, 1.0, 0.95, 1.15]

    for mi, ms in enumerate(months):
        me = month_end(ms)
        n_act = len(active)

        # ---- 离职 ----
        vol_rate = 0.014 * leave_mult[mi]
        invol_rate = 0.004 * leave_mult[mi]
        n_vol = max(0, int(n_act * vol_rate + rng.gauss(0, 3)))
        n_invol = max(0, int(n_act * invol_rate + rng.gauss(0, 1.5)))

        # 试用期离职额外一批
        probationers = [
            e for e in active if e.hire_date > ms - timedelta(days=180) and e.probation_end >= ms
        ]
        n_prob = max(0, int(len(probationers) * 0.04 + rng.random() * 2))

        leavers_set: set[str] = set()
        candidates = active[:]
        rng.shuffle(candidates)

        def pick_leave_reason(prefer_invol: bool, probation: bool = False) -> tuple[str, str]:
            if probation:
                return "R06", "invol"
            pool = [(r[0], r[2], r[3]) for r in LEAVE_REASONS]
            if prefer_invol:
                pool = [(c, t, w) for c, t, w in pool if t == "invol"] or pool
            else:
                pool = [(c, t, w) for c, t, w in pool if t == "vol"] or pool
            codes = [(c, w) for c, t, w in pool]
            code = weighted_choice(codes, rng)
            typ = next(t for c, t, w in pool if c == code)
            return code, typ

        for e in candidates:
            if len(leavers_set) >= n_vol + n_invol + n_prob:
                break
            # 试用期优先抽一部分
            is_prob = e in probationers and len([x for x in leavers_set if True]) < n_prob and rng.random() < 0.4
            want_invol = len([x for x in leavers_set]) >= n_vol  # 粗略
            if is_prob or rng.random() < (vol_rate + invol_rate) * 8:
                if e.employee_id in leavers_set:
                    continue
                # 控制数量
                current_leaves = len(leavers_set)
                if current_leaves >= n_vol + n_invol + n_prob:
                    break
                probation_flag = e.hire_date >= ms - timedelta(days=100) and rng.random() < 0.35
                if current_leaves < n_vol:
                    reason, ltype = pick_leave_reason(False, probation_flag)
                else:
                    reason, ltype = pick_leave_reason(True, probation_flag)
                ld = random_day_in_month(ms, rng)
                if ld < e.hire_date:
                    ld = e.hire_date + timedelta(days=1)
                e.leave_date = ld
                e.leave_type = ltype
                e.leave_reason = reason
                leavers_set.add(e.employee_id)
                add_event(
                    e,
                    "leave",
                    ld,
                    from_dept=e.dept_id,
                    from_level=e.level_code,
                    reason_code=reason,
                    note=ltype,
                )

        # 若未达目标人数，再随机补离职
        need = (n_vol + n_invol + n_prob) - len(leavers_set)
        if need > 0:
            for e in candidates:
                if need <= 0:
                    break
                if e.employee_id in leavers_set or e.leave_date:
                    continue
                reason, ltype = pick_leave_reason(rng.random() < 0.25)
                ld = random_day_in_month(ms, rng)
                if ld < e.hire_date:
                    continue
                e.leave_date = ld
                e.leave_type = ltype
                e.leave_reason = reason
                leavers_set.add(e.employee_id)
                add_event(
                    e, "leave", ld, from_dept=e.dept_id, from_level=e.level_code, reason_code=reason, note=ltype
                )
                need -= 1

        active = [e for e in active if e.employee_id not in leavers_set]

        # ---- 入职：净增路径 + 填补离职 ----
        remaining_months = N_MONTHS - mi
        gap_to_target = TARGET_ACTIVE_END - len(active)
        # 本月计划净增
        planned_net = gap_to_target / max(1, remaining_months)
        planned_hires = int(len(leavers_set) + planned_net * hire_mult[mi] + rng.gauss(5, 8))
        planned_hires = max(int(30 * hire_mult[mi]), min(220, planned_hires))

        new_hires: list[Employee] = []
        for _ in range(planned_hires):
            hd = random_day_in_month(ms, rng)
            emp = make_employee(hd)
            employees.append(emp)
            active.append(emp)
            new_hires.append(emp)
            add_event(emp, "hire", hd, to_dept=emp.dept_id, to_level=emp.level_code)

        # ---- 调岗 / 晋升 / 调薪（小比例）----
        n_transfer = max(1, int(len(active) * 0.008))
        n_promo = max(1, int(len(active) * 0.006))
        n_salary = max(1, int(len(active) * (0.04 if ms.month in (4, 10) else 0.01)))

        pool_a = active[:]
        rng.shuffle(pool_a)
        for e in pool_a[:n_transfer]:
            old = e.dept_id
            new_d = pick_dept()
            if new_d == old:
                continue
            ed = random_day_in_month(ms, rng)
            add_event(e, "transfer", ed, from_dept=old, to_dept=new_d, from_level=e.level_code, to_level=e.level_code)
            e.dept_id = new_d

        rng.shuffle(pool_a)
        level_codes = [c for c, *_ in LEVELS]
        for e in pool_a[:n_promo]:
            idx = level_codes.index(e.level_code)
            if idx >= len(level_codes) - 1:
                continue
            if rng.random() > 0.5:
                continue
            old_l = e.level_code
            new_l = level_codes[idx + 1]
            ed = random_day_in_month(ms, rng)
            add_event(e, "promotion", ed, from_dept=e.dept_id, to_dept=e.dept_id, from_level=old_l, to_level=new_l)
            e.level_code = new_l
            # 晋升调薪
            e.base_salary = round(e.base_salary * rng.uniform(1.08, 1.18) / 100) * 100

        rng.shuffle(pool_a)
        for e in pool_a[:n_salary]:
            old_s = e.base_salary
            rate = rng.uniform(0.03, 0.12)
            e.base_salary = round(old_s * (1 + rate) / 100) * 100
            ed = random_day_in_month(ms, rng)
            add_event(
                e,
                "salary_adjust",
                ed,
                from_dept=e.dept_id,
                to_dept=e.dept_id,
                from_level=e.level_code,
                to_level=e.level_code,
                note=f"{rate:.2%}",
            )

        # ---- 月末快照 + 成本 ----
        month_key = ms.strftime("%Y-%m")
        dept_level_actual: dict[tuple[str, str], int] = {}

        for e in active:
            age = me.year - e.birth_year
            tenure_days = (me - e.hire_date).days
            snapshots.append(
                {
                    "snapshot_month": month_key,
                    "snapshot_date": me.isoformat(),
                    "employee_id": e.employee_id,
                    "dept_id": e.dept_id,
                    "level_code": e.level_code,
                    "status": "active",
                    "gender": e.gender,
                    "age_band": age_band_from_age(age),
                    "tenure_band": tenure_band_from_days(tenure_days),
                    "is_key_talent": e.is_key_talent,
                    "is_probation": 1 if me <= e.probation_end else 0,
                    "base_salary": e.base_salary,
                }
            )
            key = (e.dept_id, e.level_code)
            dept_level_actual[key] = dept_level_actual.get(key, 0) + 1

            # 成本：月薪 + 奖金分摊 + 加班 + 企业社保公积金
            bonus = 0.0
            if ms.month == 1:
                bonus = e.base_salary * rng.uniform(0.5, 2.0)  # 年终奖计入 1 月
            elif ms.month in (6, 12) and rng.random() < 0.3:
                bonus = e.base_salary * rng.uniform(0.1, 0.4)
            overtime = round(e.base_salary * rng.uniform(0, 0.06), 2) if e.dept_id in ("D01", "D03", "D05") else round(
                e.base_salary * rng.uniform(0, 0.02), 2
            )
            # 企业部分约 社保 20% + 公积金 12% 基数简化为 base
            ss = round(e.base_salary * 0.20, 2)
            hf = round(e.base_salary * 0.12, 2)
            other = round(rng.uniform(50, 400), 2)
            costs.append(
                {
                    "employee_id": e.employee_id,
                    "month": month_key,
                    "dept_id": e.dept_id,
                    "level_code": e.level_code,
                    "cost_center": e.dept_id,
                    "base_salary": e.base_salary,
                    "bonus": round(bonus, 2),
                    "overtime_pay": overtime,
                    "social_security_co": ss,
                    "housing_fund_co": hf,
                    "other_cost": other,
                    "total_cost": round(e.base_salary + bonus + overtime + ss + hf + other, 2),
                }
            )

        # 编制：实际 * (1.02~1.12) 取整，体现空编
        for (dept_id, level_code), actual in dept_level_actual.items():
            vac_ratio = rng.uniform(0.03, 0.14)
            # 部分部门故意高空编
            if dept_id in ("D01", "D03") and mi < 6:
                vac_ratio = rng.uniform(0.08, 0.18)
            budget = max(actual, int(round(actual * (1 + vac_ratio))))
            hc_rows.append(
                {
                    "dept_id": dept_id,
                    "level_code": level_code,
                    "month": month_key,
                    "hc_budget": budget,
                    "hc_actual": actual,
                }
            )

        print(
            f"  {month_key}: active={len(active)}, hires={len(new_hires)}, "
            f"leaves={len(leavers_set)}, events_total={len(events)}"
        )

    # ---------- 写 SQLite ----------
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE dim_date (
            date_key TEXT PRIMARY KEY,          -- YYYY-MM-DD
            month_key TEXT NOT NULL,           -- YYYY-MM
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            month_name TEXT NOT NULL,
            quarter TEXT NOT NULL,
            year_month_label TEXT NOT NULL,    -- 2025年1月
            is_month_end INTEGER NOT NULL,
            month_index INTEGER NOT NULL       -- 1..12 演示期
        );

        CREATE TABLE dim_org (
            dept_id TEXT PRIMARY KEY,
            dept_name TEXT NOT NULL,
            dept_group TEXT NOT NULL,          -- P产品技术 / S商业 / F职能 / O运营支持
            sort_order INTEGER NOT NULL
        );

        CREATE TABLE dim_level (
            level_code TEXT PRIMARY KEY,
            level_name TEXT NOT NULL,
            level_band TEXT NOT NULL,          -- IC / M / E
            salary_mid INTEGER NOT NULL,
            sort_order INTEGER NOT NULL
        );

        CREATE TABLE dim_leave_reason (
            reason_code TEXT PRIMARY KEY,
            reason_name TEXT NOT NULL,
            leave_category TEXT NOT NULL       -- vol / invol / other
        );

        CREATE TABLE dim_employee (
            employee_id TEXT PRIMARY KEY,
            name_mask TEXT NOT NULL,
            gender TEXT NOT NULL,
            birth_year INTEGER NOT NULL,
            hire_date TEXT NOT NULL,
            leave_date TEXT,
            leave_type TEXT,
            leave_reason_code TEXT,
            current_dept_id TEXT,
            current_level_code TEXT,
            is_key_talent INTEGER NOT NULL,
            probation_end TEXT,
            status_end TEXT NOT NULL            -- active / left（期末状态）
        );

        CREATE TABLE fact_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_month TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            dept_id TEXT NOT NULL,
            level_code TEXT NOT NULL,
            status TEXT NOT NULL,
            gender TEXT NOT NULL,
            age_band TEXT NOT NULL,
            tenure_band TEXT NOT NULL,
            is_key_talent INTEGER NOT NULL,
            is_probation INTEGER NOT NULL,
            base_salary REAL NOT NULL
        );

        CREATE TABLE fact_event (
            event_id TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            event_type TEXT NOT NULL,          -- hire/leave/transfer/promotion/salary_adjust
            event_date TEXT NOT NULL,
            event_month TEXT NOT NULL,
            from_dept TEXT,
            to_dept TEXT,
            from_level TEXT,
            to_level TEXT,
            reason_code TEXT,
            note TEXT
        );

        CREATE TABLE fact_cost (
            cost_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            month TEXT NOT NULL,
            dept_id TEXT NOT NULL,
            level_code TEXT NOT NULL,
            cost_center TEXT NOT NULL,
            base_salary REAL NOT NULL,
            bonus REAL NOT NULL,
            overtime_pay REAL NOT NULL,
            social_security_co REAL NOT NULL,
            housing_fund_co REAL NOT NULL,
            other_cost REAL NOT NULL,
            total_cost REAL NOT NULL
        );

        CREATE TABLE fact_hc_budget (
            hc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_id TEXT NOT NULL,
            level_code TEXT NOT NULL,
            month TEXT NOT NULL,
            hc_budget INTEGER NOT NULL,
            hc_actual INTEGER NOT NULL
        );

        -- 月度汇总（方便快速核对 / 不进 PBI 也可）
        CREATE TABLE agg_monthly_kpi (
            month TEXT PRIMARY KEY,
            headcount_end INTEGER NOT NULL,
            headcount_begin INTEGER NOT NULL,
            headcount_avg REAL NOT NULL,
            hires INTEGER NOT NULL,
            leaves INTEGER NOT NULL,
            leaves_vol INTEGER NOT NULL,
            leaves_invol INTEGER NOT NULL,
            turnover_rate REAL NOT NULL,
            hc_budget_total INTEGER NOT NULL,
            occupancy_rate REAL NOT NULL,
            total_cost REAL NOT NULL,
            cost_per_capita REAL NOT NULL
        );
        """
    )

    # meta
    cur.executemany(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        [
            ("title", "HR Compensation & People Analytics Demo"),
            ("locale", "zh-CN"),
            ("currency", "CNY"),
            ("period_start", months[0].isoformat()),
            ("period_end", end_of_period.isoformat()),
            ("seed", str(seed)),
            ("target_active_end", str(TARGET_ACTIVE_END)),
            ("generated_note", "模拟数据，仅用于面试/学习演示，非真实个人信息"),
            ("version", "1.0"),
        ],
    )

    # dim_date: 每天 + 月度索引
    d0 = months[0]
    d1 = end_of_period
    cur_d = d0
    month_index_map = {m.strftime("%Y-%m"): i + 1 for i, m in enumerate(months)}
    month_names = "一月 二月 三月 四月 五月 六月 七月 八月 九月 十月 十一月 十二月".split()
    date_rows = []
    while cur_d <= d1:
        mk = cur_d.strftime("%Y-%m")
        me = month_end(date(cur_d.year, cur_d.month, 1))
        date_rows.append(
            (
                cur_d.isoformat(),
                mk,
                cur_d.year,
                cur_d.month,
                month_names[cur_d.month - 1],
                f"Q{(cur_d.month - 1) // 3 + 1}",
                f"{cur_d.year}年{cur_d.month}月",
                1 if cur_d == me else 0,
                month_index_map.get(mk, 0),
            )
        )
        cur_d += timedelta(days=1)
    cur.executemany(
        """INSERT INTO dim_date VALUES (?,?,?,?,?,?,?,?,?)""",
        date_rows,
    )

    # dim_org
    group_map = {"P": "产品技术", "S": "商业前线", "F": "职能支持", "O": "运营支持"}
    cur.executemany(
        "INSERT INTO dim_org VALUES (?,?,?,?)",
        [(d[0], d[1], group_map[d[2]], i + 1) for i, d in enumerate(DEPTS)],
    )

    # dim_level
    cur.executemany(
        "INSERT INTO dim_level VALUES (?,?,?,?,?)",
        [(c, n, b, mid, i + 1) for i, (c, n, b, mid, _) in enumerate(LEVELS)],
    )

    # dim_leave_reason
    cur.executemany(
        "INSERT INTO dim_leave_reason VALUES (?,?,?)",
        [(c, n, t) for c, n, t, _ in LEAVE_REASONS],
    )

    # dim_employee
    emp_end_status = {e.employee_id: ("left" if e.leave_date else "active") for e in employees}
    # 期末部门/职级：用最后快照覆盖；无快照的用对象字段
    last_snap: dict[str, tuple[str, str]] = {}
    for s in snapshots:
        last_snap[s["employee_id"]] = (s["dept_id"], s["level_code"])

    emp_rows = []
    for e in employees:
        dept, lv = last_snap.get(e.employee_id, (e.dept_id, e.level_code))
        emp_rows.append(
            (
                e.employee_id,
                e.name_mask,
                e.gender,
                e.birth_year,
                e.hire_date.isoformat(),
                e.leave_date.isoformat() if e.leave_date else None,
                e.leave_type,
                e.leave_reason,
                dept,
                lv,
                e.is_key_talent,
                e.probation_end.isoformat(),
                emp_end_status[e.employee_id],
            )
        )
    cur.executemany(
        """INSERT INTO dim_employee VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        emp_rows,
    )

    # facts
    cur.executemany(
        """INSERT INTO fact_snapshot (
            snapshot_month, snapshot_date, employee_id, dept_id, level_code,
            status, gender, age_band, tenure_band, is_key_talent, is_probation, base_salary
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                s["snapshot_month"],
                s["snapshot_date"],
                s["employee_id"],
                s["dept_id"],
                s["level_code"],
                s["status"],
                s["gender"],
                s["age_band"],
                s["tenure_band"],
                s["is_key_talent"],
                s["is_probation"],
                s["base_salary"],
            )
            for s in snapshots
        ],
    )

    cur.executemany(
        """INSERT INTO fact_event VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                ev["event_id"],
                ev["employee_id"],
                ev["event_type"],
                ev["event_date"],
                ev["event_date"][:7],
                ev["from_dept"],
                ev["to_dept"],
                ev["from_level"],
                ev["to_level"],
                ev["reason_code"],
                ev["note"],
            )
            for ev in events
        ],
    )

    cur.executemany(
        """INSERT INTO fact_cost (
            employee_id, month, dept_id, level_code, cost_center,
            base_salary, bonus, overtime_pay, social_security_co,
            housing_fund_co, other_cost, total_cost
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                c["employee_id"],
                c["month"],
                c["dept_id"],
                c["level_code"],
                c["cost_center"],
                c["base_salary"],
                c["bonus"],
                c["overtime_pay"],
                c["social_security_co"],
                c["housing_fund_co"],
                c["other_cost"],
                c["total_cost"],
            )
            for c in costs
        ],
    )

    cur.executemany(
        """INSERT INTO fact_hc_budget (dept_id, level_code, month, hc_budget, hc_actual)
           VALUES (?,?,?,?,?)""",
        [(h["dept_id"], h["level_code"], h["month"], h["hc_budget"], h["hc_actual"]) for h in hc_rows],
    )

    # 月度 KPI 汇总
    for i, ms in enumerate(months):
        mk = ms.strftime("%Y-%m")
        hc_end = cur.execute(
            "SELECT COUNT(*) FROM fact_snapshot WHERE snapshot_month=? AND status='active'", (mk,)
        ).fetchone()[0]
        if i == 0:
            # 期初 ≈ 期初在职：用当月在职 - 当月入职 + 当月离职 近似，或单独统计
            hires_m = cur.execute(
                "SELECT COUNT(*) FROM fact_event WHERE event_type='hire' AND event_month=?", (mk,)
            ).fetchone()[0]
            leaves_m = cur.execute(
                "SELECT COUNT(*) FROM fact_event WHERE event_type='leave' AND event_month=?", (mk,)
            ).fetchone()[0]
            hc_begin = hc_end - hires_m + leaves_m
        else:
            prev = months[i - 1].strftime("%Y-%m")
            hc_begin = cur.execute(
                "SELECT COUNT(*) FROM fact_snapshot WHERE snapshot_month=? AND status='active'", (prev,)
            ).fetchone()[0]
            hires_m = cur.execute(
                "SELECT COUNT(*) FROM fact_event WHERE event_type='hire' AND event_month=?", (mk,)
            ).fetchone()[0]
            leaves_m = cur.execute(
                "SELECT COUNT(*) FROM fact_event WHERE event_type='leave' AND event_month=?", (mk,)
            ).fetchone()[0]

        leaves_vol = cur.execute(
            """SELECT COUNT(*) FROM fact_event e
               JOIN dim_leave_reason r ON e.reason_code = r.reason_code
               WHERE e.event_type='leave' AND e.event_month=? AND r.leave_category='vol'""",
            (mk,),
        ).fetchone()[0]
        leaves_invol = cur.execute(
            """SELECT COUNT(*) FROM fact_event e
               JOIN dim_leave_reason r ON e.reason_code = r.reason_code
               WHERE e.event_type='leave' AND e.event_month=? AND r.leave_category='invol'""",
            (mk,),
        ).fetchone()[0]

        hc_avg = (hc_begin + hc_end) / 2.0
        turnover = leaves_m / hc_avg if hc_avg else 0.0
        bud = cur.execute(
            "SELECT COALESCE(SUM(hc_budget),0), COALESCE(SUM(hc_actual),0) FROM fact_hc_budget WHERE month=?",
            (mk,),
        ).fetchone()
        occ = bud[1] / bud[0] if bud[0] else 0.0
        total_cost = cur.execute(
            "SELECT COALESCE(SUM(total_cost),0) FROM fact_cost WHERE month=?", (mk,)
        ).fetchone()[0]
        cpc = total_cost / hc_avg if hc_avg else 0.0

        cur.execute(
            """INSERT INTO agg_monthly_kpi VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                mk,
                hc_end,
                hc_begin,
                round(hc_avg, 2),
                hires_m,
                leaves_m,
                leaves_vol,
                leaves_invol,
                round(turnover, 6),
                bud[0],
                round(occ, 6),
                round(total_cost, 2),
                round(cpc, 2),
            ),
        )

    # 索引
    cur.executescript(
        """
        CREATE INDEX idx_snap_month ON fact_snapshot(snapshot_month);
        CREATE INDEX idx_snap_dept ON fact_snapshot(dept_id);
        CREATE INDEX idx_snap_emp ON fact_snapshot(employee_id);
        CREATE INDEX idx_event_month ON fact_event(event_month);
        CREATE INDEX idx_event_type ON fact_event(event_type);
        CREATE INDEX idx_event_emp ON fact_event(employee_id);
        CREATE INDEX idx_cost_month ON fact_cost(month);
        CREATE INDEX idx_cost_dept ON fact_cost(dept_id);
        CREATE INDEX idx_hc_month ON fact_hc_budget(month);
        """
    )

    conn.commit()

    # 统计
    stats = {
        "db_path": str(db_path),
        "employees_total": cur.execute("SELECT COUNT(*) FROM dim_employee").fetchone()[0],
        "employees_active_end": cur.execute(
            "SELECT COUNT(*) FROM dim_employee WHERE status_end='active'"
        ).fetchone()[0],
        "snapshots": cur.execute("SELECT COUNT(*) FROM fact_snapshot").fetchone()[0],
        "events": cur.execute("SELECT COUNT(*) FROM fact_event").fetchone()[0],
        "cost_rows": cur.execute("SELECT COUNT(*) FROM fact_cost").fetchone()[0],
        "hc_rows": cur.execute("SELECT COUNT(*) FROM fact_hc_budget").fetchone()[0],
        "date_rows": cur.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0],
    }
    print("\n=== 生成完成 ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n=== 月度 KPI 预览 ===")
    for row in cur.execute(
        "SELECT month, headcount_end, hires, leaves, printf('%.2f%%', turnover_rate*100), "
        "printf('%.1f%%', occupancy_rate*100), printf('%.0f', total_cost) FROM agg_monthly_kpi ORDER BY month"
    ):
        print(
            f"  {row[0]}  在职={row[1]:5d}  入={row[2]:4d}  离={row[3]:4d}  "
            f"离职率={row[4]:>7}  占用={row[5]:>6}  成本={row[6]}"
        )

    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="生成 HR 演示 SQLite 数据库")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "hr_analytics_demo.db",
        help="输出 .db 路径",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    print(f"生成数据库 → {args.output}")
    build_db(args.output, seed=args.seed)


if __name__ == "__main__":
    main()
