/* ============================================================
   Finance Tracker — shared interactions & animation
   ============================================================ */
(function () {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- Today on empty date inputs ---- */
  document.addEventListener('DOMContentLoaded', () => {
    const today = new Date().toISOString().slice(0, 10);
    document.querySelectorAll('input[type=date]').forEach(i => { if (!i.value) i.value = today; });
    initCountUps();
    initReveal();
    initSparklines();
  });

  /* ---- Count-up numbers ---- */
  function initCountUps() {
    const els = document.querySelectorAll('[data-count]');
    if (reduce) { els.forEach(el => { el.textContent = el.dataset.formatted || el.textContent; }); return; }
    els.forEach(el => {
      const target = parseFloat(el.dataset.count);
      const prefix = el.dataset.prefix || '';
      const suffix = el.dataset.suffix || '';
      const decimals = parseInt(el.dataset.decimals || '0', 10);
      const dur = 1100;
      const start = performance.now();
      function frame(now) {
        const t = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - t, 3);
        const val = target * eased;
        el.textContent = prefix + val.toLocaleString('en-US', {
          minimumFractionDigits: decimals, maximumFractionDigits: decimals
        }) + suffix;
        if (t < 1) requestAnimationFrame(frame);
        else el.textContent = prefix + target.toLocaleString('en-US', {
          minimumFractionDigits: decimals, maximumFractionDigits: decimals
        }) + suffix;
      }
      requestAnimationFrame(frame);
    });
  }

  /* ---- Reveal on scroll (staggered) ---- */
  function initReveal() {
    const els = document.querySelectorAll('.reveal');
    if (reduce || !('IntersectionObserver' in window)) {
      els.forEach(el => el.classList.add('is-visible'));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          const el = e.target;
          const delay = parseFloat(el.dataset.delay || '0');
          setTimeout(() => el.classList.add('is-visible'), delay * 1000);
          io.unobserve(el);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
    els.forEach(el => io.observe(el));
  }

  /* ---- Sparklines (draw-in) ---- */
  function initSparklines() {
    document.querySelectorAll('.spark[data-values]').forEach(svg => {
      const values = svg.dataset.values.split(',').map(Number);
      const color = svg.dataset.color || 'var(--c-ink)';
      const w = 100, h = 34, pad = 3;
      const min = Math.min(...values), max = Math.max(...values);
      const range = (max - min) || 1;
      const pts = values.map((v, i) => {
        const x = pad + (i / (values.length - 1)) * (w - pad * 2);
        const y = h - pad - ((v - min) / range) * (h - pad * 2);
        return [x, y];
      });
      const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
      const area = line + ` L ${pts[pts.length-1][0].toFixed(1)} ${h} L ${pts[0][0].toFixed(1)} ${h} Z`;
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
      svg.setAttribute('preserveAspectRatio', 'none');
      svg.innerHTML =
        `<path class="area" d="${area}" fill="${color}"></path>` +
        `<path class="line" d="${line}" stroke="${color}"></path>`;
      const path = svg.querySelector('.line');
      if (!reduce && path.getTotalLength) {
        const len = path.getTotalLength();
        path.style.strokeDasharray = len;
        path.style.strokeDashoffset = len;
        path.getBoundingClientRect();
        path.style.transition = 'stroke-dashoffset 1.3s cubic-bezier(.16,1,.3,1)';
        requestAnimationFrame(() => { path.style.strokeDashoffset = '0'; });
      }
    });
  }

  /* ---- Chart.js shared theme ---- */
  window.FT = window.FT || {};
  window.FT.theme = function () {
    if (!window.Chart) return;
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue('--c-ink').trim();
    Chart.defaults.font.family = "'Hanken Grotesk', sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css.getPropertyValue('--muted').trim();
    Chart.defaults.animation = reduce ? false : { duration: 1000, easing: 'easeOutQuart' };
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip = Object.assign(Chart.defaults.plugins.tooltip || {}, {
      backgroundColor: ink,
      titleColor: '#fff', bodyColor: '#e8e6e1',
      padding: 11, cornerRadius: 9, displayColors: true, boxPadding: 4,
      titleFont: { weight: '600' },
    });
  };
  window.FT.colors = function () {
    const css = getComputedStyle(document.documentElement);
    return {
      ink:   css.getPropertyValue('--c-ink').trim(),
      slate: css.getPropertyValue('--c-slate').trim(),
      green: css.getPropertyValue('--c-green').trim(),
      clay:  css.getPropertyValue('--c-clay').trim(),
      amber: css.getPropertyValue('--c-amber').trim(),
      grid:  css.getPropertyValue('--border').trim(),
    };
  };
  window.FT.reduce = reduce;
})();
