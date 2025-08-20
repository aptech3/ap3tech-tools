from ai_analysis import parse_processors_and_accounts, sum_deposits_and_accounts


def test_parse_processors_and_accounts_simple():
    text = """
    06/01 ACH CREDIT STRIPE PAYOUT $123.45
    06/02 POS PURCHASE CAFE -$12.00
    06/03 ACH CREDIT SQUARE INC $200.00
    ... account 1234 deposit ...
    """
    procs, accts = parse_processors_and_accounts(text)
    assert "Stripe" in procs or "STRIPE" in [p.upper() for p in procs]
    assert any(a == "1234" for a in accts)


def test_sum_deposits_and_accounts_totals():
    text = "STRIPE PAYOUT $100.00\nSQUARE INC $50.00\nacct 9876 deposit $25.00"
    procs = ["Stripe", "Square"]
    accts = ["9876"]
    p_totals, total, a_totals = sum_deposits_and_accounts(text, procs, accts)
    assert p_totals.get("Stripe", 0) == 100.00
    assert p_totals.get("Square", 0) == 50.00
    assert total == 150.00
    assert a_totals["9876"]["qty"] == 1
    assert a_totals["9876"]["total"] == 25.00
