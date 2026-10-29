// <chestnut-dashboard>: the Chestnut dashboard, HA's Overview (one panel view).
// Task 4 stub: the frame and title only; the tabs and cards come in later tasks.
import { styles } from './style.js';

const DEFAULT_DEVICE = 'Main Thermostat';

class ChestnutDashboard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.adoptedStyleSheets = [styles];
    this._config = { device_name: DEFAULT_DEVICE };
    this._hass = null;
  }

  setConfig(config) {
    this._config = { device_name: DEFAULT_DEVICE, ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._render();
  }

  getCardSize() {
    return 12;
  }

  _render() {
    if (this._rendered) return;
    this._rendered = true;
    this.shadowRoot.innerHTML = `
      <style>
        header { border-bottom: 1px solid var(--cn-hairline); }
        .head { max-width: 1200px; margin: 0 auto; padding: 24px 24px 16px; display: flex; flex-direction: column; gap: 2px; }
        .prompt { font-size: 12px; color: var(--cn-label); }
        h1 { margin: 0; font-size: 24px; line-height: 1.33; font-weight: 700; }
      </style>
      <header>
        <div class="head">
          <span class="prompt">~/chestnut/main-thermostat</span>
          <h1>Main Thermostat</h1>
        </div>
      </header>
    `;
  }
}

if (!customElements.get('chestnut-dashboard')) {
  customElements.define('chestnut-dashboard', ChestnutDashboard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'chestnut-dashboard')) {
  window.customCards.push({
    type: 'chestnut-dashboard',
    name: 'Chestnut dashboard',
    description: 'The Main Thermostat dashboard (Axiom).',
  });
}
