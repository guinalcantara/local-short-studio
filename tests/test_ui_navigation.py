from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class StudioNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app_path = Path(__file__).resolve().parents[1] / "app" / "ui.py"

    def test_lateral_destinations_keep_generation_separate_from_account_management(self):
        app = AppTest.from_file(str(self.app_path))
        app.run(timeout=15)
        self.assertFalse(app.exception)
        self.assertEqual(app.sidebar.radio[0].value, "Editar e publicar")

        app.sidebar.radio[0].set_value("Contas do YouTube").run(timeout=15)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Contas do YouTube")
        self.assertFalse(any("Gerar Short" in button.label for button in app.button))

        app.sidebar.radio[0].set_value("Arquivo analítico do canal").run(timeout=15)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Arquivo analítico do canal")
        self.assertFalse(any("Gerar Short" in button.label for button in app.button))


if __name__ == "__main__":
    unittest.main()
