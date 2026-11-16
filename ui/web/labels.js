// Accessible names for icon-only buttons Streamlit draws without one (the bell, the profile menu).
// data.labels: [{selector, label}]. A MutationObserver re-applies them after Streamlit redraws,
// and only one observer exists per tab.

export default function ({ data }) {
  window.__aureliaLabels = (data && data.labels) || [];
  const apply = () => {
    for (const { selector, label } of window.__aureliaLabels) {
      document.querySelectorAll(selector).forEach((node) => {
        if (node.getAttribute("aria-label") !== label) node.setAttribute("aria-label", label);
      });
    }
  };
  apply();
  if (!window.__aureliaLabelObserver) {
    window.__aureliaLabelObserver = new MutationObserver(apply);
    window.__aureliaLabelObserver.observe(document.body, { childList: true, subtree: true });
  }
}
