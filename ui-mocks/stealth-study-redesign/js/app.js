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
     设计稿原本是一张屏一幅画，这里合成一个可交互应用：屏与屏之间靠 device 的
     data-view 驱动，侧栏哪一组导航可见也由它决定（css/sidebar.css）。
     屏的顺序 = DOM 顺序 = 控制条按钮顺序 = 数字快捷键顺序，四处共用一份。   */
  var viewEls = [];
  var allViews = document.querySelectorAll('.main .view');
  for (var v = 0; v < allViews.length; v++) {
    if (allViews[v].getAttribute('data-view-name')) viewEls.push(allViews[v]);
  }
  var viewButtons = document.querySelectorAll('[data-view-btn]');

  function viewName(el) { return el.getAttribute('data-view-name'); }

  function setView(name) {
    var hit = null;
    for (var i = 0; i < viewEls.length; i++) {
      var on = viewName(viewEls[i]) === name;
      viewEls[i].classList.toggle('is-on', on);
      if (on) hit = viewEls[i];
    }
    if (!hit) return;
    device.setAttribute('data-view', name);
    for (var b = 0; b < viewButtons.length; b++) {
      viewButtons[b].classList.toggle('is-on', viewButtons[b].getAttribute('data-view-btn') === name);
    }
  }

  function viewNameAt(index) {
    return viewEls[index] ? viewName(viewEls[index]) : null;
  }
  function viewIndexOf(name) {
    for (var i = 0; i < viewEls.length; i++) if (viewName(viewEls[i]) === name) return i;
    return -1;
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

  /* ============================================================== 页签 ==
     备考台「一屏一模块」的切换器。页签与面板同属一个 .view，靠 data-tab /
     data-pane 配对；右栏里「去做这件事」的按钮用 data-goto-tab 走同一个入口，
     保证跳过去之后页签选中态和面板内容不会分家。                          */
  function selectTab(view, name, focus) {
    var tabs = view.querySelectorAll('.st-tab');
    var hit = null;
    for (var t = 0; t < tabs.length; t++) {
      var on = tabs[t].getAttribute('data-tab') === name;
      tabs[t].classList.toggle('is-on', on);
      tabs[t].setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) hit = tabs[t];
    }
    if (!hit) return false;

    var panes = view.querySelectorAll('.st-pane');
    for (var p = 0; p < panes.length; p++) {
      panes[p].classList.toggle('is-on', panes[p].getAttribute('data-pane') === hit.getAttribute('data-tab'));
    }

    /* 页签条溢出时把选中项带回视野中央，否则窄窗口下会选中一个看不见的页签 */
    var strip = hit.parentNode;
    if (strip.scrollWidth > strip.clientWidth) {
      strip.scrollLeft = Math.max(0, hit.offsetLeft - (strip.clientWidth - hit.offsetWidth) / 2);
    }
    if (focus) hit.focus();
    return true;
  }

  var tabViews = document.querySelectorAll('.st-tabs');
  for (var tb = 0; tb < tabViews.length; tb++) {
    (function (strip) {
      var view = strip.closest('.view');
      var items = strip.querySelectorAll('.st-tab');

      function move(from, delta) {
        var next = (from + delta + items.length) % items.length;
        selectTab(view, items[next].getAttribute('data-tab'), true);
      }

      for (var n = 0; n < items.length; n++) {
        (function (tab, index) {
          tab.addEventListener('click', function () {
            selectTab(view, tab.getAttribute('data-tab'), false);
          });
          tab.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowRight') { move(index, 1); e.preventDefault(); }
            else if (e.key === 'ArrowLeft') { move(index, -1); e.preventDefault(); }
            else if (e.key === 'Home') { selectTab(view, items[0].getAttribute('data-tab'), true); e.preventDefault(); }
            else if (e.key === 'End') { selectTab(view, items[items.length - 1].getAttribute('data-tab'), true); e.preventDefault(); }
          });
        })(items[n], n);
      }
    })(tabViews[tb]);
  }

  var gotoTabs = document.querySelectorAll('[data-goto-tab]');
  for (var gt = 0; gt < gotoTabs.length; gt++) {
    (function (btn) {
      btn.addEventListener('click', function () {
        selectTab(btn.closest('.view'), btn.getAttribute('data-goto-tab'), false);
      });
    })(gotoTabs[gt]);
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

  /* ============================================================ 快捷键 ==
     数字键按屏序切屏（设置 → 新建会话 → 三个备考台），T 切明暗。
     表单控件内的按键不参与：在备考台里敲「1」多半是在填目标分数。      */
  document.addEventListener('keydown', function (e) {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    var digit = parseInt(e.key, 10);
    if (!isNaN(digit) && digit >= 1 && digit <= viewEls.length) {
      setView(viewNameAt(digit - 1));
    } else if (e.key === 't' || e.key === 'T') {
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
     ?view=cet&tab=mock&mode=dark —— 评审时可以直接把某一屏的某个模块甩过来。 */
  try {
    var q = new URLSearchParams(window.location.search);
    var qv = q.get('view');
    var qm = q.get('mode');
    var qi = viewIndexOf(qv);
    if (qi >= 0) {
      setView(qv);
      var qt = q.get('tab');
      if (qt) selectTab(viewEls[qi], qt, false);
    }
    if (qm === 'light' || qm === 'dark' || qm === 'auto') StealthTheme.setMode(qm);
  } catch (err) { /* 非法参数忽略 */ }
})();
