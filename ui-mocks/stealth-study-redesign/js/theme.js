/* ============================================================================
   theme.js · 主题状态
   ----------------------------------------------------------------------------
   等价于画布里的 `Colors` 变量集模式切换（浅色 / 夜读）：
   只改 <html data-theme>，颜色由 tokens.css 里的变量整体换肤，不逐个改元素。

   「自动」模式跟随系统外观（prefers-color-scheme）。

   本模块只负责状态，不碰 UI；按钮激活态由 js/app.js 订阅 onChange 后同步。
   ============================================================================ */
(function (global) {
  'use strict';

  var root = document.documentElement;
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  var MODES = ['light', 'dark', 'auto'];

  /* 初始模式由 index.html 的预热脚本写在 data-mode 上，缺省为「自动」 */
  var initial = root.getAttribute('data-mode');
  var mode = MODES.indexOf(initial) >= 0 ? initial : 'auto';

  var listeners = [];

  /** 当前实际生效的外观（「自动」时看系统） */
  function resolved() {
    return mode === 'auto' ? (mq.matches ? 'dark' : 'light') : mode;
  }

  function paint() {
    var theme = resolved();
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-mode', mode);
    for (var i = 0; i < listeners.length; i++) listeners[i](mode, theme);
  }

  function setMode(next) {
    if (MODES.indexOf(next) < 0) return;
    mode = next;
    paint();
  }

  /* 「自动」模式下，系统外观变化要实时跟上 */
  function onSystemChange() {
    if (mode === 'auto') paint();
  }
  if (mq.addEventListener) mq.addEventListener('change', onSystemChange);
  else if (mq.addListener) mq.addListener(onSystemChange);

  global.StealthTheme = {
    MODES: MODES,
    getMode: function () { return mode; },
    resolved: resolved,
    setMode: setMode,
    /** 订阅主题变化，注册时立即回调一次，省去各处手动初始化 */
    onChange: function (fn) {
      listeners.push(fn);
      fn(mode, resolved());
    }
  };
})(window);
