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

  /* 周报卡：整行是开关，展开态同时改 aria-expanded，读屏才知道折叠边界 */
  var rptHeads = document.querySelectorAll('[data-rpt] > .rpt-h');
  for (var rh = 0; rh < rptHeads.length; rh++) {
    (function (head) {
      head.addEventListener('click', function () {
        var open = head.parentNode.classList.toggle('is-on');
        head.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    })(rptHeads[rh]);
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

  /* ============================================ 备考台：模块内作答交互 ==
     作答类模块的每个状态都要点得动：选项互斥、掌握度互斥、助记有进行中、
     测评与模考能在阶段之间推进。原型的价值就在这条状态链上，静态图做不到。 */

  /* 单选：一组里只能有一个选中 */
  function bindExclusive(root, itemSel, after) {
    var items = root.querySelectorAll(itemSel);
    for (var n = 0; n < items.length; n++) {
      (function (item) {
        item.addEventListener('click', function () {
          for (var m = 0; m < items.length; m++) {
            var on = items[m] === item;
            items[m].classList.toggle('is-on', on);
            if (after) after(items[m], on);
          }
        });
      })(items[n]);
    }
  }
  var optGroups = document.querySelectorAll('.opts');
  for (var og = 0; og < optGroups.length; og++) bindExclusive(optGroups[og], '.opt');
  var pickGroups = document.querySelectorAll('.picks');
  for (var pg = 0; pg < pickGroups.length; pg++) {
    bindExclusive(pickGroups[pg], '.pick', function (item, on) {
      var dot = item.querySelector('.md');
      if (dot) dot.classList.toggle('is-on', on);
    });
  }

  /* 生成助记：先给「生成中…」，再落结果 —— 模型调用没有中间态会被当成假数据 */
  var mnemonicBtns = document.querySelectorAll('[data-mnemonic]');
  for (var mb = 0; mb < mnemonicBtns.length; mb++) {
    (function (btn) {
      var label = btn.textContent;
      btn.addEventListener('click', function () {
        var box = btn.closest('.word').querySelector('.mnemonic');
        btn.disabled = true;
        btn.innerHTML = '<svg class="ic" width="12" height="12"><use href="#i-sparkle"/></svg>生成中…';
        setTimeout(function () {
          box.hidden = false;
          btn.disabled = false;
          btn.innerHTML = '<svg class="ic" width="12" height="12"><use href="#i-sparkle"/></svg>' + label;
        }, 520);
      });
    })(mnemonicBtns[mb]);
  }

  /* 定级测评：作答卷 ↔ 成绩两张态互换 */
  var papers = document.querySelectorAll('[data-assess="paper"]');
  for (var ap = 0; ap < papers.length; ap++) {
    (function (paper) {
      var mod = paper.closest('.mod');
      var result = mod.querySelector('[data-assess="result"]');
      mod.querySelector('[data-assess="finish"]').addEventListener('click', function () {
        paper.hidden = true;
        result.hidden = false;
        result.querySelector('.fill').scrollTop = 0;
      });
      result.querySelector('[data-assess="again"]').addEventListener('click', function () {
        result.hidden = true;
        paper.hidden = false;
      });
    })(papers[ap]);
  }

  /* 听力：提交即判卷，对错都给出下一步；主观题走批改所以这里只有客观题分支 */
  var listenSubmits = document.querySelectorAll('[data-listen="submit"]');
  for (var ls = 0; ls < listenSubmits.length; ls++) {
    (function (submit) {
      var mod = submit.closest('.mod');
      var group = mod.querySelector('.opts');
      var feedback = mod.querySelector('[data-listen="feedback"]');
      var verdict = mod.querySelector('[data-listen-verdict]');
      var next = mod.querySelector('[data-listen="next"]');
      var label = mod.querySelector('[data-listen-label]');
      var index = 3, total = 12;

      submit.addEventListener('click', function () {
        var picked = group.querySelector('.opt.is-on');
        var answer = group.getAttribute('data-answer');
        var right = !!picked && picked.querySelector('.opt-k').textContent === answer;
        for (var i = 0; i < group.children.length; i++) {
          var kid = group.children[i];
          kid.classList.toggle('is-right', right && kid === picked);
          if (!right && kid === picked) kid.classList.add('is-wrong');
        }
        feedback.className = 'verdict ' + (right ? 'verdict--right' : 'verdict--wrong');
        feedback.querySelector('use').setAttribute('href', right ? '#i-check' : '#i-x');
        verdict.textContent = right ? '回答正确' : '回答错误';
        feedback.hidden = false;
        submit.hidden = true;
        next.hidden = false;
      });
      next.addEventListener('click', function () {
        index = index % total + 1;
        label.textContent = '第 ' + index + ' / ' + total + ' 题';
        feedback.hidden = true;
        next.hidden = true;
        submit.hidden = false;
        for (var i = 0; i < group.children.length; i++) {
          group.children[i].classList.remove('is-on', 'is-right', 'is-wrong');
        }
      });
    })(listenSubmits[ls]);
  }

  /* 模考：三阶段倒计时 + 暂停 + 收卡锁定 + 交卷出成绩。
     真实实现的时长由服务端持有，本地 tick 只管显示；原型同样只管显示。 */
  var MOCK_STAGE_SECONDS = [30 * 60, 25 * 60, 40 * 60];
  var mockTimers = document.querySelectorAll('[data-mock-timer]');
  for (var mt = 0; mt < mockTimers.length; mt++) {
    (function (face) {
      var mod = face.closest('.mod');
      var stages = mod.querySelectorAll('.mstage');
      var answers = mod.querySelectorAll('.answer');
      var counter = mod.querySelector('.mod-acts .sec-n');
      var pauseBtn = mod.querySelector('[data-mock="pause"]');
      var ffBtn = mod.querySelector('[data-mock="ff"]');
      var advBtn = mod.querySelector('[data-mock="advance"]');
      var answerBox = mod.querySelector('.fill');
      var result = mod.querySelector('[data-mock-result]');
      var stage = 0, left = MOCK_STAGE_SECONDS[0], paused = false, over = false;

      function clock(sec) {
        var m = Math.floor(Math.max(0, sec) / 60), s = Math.max(0, sec) % 60;
        return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
      }
      function paint() {
        face.textContent = clock(left);
        face.classList.toggle('is-over', left <= 0);
      }
      function lock(box, note) {
        var ta = box.querySelector('textarea');
        box.classList.add('is-locked');
        ta.disabled = true;
        ta.placeholder = note;
        var tag = box.querySelector('.tag');
        tag.className = 'tag tag--muted';
        tag.innerHTML = '<svg class="ic" width="11" height="11"><use href="#i-lock"/></svg>' +
          (note === '本阶段尚未开始' ? '未开始' : '已锁定');
      }
      function unlock(box) {
        box.classList.remove('is-locked');
        box.querySelector('textarea').disabled = false;
        box.querySelector('textarea').placeholder = '';
        var tag = box.querySelector('.tag');
        tag.className = 'tag tag--accent';
        tag.textContent = '当前阶段';
      }
      function show() {
        for (var i = 0; i < stages.length; i++) {
          stages[i].classList.toggle('is-on', i === stage);
          stages[i].classList.toggle('is-done', i < stage);
          stages[i].querySelector('.mstage-k').innerHTML = i < stage
            ? '<svg class="ic" width="12" height="12"><use href="#i-check"/></svg>已结束'
            : (i === stage
              ? '<svg class="ic" width="12" height="12"><use href="#i-pause"/></svg>进行中'
              : '<svg class="ic" width="12" height="12"><use href="#i-lock"/></svg>未开始');
          if (i < stage) lock(answers[i], '本阶段已收卡');
          else if (i === stage) unlock(answers[i]);
          else lock(answers[i], '本阶段尚未开始');
        }
        counter.textContent = '第 ' + (stage + 1) + ' / ' + stages.length + ' 阶段';
        advBtn.textContent = stage === stages.length - 1 ? '交卷' : '结束本阶段';
        left = MOCK_STAGE_SECONDS[stage];
        over = false;
        paint();
      }
      setInterval(function () {
        if (paused || over || result.hidden === false) return;
        if (left > 0) { left -= 1; paint(); return; }
        if (stage < stages.length - 1) advance();
      }, 1000);
      function advance() {
        if (left <= 0) over = true;
        if (stage < stages.length - 1) { stage += 1; show(); }
        else submitAll();
      }
      function submitAll() {
        result.hidden = false;
        answerBox.hidden = true;
        pauseBtn.hidden = true;
        ffBtn.hidden = true;
        advBtn.hidden = true;
        counter.textContent = '已交卷';
        for (var i = 0; i < stages.length; i++) {
          stages[i].classList.remove('is-on');
          stages[i].classList.add('is-done');
        }
        result.scrollIntoView({ block: 'nearest' });
      }
      pauseBtn.addEventListener('click', function () {
        paused = !paused;
        pauseBtn.querySelector('use').setAttribute('href', paused ? '#i-play' : '#i-pause');
        pauseBtn.querySelector('span').textContent = paused ? '继续' : '暂停';
      });
      ffBtn.addEventListener('click', function () { left = Math.max(0, left - 600); paint(); });
      advBtn.addEventListener('click', advance);
      show();
    })(mockTimers[mt]);
  }

  /* =============================================== 证书：知识点树交互 ==
     掌握度 Picker 改的是「同一行的文字 + 点阵」两件事，缺一读屏就丢信息；
     折叠只收更深的连续几行，与真实实现按 depth 展开的行为一致。        */
  var LEVELS = ['unknown', 'fuzzy', 'mastered'];
  var LEVEL_WORDS = { unknown: '未掌握', fuzzy: '模糊', mastered: '已掌握' };
  var lvlSets = document.querySelectorAll('.lvls');
  for (var lv = 0; lv < lvlSets.length; lv++) {
    (function (set) {
      var btns = set.querySelectorAll('.lvl');
      var label = set.parentNode.querySelector('.lvl-l');
      for (var b = 0; b < btns.length; b++) {
        (function (btn, i) {
          btn.addEventListener('click', function () {
            for (var m = 0; m < btns.length; m++) {
              btns[m].classList.toggle('is-on', m === i);
              var dot = btns[m].querySelector('.md');
              if (dot) dot.classList.toggle('is-on', m === i);
            }
            var key = LEVELS[i];
            label.textContent = LEVEL_WORDS[key];
            label.className = 'lvl-l lvl-l--' + key;
          });
        })(btns[b], b);
      }
    })(lvlSets[lv]);
  }

  var trees = document.querySelectorAll('.tree');
  for (var tr = 0; tr < trees.length; tr++) {
    (function (tree) {
      function depth(row) { return parseInt(row.style.getPropertyValue('--d'), 10) || 1; }
      var toggles = tree.querySelectorAll('button.tnode-tw');
      for (var tg = 0; tg < toggles.length; tg++) {
        (function (tw) {
          tw.addEventListener('click', function () {
            var row = tw.parentNode, d = depth(row), seen = false, folded = false;
            for (var sib = row.nextElementSibling; sib && depth(sib) > d; sib = sib.nextElementSibling) {
              if (depth(sib) === d + 1) seen = true;
              if (seen) { sib.hidden = !row.classList.contains('is-folded'); }
            }
            folded = row.classList.toggle('is-folded');
            tw.setAttribute('aria-label', folded ? '展开' : '折叠');
            tw.querySelector('use').setAttribute('href', folded ? '#i-chev-right' : '#i-minus');
          });
        })(toggles[tg]);
      }
    })(trees[tr]);
  }

  /* 就地新增节点：只有一个表单槽位，点谁就在谁下面展开 */
  var addForms = document.querySelectorAll('[data-add-form]');
  var addRoot = document.querySelector('[data-add-node]');
  function hideAddForms() {
    for (var f = 0; f < addForms.length; f++) addForms[f].hidden = true;
  }
  for (var af = 0; af < addForms.length; af++) {
    (function (form) {
      var cancel = form.querySelectorAll('.btn')[1];
      cancel.addEventListener('click', hideAddForms);
      form.querySelectorAll('.btn')[0].addEventListener('click', hideAddForms);
    })(addForms[af]);
  }
  if (addRoot) addRoot.addEventListener('click', function () {
    hideAddForms();
    addForms[0].hidden = false;
    addForms[0].querySelector('input').focus();
  });

  /* 创建提醒：按钮就地变成已创建徽标，与真实实现的 remindBusy 单向流转一致 */
  var reminders = document.querySelectorAll('[data-remind]');
  for (var rm = 0; rm < reminders.length; rm++) {
    (function (btn) {
      btn.addEventListener('click', function () {
        btn.outerHTML = '<span class="tag tag--ok"><svg class="ic" width="11" height="11"><use href="#i-check"/></svg>已创建提醒</span>';
      });
    })(reminders[rm]);
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
