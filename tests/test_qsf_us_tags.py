"""Which SEC tags answer for each annual item, and that a reading never passes off a part or an old value as the current whole."""
from terminal.qsf import fundamentals


def _flow(val, year=2025, filed=None):
    return {"start": f"{year}-01-01", "end": f"{year}-12-31", "val": val, "filed": filed or f"{year + 1}-02-20", "form": "10-K"}


def _facts(**concepts):
    return {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in concepts.items()}}}


def test_total_revenue_wins_over_contract_revenue():
    """An apartment REIT reports nearly all revenue as rent, outside contract revenue."""
    a = fundamentals.extract_us(_facts(Revenues=[_flow(1890.0)], RevenueFromContractWithCustomerExcludingAssessedTax=[_flow(10.0)]))
    assert a["revenue"][-1]["val"] == 1890.0


def test_net_revenue_wins_over_contract_revenue():
    a = fundamentals.extract_us(_facts(RevenuesNetOfInterestExpense=[_flow(72.0)], RevenueFromContractWithCustomerExcludingAssessedTax=[_flow(41.0)]))
    assert a["revenue"][-1]["val"] == 72.0


def test_utility_total_revenue_continues_a_stopped_series():
    old = [_flow(10.0, y) for y in (2017, 2018)]
    a = fundamentals.extract_us(_facts(Revenues=old, RegulatedAndUnregulatedOperatingRevenue=[_flow(14.0)], RegulatedOperatingRevenue=[_flow(8.0)]))
    assert a["revenue"][-1]["val"] == 14.0


def test_contract_revenue_stays_when_it_is_all_there_is():
    a = fundamentals.extract_us(_facts(RevenueFromContractWithCustomerExcludingAssessedTax=[_flow(41.0)]))
    assert a["revenue"][-1]["val"] == 41.0


def test_excise_tax_inclusive_revenue_stays_behind_the_exclusive_one():
    a = fundamentals.extract_us(_facts(RevenueFromContractWithCustomerExcludingAssessedTax=[_flow(39.0)], RevenueFromContractWithCustomerIncludingAssessedTax=[_flow(50.0)]))
    assert a["revenue"][-1]["val"] == 39.0


def test_net_income_prefers_the_parent_figure():
    a = fundamentals.extract_us(_facts(NetIncomeLoss=[_flow(90.0)], ProfitLoss=[_flow(100.0)]))
    assert a["net_income"][-1]["val"] == 90.0
    a = fundamentals.extract_us(_facts(ProfitLoss=[_flow(100.0)]))
    assert a["net_income"][-1]["val"] == 100.0


def test_a_retagged_item_continues_its_series_and_is_not_dropped():
    old = [_flow(5.0, y) for y in (2022, 2023)]
    new = [_flow(9.0, y) for y in (2024, 2025)]
    a = fundamentals.drop_stale_series(fundamentals.extract_us(_facts(NetIncomeLoss=[_flow(1.0)], PaymentsToAcquirePropertyPlantAndEquipment=old, PaymentsToAcquireProductiveAssets=new)))
    assert [r["val"] for r in a["capex"]] == [5.0, 5.0, 9.0, 9.0]


def test_an_item_with_another_meaning_never_stands_in_for_operating_income():
    a = fundamentals.extract_us(_facts(IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest=[_flow(5.0)]))
    assert a["op_income"] == []


def test_a_stopped_figure_reads_as_missing_not_zero():
    a = fundamentals.drop_stale_series(fundamentals.extract_us(_facts(Revenues=[_flow(700.0)], NetIncomeLoss=[_flow(70.0)], GrossProfit=[_flow(5.0, 2009)])))
    m = fundamentals.metrics(a, 10.0, "2026-06-01", shares=5.0)
    assert m["gross_margin"] is None and m["net_margin"] == 0.1
