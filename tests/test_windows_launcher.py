import importlib.util
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "windows_launcher", Path(__file__).resolve().parents[1] / "packaging" / "windows_launcher.py"
)
windows_launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows_launcher)


def test_second_launch_opens_dashboard_again():
    with (
        patch.object(windows_launcher, "urlopen") as urlopen,
        patch.object(windows_launcher.webbrowser, "open") as open_browser,
        patch.object(windows_launcher, "RunRelayService") as service,
        patch.object(windows_launcher, "serve") as serve,
    ):
        urlopen.return_value.__enter__.return_value = None
        windows_launcher.main()

    open_browser.assert_called_once_with("http://127.0.0.1:8765")
    service.assert_not_called()
    serve.assert_not_called()
