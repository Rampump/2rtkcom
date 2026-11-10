/* ============================================================
   2RTK 内容页交互：目录自动生成 + 代码块一键复制
   无依赖，直接内联引入
   ============================================================ */
(function () {
  'use strict';

  /* ---------- 1. 由正文 h2[id] 自动生成右侧目录 ---------- */
  var tocBox = document.querySelector('[data-toc]');
  var heads = [].slice.call(document.querySelectorAll('.prose h2[id]'));

  if (tocBox) {
    if (!heads.length) {
      tocBox.style.display = 'none';
    } else {
      var html = '<div class="toc-title">本页目录</div>';
      heads.forEach(function (h) {
        html += '<a href="#' + h.id + '">' + h.textContent.replace(/\s+/g, ' ').trim() + '</a>';
      });
      tocBox.innerHTML = html;

      var links = [].slice.call(tocBox.querySelectorAll('a'));
      var ticking = false;

      function sync() {
        ticking = false;
        var offset = 96;
        var current = 0;
        for (var i = 0; i < heads.length; i++) {
          if (heads[i].getBoundingClientRect().top - offset <= 0) current = i;
        }
        links.forEach(function (a, i) {
          a.classList.toggle('is-active', i === current);
        });
      }

      window.addEventListener('scroll', function () {
        if (!ticking) {
          ticking = true;
          window.requestAnimationFrame(sync);
        }
      }, { passive: true });

      sync();
    }
  }

  /* ---------- 2. 代码块复制按钮 ---------- */
  document.querySelectorAll('.code-block').forEach(function (block) {
    var head = block.querySelector('.code-head');
    var pre = block.querySelector('pre');
    if (!head || !pre) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = '复制';
    head.appendChild(btn);

    btn.addEventListener('click', function () {
      var text = pre.innerText;
      var done = function () {
        btn.textContent = '已复制';
        setTimeout(function () { btn.textContent = '复制'; }, 1400);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {
          btn.textContent = '复制失败';
        });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) { btn.textContent = '复制失败'; }
        document.body.removeChild(ta);
      }
    });
  });
})();
