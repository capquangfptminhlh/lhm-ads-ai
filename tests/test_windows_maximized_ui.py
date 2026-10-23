"""Desktop maximization and viewport-safe first-run layout regression guards."""
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def test_native_window_starts_maximized_without_kiosk_fullscreen(tmp_path, monkeypatch):
    import uvicorn
    from windows import desktop_window as desktop

    created = {}

    class FakeServer:
        def __init__(self, config):
            self.should_exit = False

        def run(self):
            while not self.should_exit:
                time.sleep(.005)

    def fake_create_window(title, **kwargs):
        created.update(kwargs)
        created['title'] = title
        return object()

    def fake_start(**kwargs):
        created['renderer'] = kwargs.get('gui')

    monkeypatch.setattr(uvicorn, 'Server', FakeServer)
    monkeypatch.setattr(desktop, 'wait_for_service', lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, 'webview', SimpleNamespace(
        create_window=fake_create_window, start=fake_start
    ))

    desktop.run_window(object(), port=18766, setup_token=None, data_folder=tmp_path)

    assert created['maximized'] is True
    assert created.get('fullscreen') is not True
    assert created['resizable'] is True
    assert created['min_size'][0] <= 800
    assert created['min_size'][1] <= 600
    assert created['background_color'] == '#0b0c0e'
    assert created['renderer'] == 'edgechromium'
    assert created['url'] == 'http://localhost:18766/studio'


def test_setup_dark_skin_is_full_bleed_and_hides_preview_on_small_viewports():
    css = (ROOT / 'static' / 'setup-dark.css').read_text(encoding='utf-8')
    assert '.app-frame{' in css
    assert 'max-width:none;min-height:100vh;min-height:100dvh' in css
    assert 'margin:0;border:0;border-radius:0;box-shadow:none' in css
    assert '@media(max-width:1100px)' in css
    assert '.aside-card{display:none!important}' in css
    assert '@media(max-width:660px)' in css
    assert 'overflow-x:clip' in css


def test_setup_form_remains_present_at_first_run():
    html = (ROOT / 'static' / 'setup.html').read_text(encoding='utf-8')
    for name in ('setup-form', 'email', 'password', 'confirm', 'submit'):
        assert f'id="{name}"' in html
