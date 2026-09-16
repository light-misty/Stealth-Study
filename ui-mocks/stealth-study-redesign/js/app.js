/* ============================================================================
   app.js · 界面交互
   ----------------------------------------------------------------------------
   逐块对应设计稿里的可交互元素。所有逻辑都是原型的程度（不落库、不发请求），
   接入真实工程时替换对应实现即可。

   依赖：js/theme.js（StealthTheme）
   ============================================================================ */
(function () {
  'use strict';

  var device = document.getElementById('device');

  /* ============================================================ 视图切换 ==
     设计稿是两张独立的屏（设置 / 新建会话），这里合成一个可交互应用。
     切的不只是内容 —— 侧栏两套导航也按稿子各自还原，由 device 的
     data-view 驱动 css/sidebar.css 里的显隐规则。                       */
  var viewSettings = document.getElementById('viewSettings');
  var viewNew = document.getElementById('viewNew');
  var viewButtons = document.querySelectorAll('[data-view-btn]');

  function setView(name) {
    device.setAttribute('data-view', name);
    viewSettings.classList.toggle('is-on', name === 'settings');
    viewNew.classList.toggle('is-on', name === 'new');
    for (var i = 0; i < viewButtons.length; i++) {
      viewButtons[i].classList.toggle('is-on', viewButtons[i].getAttribute('data-view-btn') === name);
    }
  }
  for (var i = 0; i < viewButtons.length; i++) {
    (function (btn) {
      btn.addEventListener('click', function () { setView(btn.getAttribute('data-view-btn')); });
    })(viewButtons[i]);
  }

  /* ============================================================ 主题控件 ==
     设置页的「主题」分段与控制条上的主题按钮共用 data-mode-btn，
     一处接线即可双向同步。                                             */
  var modeButtons = document.querySelectorAll('[data-mode-btn]');

  StealthTheme.onChange(function (mode) {
    for (var i = 0; i < modeButtons.length; i++) {
      modeButtons[i].classList.toggle('is-on', modeButtons[i].getAttribute('data-mode-btn') === mode);
    }
  });
  for (var j = 0; j < modeButtons.length; j++) {
    (function (btn) {
      btn.addEventListener('click', function () { StealthTheme.setMode(btn.getAttribute('data-mode-btn')); });
    })(modeButtons[j]);
  }

  /* ======================================================== 设置页导航 ==
     设计稿只展开了「通用」页，其余导航项给出占位说明，不静默假装有内容。 */
  var panel = document.getElementById('panel');
  var panelPh = document.getElementById('panelPh');
  var pageTitle = document.getElementById('pageTitle');
  var pageSub = document.getElementById('pageSub');
  var navItems = document.querySelectorAll('.nav-set--settings .nav-item');

  var SUB_GENERAL = 'Stealth Study 在本机的外观与行为。改动立即生效，无需重启。';
  var SUB_PLACEHOLDER = '本次设计稿只展开了「通用」页的设置项。';

  for (var k = 0; k < navItems.length; k++) {
    (function (item) {
      item.addEventListener('click', function () {
        var label = item.getAttribute('data-nav');
        for (var n = 0; n < navItems.length; n++) {
          navItems[n].classList.toggle('is-active', navItems[n] === item);
        }
        var isGeneral = label === '通用';
        panel.classList.toggle('is-ph', !isGeneral);
        panelPh.textContent = '「' + label + '」页面未包含在本次设计稿中。';
        pageTitle.textContent = label;
        pageSub.textContent = isGeneral ? SUB_GENERAL : SUB_PLACEHOLDER;
        setView('settings');
      });
    })(navItems[k]);
  }

  /* ================================================================ 开关 ==
     即时生效的布尔设置，选中态由 aria-checked 表达（CSS 据此换色/位移）。 */
  var switches = document.querySelectorAll('.sw');
  for (var s = 0; s < switches.length; s++) {
    (function (sw) {
      sw.addEventListener('click', function () {
        sw.setAttribute('aria-checked', sw.getAttribute('aria-checked') === 'true' ? 'false' : 'true');
      });
    })(switches[s]);
  }

  /* ========================================================== 分段控件 ==
     注意「主题」那一组用的是 data-mode-group 而非 data-seg，
     它由上面的主题逻辑单独接管，不要在这里重复处理。                    */
  var segs = document.querySelectorAll('[data-seg]');
  for (var g = 0; g < segs.length; g++) {
    (function (seg) {
      var items = seg.querySelectorAll('.seg-item');
      for (var t = 0; t < items.length; t++) {
        (function (btn) {
          btn.addEventListener('click', function () {
            for (var x = 0; x < items.length; x++) items[x].classList.toggle('is-on', items[x] === btn);
          });
        })(items[t]);
      }
    })(segs[g]);
  }

  /* ============================================================ 步进器 ==
     侧栏密度：1–9。数值设计稿为 5。                                    */
  var densityVal = document.getElementById('densityVal');
  var stepButtons = document.querySelectorAll('.step-btn');
  for (var p = 0; p < stepButtons.length; p++) {
    (function (btn) {
      btn.addEventListener('click', function () {
        var next = parseInt(densityVal.textContent, 10) + parseInt(btn.getAttribute('data-step'), 10);
        densityVal.textContent = Math.max(1, Math.min(9, next));
      });
    })(stepButtons[p]);
  }

  /* ======================================================== 新建会话 == */
  document.getElementById('newSessionBtn').addEventListener('click', function () {
    setView('new');
    document.getElementById('promptInput').focus();
  });

  /* ============================================================ 快捷键 == */
  document.addEventListener('keydown', function (e) {
    if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === '1') setView('settings');
    else if (e.key === '2') setView('new');
    else if (e.key === 't' || e.key === 'T') {
      StealthTheme.setMode(StealthTheme.getMode() === 'light' ? 'dark' : 'light');
    }
  });

  /* =================================================== 等比缩放铺满视口 ==
     内部始终按设计稿原始画布 1280×800 排版，再整体等比缩放 ——
     圆角、间距、字号的比例因此不会走形。底部控制条占 DOCK 高度。         */
  var DOCK = 76;
  var MARGIN = 20;
  var W = 1280;
  var H = 800;

  function fit() {
    var availW = Math.max(320, window.innerWidth - MARGIN * 2);
    var availH = Math.max(240, window.innerHeight - DOCK - MARGIN * 2);
    var scale = Math.min(availW / W, availH / H, 1.75);
    device.style.transform = 'translate(' +
      Math.round((window.innerWidth - W * scale) / 2) + 'px,' +
      Math.round((window.innerHeight - DOCK - H * scale) / 2) + 'px) scale(' + scale + ')';
  }
  window.addEventListener('resize', fit);
  fit();

  /* ============================================================ 深链接 ==
     ?view=new&mode=dark 可直接打开指定屏幕与主题。                     */
  try {
    var q = new URLSearchParams(window.location.search);
    var qv = q.get('view');
    var qm = q.get('mode');
    if (qv === 'settings' || qv === 'new') setView(qv);
    if (qm === 'light' || qm === 'dark' || qm === 'auto') StealthTheme.setMode(qm);
  } catch (err) { /* 非法参数忽略 */ }
})();
