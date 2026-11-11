import sys
import unittest
from pathlib import Path

sys.path[:0] = [
    str(Path(__file__).resolve().parent),
    str(Path(__file__).resolve().parents[1]),
]
import solution
from harness import DayCase


class LineTotal(DayCase):
    def test_price_times_quantity(self):
        self.assertEqual(solution.line_total(12, 3), 36.0)

    def test_discount_is_a_percentage(self):
        self.assertEqual(solution.line_total(19.99, 3, 10), 53.97)
        self.assertEqual(solution.line_total(80, 1, 25), 60.0)

    def test_result_is_rounded_to_two_decimals(self):
        self.assertEqual(solution.line_total(0.1, 3), 0.3)
        self.assertEqual(solution.line_total(3.333, 3), 10.0)

    def test_zero_quantity_and_full_discount_are_allowed(self):
        self.assertEqual(solution.line_total(12, 0), 0.0)
        self.assertEqual(solution.line_total(12, 3, 100), 0.0)

    def test_bad_quantity_or_discount_is_rejected(self):
        for arguments in ((12, -1), (12, 3, -5), (12, 3, 100.5)):
            with self.assertRaises(ValueError, msg=f"line_total{arguments}"):
                solution.line_total(*arguments)


class TicketRef(DayCase):
    def test_number_is_padded_to_five_digits(self):
        self.assertEqual(solution.ticket_ref("SUP", 42), "SUP-00042")
        self.assertEqual(solution.ticket_ref("SUP", 0), "SUP-00000")

    def test_prefix_is_tidied_and_upper_cased(self):
        self.assertEqual(solution.ticket_ref(" sup ", 7), "SUP-00007")

    def test_long_numbers_are_not_cut(self):
        self.assertEqual(solution.ticket_ref("BILL", 123456), "BILL-123456")

    def test_negative_number_is_rejected(self):
        with self.assertRaises(ValueError):
            solution.ticket_ref("SUP", -1)


class CleanSubject(DayCase):
    def test_whitespace_is_trimmed_and_collapsed(self):
        self.assertEqual(
            solution.clean_subject("  printer   NOT working\t again "),
            "Printer NOT working again",
        )

    def test_only_the_first_character_changes_case(self):
        self.assertEqual(
            solution.clean_subject("iPhone app crashes on LOGIN"),
            "IPhone app crashes on LOGIN",
        )

    def test_tidy_input_is_returned_unchanged(self):
        self.assertEqual(solution.clean_subject("Refund request"), "Refund request")

    def test_blank_input_gives_an_empty_string(self):
        self.assertEqual(solution.clean_subject(""), "")
        self.assertEqual(solution.clean_subject(" \t\n "), "")


class Priority(DayCase):
    def test_ordinary_ticket_is_normal(self):
        self.assertEqual(solution.priority("Question about my invoice"), "normal")

    def test_vip_is_always_high(self):
        self.assertEqual(
            solution.priority("Question about my invoice", is_vip=True), "high"
        )

    def test_keywords_match_in_any_case(self):
        for subject in (
            "URGENT: cannot log in",
            "Payment Outage since 9am",
            "this is urgent",
        ):
            self.assertEqual(solution.priority(subject), "high", msg=subject)


class WithTag(DayCase):
    def test_new_tag_goes_at_the_end(self):
        self.assertEqual(solution.with_tag(["billing"], "vip"), ["billing", "vip"])
        self.assertEqual(solution.with_tag([], "vip"), ["vip"])

    def test_existing_tag_is_not_repeated(self):
        self.assertEqual(
            solution.with_tag(["billing", "vip"], "vip"), ["billing", "vip"]
        )

    def test_the_callers_list_is_left_alone(self):
        original = ["billing"]
        solution.with_tag(original, "vip")
        self.assertEqual(original, ["billing"])

    def test_result_is_always_a_different_list(self):
        original = ["billing", "vip"]
        self.assertIsNot(solution.with_tag(original, "vip"), original)
        self.assertIsNot(solution.with_tag(original, "new"), original)


if __name__ == "__main__":
    unittest.main()
