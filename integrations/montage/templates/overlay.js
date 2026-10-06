// Детерминированная анимация: render(t) задаёт состояние всех сцен как функцию времени t (секунды финального ролика).
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const prog = (t, a, d) => cl((t - a) / d);
const eo3 = x => 1 - Math.pow(1 - x, 3);
const eio = x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const eob = x => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
const $ = (el, sel) => Array.from(el.querySelectorAll(sel));

const SC = DATA.scenes;
const byId = {};
SC.forEach(s => { s.el = document.getElementById(s.id); byId[s.id] = s; });

// --- геометрия чипов (раскладка без трансформаций), считается один раз
function centerOf(el, root) {
  let x = 0, y = 0, e = el;
  while (e && e !== root) { x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; }
  return [x + el.offsetWidth / 2, y + el.offsetHeight / 2];
}
// Хук: самая широкая строка не шире безопасной полосы (кадр минус поля 64 px), иначе уменьшаем кегль
SC.forEach(s => {
  if (s.type !== 'hook') return;
  s.el.classList.add('on');
  const rows = $(s.el, '.hl');
  const box = rows[0] && rows[0].parentElement;
  if (box) {
    let w = 0;
    rows.forEach(r => {
      const a = r.firstElementChild.getBoundingClientRect(), b = r.lastElementChild.getBoundingClientRect();
      w = Math.max(w, b.right - a.left);
    });
    const avail = 1080 - 2 * 64;
    if (w > avail) {
      const f0 = parseFloat(getComputedStyle(box).fontSize), f1 = Math.floor(f0 * avail / w), k = f1 / f0;
      box.style.fontSize = f1 + 'px';
      $(s.el, '.lg').forEach(lg => {                  // объёмный логотип уменьшается вместе с текстом
        lg.style.width = (210 * k) + 'px'; lg.style.height = (170 * k) + 'px';
        if (lg.firstElementChild) lg.firstElementChild.style.zoom = k;
      });
    }
  }
  s.el.classList.remove('on');
});

SC.forEach(s => {
  if (s.type !== 'panel') return;
  s.el.classList.add('on');
  s.chips = $(s.el, '.chip').map((c, i) => ({ el: c, t: parseFloat(c.dataset.t), c: centerOf(c, s.el), idx: i }));
  s.arrows = $(s.el, '.arrow');
  s.card = s.el.querySelector('.card');
  s.cardC = centerOf(s.card, s.el);
  s.el.classList.remove('on');
});

function setT(el, tx, ty, sc, rot, op) {
  el.style.transform = `translate(${tx}px,${ty}px) scale(${sc}) rotate(${rot}deg)`;
  if (op !== undefined) el.style.opacity = op;
}

function popIn(el, l, a, d = .4, from = .5) {
  const p = prog(l, a, d), e = eob(p);
  setT(el, 0, 0, from + (1 - from) * e, 0, Math.min(1, p * 4));
}

function riseIn(el, l, a, d = .4, dy = 40) {
  const p = prog(l, a, d), e = eo3(p);
  setT(el, 0, dy * (1 - e), 1, 0, Math.min(1, p * 3));
}

// нажатие: масштаб, цвет, кольцо
function pressScale(d) {
  if (d < 0) return 1;
  if (d < .07) return 1 - .10 * (d / .07);
  if (d < .32) return .90 + .10 * eob((d - .07) / .25);
  return 1;
}

const U = {
  hook(s, t, l) {
    $(s.el, '.hl').forEach((h, i) => riseIn(h, l, .05 + i * .12, .45, 50));
    const lg = s.el.querySelector('.lg');
    const p = prog(l, .12, .6), e = eob(p);
    setT(lg, 0, -3 * Math.sin(t * 3), .15 + .85 * e, -40 * (1 - eo3(p)), Math.min(1, p * 5));
  },

  panel(s, t, l) {
    const card = s.card;
    const p = prog(l, 0, .38), e = eo3(p);
    setT(card, 0, -70 * (1 - e), .94 + .06 * e, 0, Math.min(1, p * 3));
    popIn(s.el.querySelector('.numc'), l, .12, .45, .3);
    riseIn(s.el.querySelector('.ttl'), l, .2, .4, 26);
    // прогресс
    const n = s.n;
    $(s.el, '.seg').forEach(g => {
      const i = +g.dataset.i, f = g.querySelector('.fill');
      f.style.transform = `scaleX(${i < n ? 1 : (i === n ? eo3(prog(l, .15, .55)) : 0)})`;
    });
    // чипы: появление и «нажатие» в момент слова
    let k = 0;
    s.chips.forEach((c, i) => {
      const tin = s.start + .35 + i * .11;
      const pin = prog(t, tin, .38), e2 = eob(pin);
      let sc = (.55 + .45 * e2), op = Math.min(1, pin * 4);
      let bg = '#F3EDE6', col = '#0E0D0C';
      const d = t - c.t;
      const ring = c.el.querySelector('.ring');
      if (d >= 0) {
        bg = d < .75 ? '#0E0D0C' : '#F9D8C8';
        col = d < .75 ? '#FFFFFF' : '#0E0D0C';
        sc *= pressScale(d);
        const q = cl(d / .5);
        ring.style.opacity = d < .5 ? (.85 * (1 - q)) : 0;
        ring.style.transform = `scale(${1 + .22 * eo3(q)})`;
      } else { ring.style.opacity = 0; }
      c.el.style.background = bg; c.el.style.color = col;
      setT(c.el, 0, 0, sc, 0, op);
    });
    s.arrows.forEach((a, i) => { const pa = prog(t, s.start + .4 + i * .22, .3); setT(a, 0, 0, .5 + .5 * eob(pa), 0, Math.min(1, pa * 3)); });
    // курсор
    const cur = s.el.querySelector('.cur');
    const order = s.chips.slice().sort((a, b) => a.t - b.t);
    if (order.length) {
      const first = order[0].t, last = order[order.length - 1].t;
      let x, y, sc = 1;
      // позиция: предыдущая точка -> текущая за .30 с до нажатия
      let prev = [s.cardC[0] + 330, s.cardC[1] + 260];
      let pos = prev;
      for (let i = 0; i < order.length; i++) {
        const tgt = [order[i].c[0] + 14, order[i].c[1] + 16];
        const from = i === 0 ? prev : [order[i - 1].c[0] + 14, order[i - 1].c[1] + 16];
        const a = order[i].t - .30;
        if (t >= a) { const q = eio(prog(t, a, .30)); pos = [from[0] + (tgt[0] - from[0]) * q, from[1] + (tgt[1] - from[1]) * q]; }
      }
      const dd = order.reduce((m, c) => (t >= c.t && t - c.t < .14 ? t - c.t : m), -1);
      if (dd >= 0) sc = 1 - .18 * Math.sin(Math.min(1, dd / .14) * Math.PI);
      const vis = Math.min(prog(t, first - .5, .25), 1 - prog(t, last + .65, .3));
      cur.style.opacity = cl(vis);
      cur.style.transform = `translate(${pos[0] - 8}px,${pos[1] - 4}px) scale(${sc})`;
    }
  },

  fs(s, t, l) {
    const bg = s.el.querySelector('.fsbg');
    bg.style.opacity = Math.min(1, prog(l, 0, .16) * 1.4);
  },

  phone(s, t, l) {
    U.fs(s, t, l);
    const ph = s.el.querySelector('.ph');
    const p = prog(l, .02, .5);
    setT(ph, 0, 140 * (1 - eo3(p)), 1, 0, Math.min(1, p * 3));
    riseIn(s.el.querySelector('.hd'), l, 0, .35, -30);
    popIn(s.el.querySelector('.bub'), l, .22, .35, .7);
    $(s.el, '.prow').forEach((r, i) => riseIn(r, l, .4 + i * .18, .35, 24));
  },

  week(s, t, l) {
    U.fs(s, t, l);
    riseIn(s.el.querySelector('.hd'), l, 0, .35, -30);
    $(s.el, '.wk').forEach((c, i) => popIn(c, l, .12 + i * .1, .4, .6));
    $(s.el, '.tt').forEach(tt => {
      const d = t - parseFloat(tt.dataset.t);
      const k = d >= 0 && d < .5 ? 1 + .14 * Math.sin(Math.PI * d / .5) : 1;
      tt.style.display = 'inline-block';
      tt.style.transform = `scale(${k})`;
    });
  },

  money(s, t, l) {
    U.fs(s, t, l);
    riseIn(s.el.querySelector('.hd'), l, 0, .35, -30);
    popIn(s.el.querySelector('.t1'), l, .1, .45, .5);
    popIn(s.el.querySelector('.t2'), l, .25, .45, .5);
    const line = s.el.querySelector('.line'), dot = s.el.querySelector('.dot');
    const pl = eo3(prog(l, .4, .35));
    line.style.transformOrigin = '0 50%'; line.style.transform = `scaleX(${pl})`; line.style.opacity = pl > 0 ? 1 : 0;
    const pd = eio(prog(l, .75, .6));
    dot.style.transform = `translateX(${pd * 124}px) scale(${1 + .25 * Math.sin(Math.PI * prog(l, 1.3, .3))})`; dot.style.opacity = pl > .9 ? 1 : 0;
    popIn(s.el.querySelector('.list'), l, .5, .4, .85);
    $(s.el, '.mrow').forEach((r, i) => {
      const rp = prog(l, .55 + i * .12, .3);
      r.style.opacity = Math.min(1, rp * 3);
      const tick = r.querySelector('.tick');
      const d = t - parseFloat(r.dataset.t);
      if (d >= 0) {
        tick.style.background = '#D97757';
        tick.style.transform = `scale(${d < .35 ? 1 + .35 * Math.sin(Math.PI * d / .35) : 1})`;
        r.style.background = d < .6 ? `rgba(217,119,87,${.16 * (1 - d / .6)})` : 'transparent';
      } else { tick.style.background = '#E6DFD6'; tick.style.transform = 'scale(1)'; r.style.background = 'transparent'; }
    });
  },

  pipe(s, t, l) {
    U.fs(s, t, l);
    riseIn(s.el.querySelector('.hd'), l, 0, .35, -30);
    $(s.el, '.prw').forEach((c, i) => riseIn(c, l, .12 + i * .06, .35, 36));
  },

  pill(s, t, l) {
    popIn(s.el.querySelector('.pill'), l, 0, .45, .5);
  },

  cta(s, t, l) {
    const w = s.el.querySelector('.pillwrap');
    const p = prog(l, 0, .5), e = eob(p);
    const ct1 = s.el.querySelector('.ct1'), big = s.el.querySelector('.big'), ct3 = s.el.querySelector('.ct3');
    riseIn(ct1, l, 0, .35, -24);
    const pb = prog(l, .12, .5);
    big.style.opacity = Math.min(1, pb * 4);
    const d = t - s.press;
    let sc = .4 + .6 * eob(pb);
    if (d >= 0) sc *= pressScale(d) * (d > .3 && d < .6 ? 1 : 1);
    big.style.transform = `scale(${sc})`;
    const ring = s.el.querySelector('.ring2');
    if (d >= 0 && d < .6) { const q = d / .6; ring.style.opacity = .9 * (1 - q); ring.style.transform = `scale(${1 + .3 * eo3(q)})`; } else ring.style.opacity = 0;
    riseIn(ct3, l, .3, .35, 24);
  },
};

// Своя сцена (type: custom): появление по data-a/data-d/data-dur, «нажатие» по data-t (из data-word), фон — как у остальных
U.custom = function (s, t, l) {
  const bg = s.el.querySelector('.fsbg');
  if (bg) bg.style.opacity = Math.min(1, prog(l, 0, .16) * 1.4);
  $(s.el, '[data-a],[data-t]').forEach(el => {
    let sc = 1, op = 1, ty = 0;
    const a = el.dataset.a;
    if (a) {
      const p = prog(l, parseFloat(el.dataset.d || 0), parseFloat(el.dataset.dur || .4));
      if (a === 'pop') { sc = .5 + .5 * eob(p); op = Math.min(1, p * 4); }
      else if (a === 'rise') { ty = 36 * (1 - eo3(p)); op = Math.min(1, p * 3); }
      else if (a === 'fade') { op = p; }
    }
    if (el.dataset.t !== undefined) {
      const d = t - parseFloat(el.dataset.t);
      if (d >= 0) {
        sc *= pressScale(d);
        const q = cl(d / .5);
        el.style.boxShadow = d < .5 ? `0 0 0 ${Math.round(10 * eo3(q))}px rgba(14,13,12,${(.35 * (1 - q)).toFixed(3)})` : '';
      } else el.style.boxShadow = '';
    }
    el.style.opacity = op;
    el.style.transform = `translateY(${ty}px) scale(${sc})`;
  });
};

function render(t) {
  let on = 0;
  for (const s of SC) {
    const active = t >= s.start && t < s.end;
    s.el.classList.toggle('on', active);
    if (active) { on++; U[s.type](s, t, t - s.start); }
  }
  return on;
}
window.render = render;
