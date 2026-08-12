import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "nocix_fucker" / "logic.py"
SPEC = importlib.util.spec_from_file_location("nocix_fucker.logic", MODULE_PATH)
logic = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(logic)


class LogicTests(unittest.TestCase):
    def test_out_of_stock_page_is_not_available(self):
        page = "AMD Ryzen 3900X 32GB + 2x480GB SSD Preconfig Out Of Stock"

        self.assertFalse(logic.is_in_stock(page, "https://nocix.net/out-of-stock/?id=418"))

    def test_redirect_to_cart_is_available(self):
        self.assertTrue(logic.is_in_stock("Checkout", "https://nocix.net/cart/?id=418"))

    def test_price_comparison_uses_cents(self):
        self.assertTrue(logic.prices_match("Due today: $59.00 USD", 59.0))
        self.assertFalse(logic.prices_match("Due today: $59.01 USD", 59.0))

    def test_config_summary_redacts_sensitive_values(self):
        summary = logic.redact_config(
            {"email": "person@example.com", "password": "secret", "cc_ccv": "123"}
        )

        self.assertEqual(summary["email"], "person@example.com")
        self.assertEqual(summary["password"], "***REDACTED***")
        self.assertEqual(summary["cc_ccv"], "***REDACTED***")


if __name__ == "__main__":
    unittest.main()
