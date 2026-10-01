"""
Tès èdtan siplemantè ak konje san peye dapre kalite peryòd (payroll.py).
Fonksyon pi: pa gen baz done. Tout montan an santim.
"""
from app.routers.payroll import (
    HOURS_PER_PERIOD,
    salaried_overtime_pay,
    unpaid_leave_reduction,
)


def test_monthly_overtime_is_unchanged():
    # 45 000 HTG pa mwa, 8 èdtan siplemantè: menm fòmil ak anvan koreksyon an.
    assert salaried_overtime_pay(4_500_000, 12, 480) == int(4_500_000 / 173.33 * 8 * 1.5)


def test_weekly_overtime_uses_a_40_hour_week():
    # 10 000 HTG pa semèn = 250 HTG/è. 4 èdtan × 1,5 = 1 500 HTG.
    # Anvan koreksyon an (÷ 86,67), sa te bay 692,28 HTG: mwatye.
    assert salaried_overtime_pay(1_000_000, 52, 240) == 150_000


def test_same_yearly_salary_gives_the_same_hourly_rate():
    weekly = 1_000_000
    monthly = weekly * 52 / 12
    per_hour_weekly = weekly / HOURS_PER_PERIOD[52]
    per_hour_monthly = monthly / HOURS_PER_PERIOD[12]
    assert abs(per_hour_weekly - per_hour_monthly) / per_hour_monthly < 0.001


def test_unpaid_day_by_period_type():
    assert unpaid_leave_reduction(1_000_000, 52, 1) == 800_000            # 1/5 semèn
    assert unpaid_leave_reduction(2_250_000, 24, 1) == int(2_250_000 - 2_250_000 / 11)
    assert unpaid_leave_reduction(4_500_000, 12, 1) == int(4_500_000 - 4_500_000 / 22)


def test_unpaid_leave_never_goes_below_zero():
    assert unpaid_leave_reduction(1_000_000, 52, 9) == 0