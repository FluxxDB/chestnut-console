"""The frame: Chestnut replaces Overview, HA wears the Axiom theme, and the font is self-hosted."""

from playwright.sync_api import expect

FONT_URL = "/local/chestnut/fonts/JetBrainsMono-Regular.woff2"

# Resolve a theme variable to a computed colour through a probe element on <html>, where HA
# applies the theme.
PROBE_BG = """() => {
  const probe = document.createElement('div');
  probe.style.background = 'var(--primary-background-color)';
  document.documentElement.appendChild(probe);
  const value = getComputedStyle(probe).backgroundColor;
  probe.remove();
  return value;
}"""


def test_overview_is_chestnut(page):
    dashboard = page.locator("chestnut-dashboard")
    expect(dashboard).to_have_count(1, timeout=20_000)
    expect(dashboard).to_contain_text("Main Thermostat")


def test_theme_is_axiom(page):
    page.wait_for_function(f"({PROBE_BG})() === 'rgb(0, 0, 0)'", timeout=20_000)
    assert page.evaluate(PROBE_BG) == "rgb(0, 0, 0)"


def test_font_self_hosted(page, request_log):
    response = page.request.get(FONT_URL)
    assert response.status == 200
    assert response.body()[:4] == b"wOF2"

    # The page's own font loads from /local, and nothing asks a font CDN.
    expect(page.locator("chestnut-dashboard")).to_have_count(1, timeout=20_000)
    loaded = page.evaluate(
        """async () => {
          await document.fonts.load('16px "JetBrains Mono"');
          await document.fonts.ready;
          return document.fonts.check('16px "JetBrains Mono"')
            && [...document.fonts].some(f => f.family.replace(/"/g, '') === 'JetBrains Mono'
                                             && f.status === 'loaded');
        }"""
    )
    assert loaded, "JetBrains Mono did not load"
    assert any(FONT_URL in url for url in request_log)
    cdn = [url for url in request_log if "fonts.googleapis.com" in url or "fonts.gstatic.com" in url]
    assert cdn == []
