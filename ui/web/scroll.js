// Scroll to one card after a chart click. data.selector names the card's container;
// data.token changes per click, so a rerun for any other reason does not scroll again.
// Smooth unless the visitor prefers reduced motion.

export default function ({ data }) {
  if (!data || !data.selector || window.__aureliaScrollToken === data.token) return;
  window.__aureliaScrollToken = data.token;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let tries = 0;
  const go = () => {
    const target = document.querySelector(data.selector);
    if (target) target.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
    else if (tries++ < 30) window.setTimeout(go, 100);
  };
  go();
}
