import calendar
from datetime import date

from django.db import transaction

from invoice.models import Customer, CustomerStepRule, Work, WorkStep


def _month_last_day(year, month):
    return calendar.monthrange(year, month)[1]


def _next_month(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1


def compute_planned_due_date(rule, period_year, period_month):
    if rule is None or rule.rule_type == CustomerStepRule.RuleType.NO_RULE:
        return None

    if rule.rule_type == CustomerStepRule.RuleType.THIS_MONTH_DAY:
        last_day = _month_last_day(period_year, period_month)
        day = min(rule.day_of_month, last_day)
        return date(period_year, period_month, day)

    if rule.rule_type == CustomerStepRule.RuleType.NEXT_MONTH_DAY:
        next_year, next_month = _next_month(period_year, period_month)
        last_day = _month_last_day(next_year, next_month)
        day = min(rule.day_of_month, last_day)
        return date(next_year, next_month, day)

    if rule.rule_type == CustomerStepRule.RuleType.THIS_MONTH_NTH_WEEKDAY:
        days_in_month = _month_last_day(period_year, period_month)
        matches = []
        for day in range(1, days_in_month + 1):
            if date(period_year, period_month, day).weekday() == rule.weekday:
                matches.append(day)
        if not matches:
            return None
        index = min(rule.nth, len(matches)) - 1
        return date(period_year, period_month, matches[index])

    if rule.rule_type == CustomerStepRule.RuleType.THIS_MONTH_LAST_NTH_DAY:
        last_day = _month_last_day(period_year, period_month)
        day = last_day - (rule.last_nth - 1)
        if day < 1:
            day = 1
        return date(period_year, period_month, day)

    return None


def ensure_work_for_customer(customer, period_year, period_month):
    work, created = Work.objects.get_or_create(
        customer=customer,
        period_year=period_year,
        period_month=period_month,
        defaults={
            "customer_region": customer.region,
            "assigned_cm": customer.responsible_cm,
            "assigned_lcm": customer.responsible_lcm,
            "assigned_lcm_scnx": getattr(customer.responsible_lcm, "scnx", None),
        },
    )

    rules_by_step = {
        rule.step_no: rule
        for rule in CustomerStepRule.objects.filter(customer=customer)
    }

    for step_no in range(1, 5):
        step, _ = WorkStep.objects.get_or_create(work=work, step_no=step_no)
        if step.planned_due_date is None:
            rule = rules_by_step.get(step_no)
            step.planned_due_date = compute_planned_due_date(
                rule, period_year, period_month
            )
            step.save()

    return work


def bulk_ensure_work_for_month(target_year, target_month, scoped_customers=None):
    created_count = 0
    existed_count = 0
    steps_created_count = 0

    customers = scoped_customers if scoped_customers is not None else Customer.objects.all()

    with transaction.atomic():
        for customer in customers:
            work, created = Work.objects.get_or_create(
                customer=customer,
                period_year=target_year,
                period_month=target_month,
                defaults={
                    "customer_region": customer.region,
                    "assigned_cm": customer.responsible_cm,
                    "assigned_lcm": customer.responsible_lcm,
                    "assigned_lcm_scnx": getattr(customer.responsible_lcm, "scnx", None),
                },
            )
            if created:
                created_count += 1
            else:
                existed_count += 1

            rules_by_step = {
                rule.step_no: rule
                for rule in CustomerStepRule.objects.filter(customer=customer)
            }

            for step_no in range(1, 5):
                step, step_created = WorkStep.objects.get_or_create(
                    work=work, step_no=step_no
                )
                if step_created:
                    steps_created_count += 1
                if step.planned_due_date is None:
                    rule = rules_by_step.get(step_no)
                    step.planned_due_date = compute_planned_due_date(
                        rule, target_year, target_month
                    )
                    step.save()

    return created_count, existed_count, steps_created_count
