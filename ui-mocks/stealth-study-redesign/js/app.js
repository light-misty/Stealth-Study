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
    /* 侧栏里指向本屏的那一行同时点亮，避免「进了备考台但侧栏没高亮」 */
    var opens = document.querySelectorAll('.nav-item[data-open]');
    for (var o = 0; o < opens.length; o++) {
      opens[o].classList.toggle('is-active', opens[o].getAttribute('data-open') === name);
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

  /* ==================================================== 备考台：侧栏入口 ==
     data-open 的导航行既切屏也自带选中态（选中态在 setView 里统一同步）。 */
  var openLinks = document.querySelectorAll('[data-open]');
  for (var ol = 0; ol < openLinks.length; ol++) {
    (function (btn) {
      btn.addEventListener('click', function () { setView(btn.getAttribute('data-open')); });
    })(openLinks[ol]);
  }

  /* ================================================ 备考台：档案切换器 ==
     「全部档案一眼可见」是这套切换器存在的理由，因此保持横条而非下拉；
     当前档案用橙色胶囊，改名/归档作为低频动作只在 hover 时出现。        */
  var whoPills = document.querySelectorAll('.who-pill');
  for (var wp = 0; wp < whoPills.length; wp++) {
    (function (pill) {
      pill.addEventListener('click', function () {
        var items = pill.closest('.who-list').querySelectorAll('.who-item');
        for (var x = 0; x < items.length; x++) {
          items[x].classList.toggle('is-on', items[x] === pill.parentNode);
        }
      });
    })(whoPills[wp]);
  }

  /* ================================================ 备考台：档案弹窗 ==
     对应 CampusDialog：点遮罩关、按 Esc 关，焦点回到触发它的那个按钮上。 */
  var dialogs = {};
  var allDialogs = document.querySelectorAll('.dlg');
  for (var d = 0; d < allDialogs.length; d++) {
    dialogs[allDialogs[d].getAttribute('data-dlg-id')] = allDialogs[d];
  }
  var lastTrigger = null;

  function closeDialog(el) {
    if (!el) return;
    el.setAttribute('hidden', '');
    if (lastTrigger) { try { lastTrigger.focus(); } catch (e) { /* 已移出文档 */ } }
    lastTrigger = null;
  }
  function openDialog(id, trigger) {
    var el = dialogs[id];
    if (!el) return;
    lastTrigger = trigger || null;
    el.removeAttribute('hidden');
    var first = el.querySelector('input, select, .btn:not([disabled])');
    if (first) { try { first.focus(); } catch (e) { /* 不可聚焦则跳过 */ } }
  }

  var dlgTriggers = document.querySelectorAll('[data-dlg]');
  for (var dt = 0; dt < dlgTriggers.length; dt++) {
    (function (btn) {
      btn.addEventListener('click', function () { openDialog(btn.getAttribute('data-dlg'), btn); });
    })(dlgTriggers[dt]);
  }
  for (var dc = 0; dc < allDialogs.length; dc++) {
    (function (el) {
      el.addEventListener('click', function (e) { if (e.target === el) closeDialog(el); });
      var closes = el.querySelectorAll('[data-dlg-close]');
      for (var c = 0; c < closes.length; c++) {
        (function (btn) { btn.addEventListener('click', function () { closeDialog(el); }); })(closes[c]);
      }
    })(allDialogs[dc]);
  }
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    for (var i = 0; i < allDialogs.length; i++) {
      if (!allDialogs[i].hasAttribute('hidden')) closeDialog(allDialogs[i]);
    }
  });

  /* 已归档弹窗：列表 ↔ 详情是同一张弹窗的两个态，页脚动作整组跟着换。
     每次重新打开都回到列表态 —— 详情页不该有跨次打开的记忆。            */
  var archDialog = document.querySelector('[data-dlg-id="archived"]');
  if (archDialog) {
    function archMode(detail) {
      archDialog.querySelector('.arch-list').toggleAttribute('hidden', detail);
      archDialog.querySelector('.arch-detail').toggleAttribute('hidden', !detail);
      var swaps = archDialog.querySelectorAll('.arch-list-foot, .arch-detail-foot');
      for (var i = 0; i < swaps.length; i++) {
        var wantDetail = swaps[i].classList.contains('arch-detail-foot');
        swaps[i].toggleAttribute('hidden', wantDetail !== detail);
      }
    }
    var archIn = archDialog.querySelectorAll('[data-arch-detail]');
    for (var ai = 0; ai < archIn.length; ai++) {
      (function (btn) { btn.addEventListener('click', function () { archMode(true); }); })(archIn[ai]);
    }
    var archBack = archDialog.querySelectorAll('[data-arch-back]');
    for (var ab = 0; ab < archBack.length; ab++) {
      (function (btn) { btn.addEventListener('click', function () { archMode(false); }); })(archBack[ab]);
    }
    archDialog.addEventListener('click', function (e) {
      if (e.target === archDialog) archMode(false);
    });
    var archTrigger = document.querySelector('[data-dlg="archived"]');
    if (archTrigger) archTrigger.addEventListener('click', function () { archMode(false); });
  }

  /* ======================================================= 复习队列判卷 ==
     答对 / 答错是这一屏唯一的高频动作，点下去必须看得见结果：行落成状态胶囊、
     今日进度与页签上的待办数同时前进。                                   */
  var reviewMods = document.querySelectorAll('.mod[data-review]');
  for (var rv = 0; rv < reviewMods.length; rv++) {
    (function (mod) {
      var total = parseInt(mod.getAttribute('data-review-total'), 10);
      var done = parseInt(mod.getAttribute('data-review-done'), 10);
      var label = mod.querySelector('.sec-n');
      var fill = mod.querySelector('.bar > i');

      function judge(btn, ok) {
        var row = btn.closest('.lrow');
        if (row.classList.contains('is-done')) return;
        row.classList.add('is-done');
        row.querySelector('.lrow-acts').innerHTML =
          '<span class="tag ' + (ok ? 'tag--ok' : 'tag--danger') + '">' + (ok ? '已答对' : '已答错') + '</span>';
        done = Math.min(total, done + 1);
        label.textContent = done + ' / ' + total;
        fill.style.setProperty('--w', Math.round(done / total * 100) + '%');
      }

      var rights = mod.querySelectorAll('.btn--right');
      var wrongs = mod.querySelectorAll('.btn--wrong');
      for (var q = 0; q < rights.length; q++) {
        (function (btn) { btn.addEventListener('click', function () { judge(btn, true); }); })(rights[q]);
      }
      for (var w = 0; w < wrongs.length; w++) {
        (function (btn) { btn.addEventListener('click', function () { judge(btn, false); }); })(wrongs[w]);
      }
    })(reviewMods[rv]);
  }

  /* 能力提示条的「知道了」：关掉即让位给正文，不做二次确认 */
  var dismissals = document.querySelectorAll('[data-dismiss]');
  for (var ds = 0; ds < dismissals.length; ds++) {
    (function (btn) {
      btn.addEventListener('click', function () {
        var box = btn.closest('.alert');
        if (box) box.parentNode.removeChild(box);
      });
    })(dismissals[ds]);
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
