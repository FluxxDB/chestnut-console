// Shared Axiom styles for the Chestnut dashboard, as constructable stylesheets.
//
// - fontFaces: JetBrains Mono v2.304 (OFL, fonts/OFL.txt), self-hosted from /local, no CDN,
//   plus a body rule so HA's own pages use the theme's font.
//   Files from https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
//   (sha256 6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf): fonts/webfonts/*.woff2, OFL.txt.
//   @font-face rules are ignored inside shadow roots, so this sheet is adopted by the
//   document itself; importing this module does that once. HA also loads this module on every
//   page (frontend: extra_module_url), so the Axiom theme's font works outside the dashboard.
// - styles: tokens and base rules, for each component's shadow root
//   (shadowRoot.adoptedStyleSheets = [styles]).

const FONT_DIR = '/local/chestnut/fonts';

export const FONT_FAMILY = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

export const fontFaces = new CSSStyleSheet();
fontFaces.replaceSync(`
@font-face {
  font-family: 'JetBrains Mono';
  src: url('${FONT_DIR}/JetBrainsMono-Regular.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('${FONT_DIR}/JetBrainsMono-Bold.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}
/* HA's index.html hard-codes body { font-family: Roboto } and many elements inherit it; use
   the theme's body font instead (unchanged for themes that don't set one). */
body { font-family: var(--ha-font-family-body, Roboto, Noto, sans-serif); }
`);

export function adoptFonts(doc = globalThis.document) {
  if (!doc || doc.adoptedStyleSheets.includes(fontFaces)) return;
  doc.adoptedStyleSheets = [...doc.adoptedStyleSheets, fontFaces];
}

adoptFonts();

// Colours and type from the spec's Style section (exact values).
export const styles = new CSSStyleSheet();
styles.replaceSync(`
:host {
  --cn-bg: #000000;
  --cn-card: #111111;
  --cn-raised: #191919;
  --cn-hairline: #202020;
  --cn-outline: #3a3a3a;
  --cn-text: #eeeeee;
  --cn-text-2: #b4b4b4;
  --cn-label: #7e7e7e;
  --cn-ember: #da5c2c;
  --cn-blue: #2a7fff;
  --cn-radius: 2px;
  --cn-font: ${FONT_FAMILY};

  display: block;
  min-height: 100%;
  background: var(--cn-bg);
  color: var(--cn-text);
  font-family: var(--cn-font);
  font-size: 14px;
  line-height: 1.6;
}
*, *::before, *::after { box-sizing: border-box; }
button, select, input { font-family: inherit; }
button:focus-visible, select:focus-visible, input:focus-visible, a:focus-visible {
  outline: 1px solid var(--cn-text);
  outline-offset: 2px;
}
.label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cn-label);
}
.card {
  background: var(--cn-card);
  border: 1px solid var(--cn-hairline);
  border-radius: var(--cn-radius);
}
`);
