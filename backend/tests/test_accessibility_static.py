"""
Spec section 29 asks for accessibility tests: keyboard nav, ARIA, focus
order, contrast, screen-reader semantics. A real browser/axe-core run is out
of scope for this environment, so these are static assertions against the
ACTUAL shipped frontend/index.html and styles.css — they fail if someone
removes an accessibility feature, which is the main regression risk.
"""
import os

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def _read(name):
    with open(os.path.join(FRONTEND_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_skip_link_present():
    html = _read("index.html")
    assert 'class="skip-link"' in html
    assert 'href="#main"' in html


def test_main_landmark_present():
    html = _read("index.html")
    assert 'id="main"' in html and 'role="main"' in html


def test_tabs_have_aria_roles():
    html = _read("index.html")
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'aria-selected' in html


def test_dropzone_is_keyboard_accessible():
    html = _read("index.html")
    assert 'id="dropzone"' in html
    assert 'tabindex="0"' in html
    assert 'role="button"' in html
    assert 'aria-label=' in html


def test_toast_uses_live_region():
    html = _read("index.html")
    assert 'aria-live="polite"' in html


def test_accessibility_mode_toggle_has_aria_pressed():
    html = _read("index.html")
    assert 'id="accessibilityToggle"' in html
    assert 'aria-pressed' in html


def test_css_defines_focus_visible_indicator():
    css = _read("styles.css")
    assert ":focus-visible" in css


def test_css_does_not_rely_on_color_alone_for_attention_levels():
    """Attention levels (HIGH/MEDIUM/LOW) must always be paired with a text
    badge, never conveyed by color alone -- checked by confirming the badge
    text classes exist alongside the color classes."""
    css = _read("styles.css")
    js = open(os.path.join(FRONTEND_DIR, "app.js"), encoding="utf-8").read()
    assert ".badge-high" in css and ".badge-medium" in css and ".badge-low" in css
    # badge() helper always renders the level text, not just a color swatch
    assert "function badge(level)" in js
    assert "${level}" in js


def test_reduced_motion_media_query_present():
    """Spec section 19 explicitly requires a reduced-motion option."""
    css = _read("styles.css")
    assert "@keyframes fade" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "animation-duration: 0.001ms" in css
