"""
Tès avans sou salè — kalkil vèsman yo (fonksyon pi, san baz done).
Tès API yo (demann, apwobasyon, /run, balans) nan test_salary_advances.py.
"""
from app.routers.salary_advances import installment_for, plan_repayments


def test_installment_rounds_up():
    assert installment_for(1_000_000, 3) == 333_334
    assert installment_for(1_000_000, 3) * 3 >= 1_000_000
    assert installment_for(500_000, 1) == 500_000


def test_one_installment_per_payslip():
    assert plan_repayments([(1_000_000, 333_334)], 5_000_000, False) == [333_334]


def test_last_installment_is_the_rest():
    assert plan_repayments([(333_332, 333_334)], 5_000_000, False) == [333_332]


def test_never_more_than_net():
    assert plan_repayments([(1_000_000, 400_000)], 250_000, False) == [250_000]


def test_zero_or_negative_net_takes_nothing():
    assert plan_repayments([(1_000_000, 400_000)], 0, False) == [0]
    assert plan_repayments([(1_000_000, 400_000)], -5, False) == [0]


def test_last_payslip_settles_everything():
    assert plan_repayments([(900_000, 300_000)], 5_000_000, True) == [900_000]
    assert plan_repayments([(900_000, 300_000)], 600_000, True) == [600_000]


def test_older_advance_is_paid_first():
    assert plan_repayments([(200_000, 200_000), (500_000, 250_000)], 300_000, False) == [200_000, 100_000]