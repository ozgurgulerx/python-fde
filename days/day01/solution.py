"""Day 01 · A support ticket, by hand.

Replace each `raise NotImplementedError` with your own code. The brief and the
rules are in README.md next to this file. Standard library only, no imports
needed.
"""


def line_total(unit_price, quantity, discount_pct=0):
    """Price of one order line after a percentage discount, rounded to 2 decimals.

    line_total(12, 3) -> 36.0
    line_total(19.99, 3, 10) -> 53.97

    Raise ValueError if quantity is negative or discount_pct is outside 0..100.
    """
    raise NotImplementedError


def ticket_ref(prefix, number):
    """Reference such as "SUP-00042": tidy upper-case prefix, number padded to 5 digits.

    ticket_ref(" sup ", 42) -> "SUP-00042"
    ticket_ref("BILL", 123456) -> "BILL-123456"

    Raise ValueError if number is negative.
    """
    raise NotImplementedError


def clean_subject(raw):
    """Tidy a subject line typed by a customer.

    Remove leading and trailing whitespace, turn every run of whitespace inside
    into one space, and upper-case the first character. Leave the rest as typed.

    clean_subject("  printer   NOT working\\t again ") -> "Printer NOT working again"
    clean_subject("   ") -> ""
    """
    raise NotImplementedError


def priority(subject, is_vip=False):
    """Return "high" or "normal".

    A ticket is high priority when the customer is a VIP, or when the subject
    contains "urgent" or "outage" in any mix of upper and lower case.
    """
    raise NotImplementedError


def with_tag(tags, tag):
    """Return a new list: the given tags, plus tag at the end if it is not already there.

    The caller's list must be left exactly as it was, and the result must always
    be a different list object, even when nothing was added.

    with_tag(["billing"], "vip") -> ["billing", "vip"]
    with_tag(["billing", "vip"], "vip") -> ["billing", "vip"]
    """
    raise NotImplementedError
