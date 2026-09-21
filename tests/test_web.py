from runrelay.web import _monitor_page_v2, _server_page


def test_connector_directory_scopes_dynamic_webhook():
    page = _server_page().decode("utf-8")

    assert "connectorDirectory.dataset.configPanel='connectors'" in page
    assert "webhookSettings.dataset.configPanel='connectors'" in page
    assert "data-strategy" in page
    assert "Telegram" in page
    assert "Rokid Glasses" in page
    assert "['weixin','weixin','微','WeChat'" in page
    assert "genericConnectorDefinitions" in page
    assert "connectorTutorials" in page
    assert "connector-help-button" in page
    assert "language-glyph" in page
    assert "quickImportPanel" in page
    assert ".console-search,.dream-rail" in page
    assert "settingsConnectors:'传音'" in page
    assert "settingsServers:'入梦'" in page
    assert "api('/api/connectors/'+key" in page


def test_home_has_pasteable_pid_and_per_server_gpu_quick_add():
    page = _monitor_page_v2().decode("utf-8")

    assert "守梦任务" in page
    assert "loadDreamActivity" in page
    assert "data-add-dream-pid" in page
    assert "clipboardData" in page
    assert "replace(/\\D/g,'')" in page
