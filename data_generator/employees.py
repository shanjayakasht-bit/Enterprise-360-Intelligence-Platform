"""Generates the employees dataset: account managers, salespeople, project managers,
support agents, and supporting departments, with a simple reporting hierarchy."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from .master_data import (
    CUSTOMER_FACING_DEPARTMENTS,
    DEPARTMENT_TITLES,
    DEPARTMENT_WEIGHTS,
    DEPARTMENTS,
    FAKE,
    NP_RNG,
    REFERENCE_DATE,
    REGION_WEIGHTS,
    REGIONS,
    RNG,
    make_id,
    random_date,
    weighted_choice,
)

EMPLOYEE_HISTORY_START = REFERENCE_DATE - relativedelta(years=8)


def _department_counts(n):
    counts = {dept: max(1, round(n * w)) for dept, w in zip(DEPARTMENTS, DEPARTMENT_WEIGHTS)}
    for dept in CUSTOMER_FACING_DEPARTMENTS:
        counts[dept] = max(counts[dept], min(2, n))
    diff = n - sum(counts.values())
    largest_dept = max(counts, key=counts.get)
    counts[largest_dept] += diff
    return counts


def generate(n):
    counts = _department_counts(n)
    dept_sequence = []
    for dept, count in counts.items():
        dept_sequence.extend([dept] * count)
    RNG.shuffle(dept_sequence)

    rows = []
    executive_ids = []
    for i, dept in enumerate(dept_sequence, start=1):
        employee_id = make_id("EMP", i)
        first_name = FAKE.first_name()
        last_name = FAKE.last_name()
        hire_date = random_date(RNG, EMPLOYEE_HISTORY_START, REFERENCE_DATE)
        rows.append({
            "employee_id": employee_id,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}{i}@nexora.com",
            "department": dept,
            "job_title": RNG.choice(DEPARTMENT_TITLES[dept]),
            "region": weighted_choice(RNG, REGIONS, REGION_WEIGHTS),
            "hire_date": hire_date.isoformat(),
            "manager_id": None,
            "performance_score": round(max(0.0, min(100.0, NP_RNG.normal(76, 11))), 1),
            "is_active": RNG.random() > 0.05,
        })
        if dept == "Executive":
            executive_ids.append(employee_id)

    if not executive_ids:
        executive_ids = [rows[0]["employee_id"]]

    ceo_id = executive_ids[0]
    for row in rows:
        if row["employee_id"] == ceo_id:
            row["manager_id"] = None
        elif row["employee_id"] in executive_ids:
            row["manager_id"] = ceo_id
        else:
            row["manager_id"] = RNG.choice(executive_ids)

    return pd.DataFrame(rows)
