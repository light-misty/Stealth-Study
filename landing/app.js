/* 偷偷学官网落地页 · 交互
   ----------------------------------------------------------------------------
   只做四件事：导航投影、滚动揭示、备考台切换、夜读配色切换、FAQ 折叠。
   动画一律走 transform / opacity，滚动监听用 IntersectionObserver
   （不用 window.addEventListener("scroll")），并在 prefers-reduced-motion 下退化。 */

(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var supportsIO = "IntersectionObserver" in window;

  /* ------------------------------------------------ 导航：离开顶部后加投影 */
  var nav = document.getElementById("nav");
  var sentinel = document.getElementById("navSentinel");
  if (nav && sentinel && supportsIO) {
    new IntersectionObserver(
      function (entries) {
        nav.classList.toggle("is-scrolled", !entries[0].isIntersecting);
      },
      { threshold: 0 }
    ).observe(sentinel);
  }

  /* ------------------------------------------------------------ 滚动揭示 */
  var reveals = Array.prototype.slice.call(document.querySelectorAll(".reveal"));

  // 同一组内的元素按 DOM 顺序错开 70ms，形成自然的级联而不是整块弹出。
  [".bento", ".steps", ".compare"].forEach(function (selector) {
    var group = document.querySelector(selector);
    if (!group) return;
    Array.prototype.forEach.call(group.children, function (child, i) {
      child.style.setProperty("--d", i * 70 + "ms");
    });
  });

  if (reveals.length) {
    if (reduceMotion || !supportsIO) {
      reveals.forEach(function (el) {
        el.classList.add("is-in");
      });
    } else {
      var revealObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("is-in");
            revealObserver.unobserve(entry.target);
          });
        },
        { rootMargin: "0px 0px -12% 0px", threshold: 0.12 }
      );
      reveals.forEach(function (el) {
        revealObserver.observe(el);
      });
    }
  }

  /* -------------------------------------------------- 三张台面：切换面板 */
  var tabsRoot = document.querySelector(".st-tabs");
  if (tabsRoot) {
    var tabs = Array.prototype.slice.call(tabsRoot.querySelectorAll(".st-tab"));
    var bar = tabsRoot.querySelector(".st-bar");
    var wideQuery = window.matchMedia("(max-width: 1024px)");

    var layoutBar = function (instant) {
      var active = tabsRoot.querySelector(".st-tab.is-on");
      if (!active || !bar) return;
      var horizontal = wideQuery.matches;
      var rootRect = tabsRoot.getBoundingClientRect();
      var rect = active.getBoundingClientRect();
      // 指示条内缩 12px，躲开卡片本身的圆角，读起来是卡片内的一条书脊。
      var inset = 12;

      if (instant) bar.style.transition = "none";
      if (horizontal) {
        bar.style.width = Math.max(0, rect.width - inset * 2) + "px";
        bar.style.height = "3px";
        bar.style.transform =
          "translate3d(" + (rect.left - rootRect.left + inset) + "px," +
          (rect.top - rootRect.top + rect.height - 3) + "px,0)";
      } else {
        bar.style.width = "3px";
        bar.style.height = Math.max(0, rect.height - inset * 2) + "px";
        bar.style.transform =
          "translate3d(" + (rect.left - rootRect.left) + "px," +
          (rect.top - rootRect.top + inset) + "px,0)";
      }
      if (instant) {
        void bar.offsetWidth;
        bar.style.transition = "";
      }
    };

    var selectTab = function (tab) {
      tabs.forEach(function (candidate) {
        var on = candidate === tab;
        candidate.classList.toggle("is-on", on);
        candidate.setAttribute("aria-selected", on ? "true" : "false");
        var pane = document.getElementById(candidate.getAttribute("aria-controls"));
        if (!pane) return;
        pane.hidden = !on;
        pane.classList.toggle("is-on", on);
      });
      layoutBar(false);
    };

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        selectTab(tab);
      });
      tab.addEventListener("keydown", function (event) {
        var index = tabs.indexOf(tab);
        var step =
          event.key === "ArrowDown" || event.key === "ArrowRight"
            ? 1
            : event.key === "ArrowUp" || event.key === "ArrowLeft"
              ? -1
              : 0;
        if (!step) return;
        event.preventDefault();
        var next = tabs[(index + step + tabs.length) % tabs.length];
        next.focus();
        selectTab(next);
      });
    });

    layoutBar(true);
    window.addEventListener("resize", function () {
      layoutBar(false);
    });
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        layoutBar(true);
      });
    }
  }

  /* --------------------------------------------- 夜读：浅色 / 夜读 配色切换 */
  var themeDemo = document.querySelector(".theme-demo");
  if (themeDemo) {
    var seg = themeDemo.querySelector(".seg");
    var segButtons = Array.prototype.slice.call(themeDemo.querySelectorAll(".seg-btn"));
    var thumb = themeDemo.querySelector(".seg-thumb");

    var layoutThumb = function (instant) {
      var active = themeDemo.querySelector(".seg-btn.is-on");
      if (!active || !thumb || !seg) return;
      var segRect = seg.getBoundingClientRect();
      var rect = active.getBoundingClientRect();
      if (instant) thumb.style.transition = "none";
      thumb.style.width = rect.width + "px";
      thumb.style.height = rect.height + "px";
      thumb.style.transform =
        "translate3d(" + (rect.left - segRect.left) + "px," + (rect.top - segRect.top) + "px,0)";
      if (instant) {
        void thumb.offsetWidth;
        thumb.style.transition = "";
      }
    };

    segButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        var mode = button.getAttribute("data-mode");
        themeDemo.setAttribute("data-mode", mode);
        segButtons.forEach(function (candidate) {
          var on = candidate === button;
          candidate.classList.toggle("is-on", on);
          candidate.setAttribute("aria-pressed", on ? "true" : "false");
        });
        layoutThumb(false);
      });
    });

    layoutThumb(true);
    window.addEventListener("resize", function () {
      layoutThumb(false);
    });
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        layoutThumb(true);
      });
    }
  }

  /* ------------------------------------------------------------ FAQ 折叠 */
  Array.prototype.forEach.call(document.querySelectorAll(".faq-q"), function (button) {
    button.addEventListener("click", function () {
      var item = button.parentNode;
      var open = item.classList.toggle("is-open");
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
})();
