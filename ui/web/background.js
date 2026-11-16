// The portfolio background (swarali108.github.io, src/components/ParticleField.tsx),
// ported from React to plain JS with the same constants and drawing code: a drifting
// dot network where nearby dots link up and dots ease away from the pointer. It starts
// when the browser is idle, pauses in hidden tabs, and draws one still frame when the
// user prefers reduced motion.
//
// Streamlit re-runs this function on every rerun. The canvas is created once, on
// document.body, and kept on window.__aureliaField, so it never restarts or doubles
// when the visitor changes page. data.paused (the profile menu's switch) pauses it.

const TEAL = "61, 214, 195";
const AMBER = "245, 181, 67";
const LINK_DIST = 140;
const POINTER_RADIUS = 150;

function createField() {
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.className = "aurelia-field";
  canvas.style.cssText =
    "position:fixed;inset:0;width:100%;height:100%;z-index:-1;pointer-events:none;opacity:0;transition:opacity 1s";
  document.body.prepend(canvas);
  const ctx = canvas.getContext("2d");
  if (!ctx) return { setPaused() {} };

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pointer = { x: -9999, y: -9999 };
  let w = 0;
  let h = 0;
  let dots = [];
  let frame = 0;
  let running = false;
  let paused = false;

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // Density scales with screen area: ~30 dots on a phone, capped at 80.
    const count = Math.min(80, Math.max(28, Math.round((w * h) / 16000)));
    dots = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 1.3 + 0.6,
      amber: Math.random() < 0.12,
    }));
  };

  const draw = () => {
    ctx.clearRect(0, 0, w, h);
    for (const d of dots) {
      if (!reduced && !paused) {
        const dx = d.x - pointer.x;
        const dy = d.y - pointer.y;
        const dist = Math.hypot(dx, dy);
        if (dist < POINTER_RADIUS && dist > 0) {
          const push = ((POINTER_RADIUS - dist) / POINTER_RADIUS) * 0.6;
          d.x += (dx / dist) * push;
          d.y += (dy / dist) * push;
        }
        d.x += d.vx;
        d.y += d.vy;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
      }
      ctx.beginPath();
      ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${d.amber ? AMBER : TEAL}, ${d.amber ? 0.55 : 0.45})`;
      ctx.fill();
    }
    ctx.lineWidth = 0.7;
    for (let i = 0; i < dots.length; i++) {
      for (let j = i + 1; j < dots.length; j++) {
        const a = dots[i];
        const b = dots[j];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist < LINK_DIST) {
          ctx.strokeStyle = `rgba(${TEAL}, ${0.14 * (1 - dist / LINK_DIST)})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
  };

  const loop = () => {
    draw();
    frame = requestAnimationFrame(loop);
  };
  const start = () => {
    if (running || reduced || paused) return;
    running = true;
    frame = requestAnimationFrame(loop);
  };
  const stop = () => {
    running = false;
    cancelAnimationFrame(frame);
  };

  window.addEventListener("pointermove", (e) => {
    pointer.x = e.clientX;
    pointer.y = e.clientY;
  }, { passive: true });
  document.addEventListener("pointerleave", () => {
    pointer.x = pointer.y = -9999;
  });
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      resize();
      if (reduced || paused) draw();
    }, 150);
  });

  // Defer until the page is idle so the canvas never competes with first paint.
  const begin = () => {
    resize();
    canvas.style.opacity = "1";
    if (reduced || paused) draw();
    else start();
  };
  if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(begin, { timeout: 2000 });
  else window.setTimeout(begin, 600);

  return {
    setPaused(value) {
      paused = Boolean(value);
      if (paused) stop();
      else start();
    },
  };
}

export default function ({ data }) {
  if (!window.__aureliaField) window.__aureliaField = createField();
  window.__aureliaField.setPaused(data && data.paused);
}
