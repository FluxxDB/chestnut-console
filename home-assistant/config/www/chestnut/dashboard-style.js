// The dashboard's own CSS (inside its shadow root, after the shared Axiom sheet from style.js).
export const DASHBOARD_CSS = `
  [hidden] { display: none !important; }
  .page { min-height: 100%; display: flex; flex-direction: column; }
  header { border-bottom: 1px solid var(--cn-hairline); }
  .head { max-width: 1200px; margin: 0 auto; padding: 24px 24px 0; display: flex; flex-direction: column; gap: 16px; }
  .titlebar { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 24px; }
  .title { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .prompt { font-size: 12px; color: var(--cn-label); }
  h1 { margin: 0; font-size: 24px; line-height: 1.33; font-weight: 700; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 24px; font-size: 12px; color: var(--cn-text-2); }
  .tabs { display: flex; gap: 24px; overflow-x: auto; font-size: 12px; letter-spacing: 0.08em; }
  .tab { background: transparent; border: none; border-bottom: 2px solid transparent; color: var(--cn-label); padding: 8px 0 12px; font-size: 12px; letter-spacing: 0.08em; cursor: pointer; white-space: nowrap; }
  .tab[aria-selected="true"] { border-bottom-color: var(--cn-text); color: var(--cn-text); }
  .wrap { max-width: 1200px; width: 100%; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 24px; }
  .row { display: flex; flex-wrap: wrap; gap: 24px; align-items: stretch; }
  section { padding: 24px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .between { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .small { font-size: 12px; color: var(--cn-text-2); }
  .room { flex: 999 1 560px; }
  .runtime .totals b { color: var(--cn-text); font-weight: 400; }
  .thermo { flex: 1 1 340px; background: var(--cn-raised); gap: 20px; }
  .stepper { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .step { width: 56px; height: 56px; flex: 0 0 56px; background: transparent; border: 1px solid var(--cn-outline); border-radius: 2px; color: var(--cn-text); font-size: 24px; cursor: pointer; }
  .big { font-size: 64px; line-height: 1; font-weight: 700; letter-spacing: -0.02em; white-space: nowrap; }
  .center { text-align: center; }
  .status { display: flex; flex-direction: column; align-items: center; gap: 2px; min-height: 44px; }
  .status .word { font-size: 14px; }
  .group { display: flex; flex-direction: column; gap: 8px; }
  .segs { display: flex; gap: 8px; }
  .seg { flex: 1; min-width: 0; min-height: 44px; padding: 0 8px; background: transparent; color: var(--cn-text); border: 1px solid var(--cn-outline); border-radius: 2px; font-size: 13px; cursor: pointer; }
  .seg[aria-pressed="true"] { background: var(--cn-text); color: #000000; border-color: var(--cn-text); font-weight: 700; }
  button:disabled { opacity: 0.4; cursor: default; }
  .pair { display: flex; gap: 16px; flex-wrap: wrap; }
  .pair > .group:first-child { flex: 1 1 120px; }
  .pair > .group:last-child { flex: 1 1 160px; }
  .foot { border-top: 1px solid var(--cn-hairline); padding-top: 16px; display: flex; flex-direction: column; gap: 12px; }
  .resume { min-height: 44px; background: var(--cn-ember); color: var(--cn-text); border: none; border-radius: 2px; font-size: 14px; font-weight: 700; cursor: pointer; }
  .chart { display: block; width: 100%; height: 56px; }
  .barrow { display: flex; align-items: center; gap: 12px; }
  .barrow > span { flex: 0 0 64px; font-size: 12px; color: var(--cn-text-2); }
  .bars { flex: 1; min-width: 0; display: flex; align-items: flex-end; gap: 1px; height: 10px; }
  .bars > i { flex: 1; min-width: 0; height: 2px; background: var(--cn-hairline); }
  .axis { display: flex; justify-content: space-between; font-size: 12px; color: var(--cn-label); }
  .runtime .axis { padding-left: 76px; }
  .totals { display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--cn-text-2); }
  .empty { font-size: 12px; color: var(--cn-label); }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 24px; }
  .link { background: transparent; border: none; color: var(--cn-text); font-size: 12px; text-decoration: underline; cursor: pointer; padding: 0; }
  .daybar { display: flex; height: 24px; gap: 1px; }
  .daybar > span { min-width: 0; overflow: hidden; display: flex; align-items: center; padding-left: 6px; font-size: 11px; }
  .daybar.off { opacity: 0.4; }
  .nowrow { position: relative; height: 16px; }
  .now { position: absolute; top: 0; width: 1px; height: 12px; background: var(--cn-ember); }
  .kv { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
  .kv > span:first-child { color: var(--cn-text-2); }
  @media (max-width: 860px) { .desk { display: none !important; } }
`;
