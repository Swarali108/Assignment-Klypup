// Ctrl+K search over the companies, events and people in outputs/. Runs in the browser,
// so results update on every key press without a Streamlit rerun. Picking a result sends
// {page, event, person} back to Python as the "pick" trigger.
//
// Every value from a document is written with textContent, never innerHTML, so a name
// or role can never become markup.

const GROUPS = [
  ["action", "Actions"],
  ["company", "Companies"],
  ["event", "Events"],
  ["person", "People"],
  ["entity", "Entities"],
];
const PER_GROUP = 6;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function matches(item, words) {
  const hay = `${item.label} ${item.sub}`.toLowerCase();
  return words.every((word) => hay.includes(word));
}

export default function ({ data, parentElement, setTriggerValue }) {
  const index = (data && data.index) || [];
  parentElement.querySelectorAll(".finsight-search").forEach((node) => node.remove());
  const root = el("div", "finsight-search");

  const trigger = el("button", "trigger");
  trigger.type = "button";
  trigger.setAttribute("aria-label", "Search companies, people and events (Ctrl+K)");
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.append(el("span", "icon", "⌕"), el("span", "placeholder", "Search company, person, event…"));
  const keys = el("span", "keys");
  keys.append(el("kbd", "", "Ctrl"), el("kbd", "", "K"));
  trigger.append(keys);

  const overlay = el("div", "overlay");
  overlay.hidden = true;
  const panel = el("div", "panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "Search");
  const input = el("input", "query");
  input.type = "search";
  input.placeholder = "Search company, person, event…";
  input.setAttribute("aria-label", "Search query");
  input.setAttribute("aria-controls", "finsight-results");
  const list = el("div", "results");
  list.id = "finsight-results";
  list.setAttribute("role", "listbox");
  const foot = el("div", "foot", "↑ ↓ to move · Enter to open · Esc to close");
  panel.append(input, list, foot);
  overlay.append(panel);
  root.append(trigger, overlay);
  parentElement.append(root);

  let shown = [];
  let active = 0;

  const render = () => {
    list.replaceChildren();
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    shown = [];
    if (!words.length) {
      list.append(el("div", "empty", `Type a company, person or event. ${index.length} items from the processed events.`));
      const actions = index.filter((item) => item.kind === "action");
      if (actions.length) list.append(el("div", "group", "Actions"));
      for (const item of actions) {
        const option = el("button", "option");
        option.type = "button";
        option.setAttribute("role", "option");
        option.append(el("span", "label", item.label), el("span", "sub", item.sub));
        const position = shown.length;
        option.addEventListener("click", () => pick(position));
        list.append(option);
        shown.push({ item, option });
      }
      setActive(0);
      return;
    }
    for (const [kind, title] of GROUPS) {
      const hits = index.filter((item) => item.kind === kind && matches(item, words)).slice(0, PER_GROUP);
      if (!hits.length) continue;
      list.append(el("div", "group", title));
      for (const item of hits) {
        const option = el("button", "option");
        option.type = "button";
        option.setAttribute("role", "option");
        option.append(el("span", "label", item.label), el("span", "sub", item.sub));
        const position = shown.length;
        option.addEventListener("click", () => pick(position));
        option.addEventListener("mousemove", () => setActive(position));
        list.append(option);
        shown.push({ item, option });
      }
    }
    if (!shown.length) list.append(el("div", "empty", "No matches in the processed events."));
    setActive(0);
  };

  const setActive = (position) => {
    active = position;
    shown.forEach(({ option }, i) => option.setAttribute("aria-selected", String(i === active)));
    if (shown[active]) shown[active].option.scrollIntoView({ block: "nearest" });
  };

  const open = () => {
    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add("open"));
    input.value = "";
    render();
    input.focus();
  };
  const close = () => {
    overlay.classList.remove("open");
    overlay.hidden = true;
    trigger.focus();
  };
  const pick = (position) => {
    const chosen = shown[position];
    if (!chosen) return;
    close();
    setTriggerValue("pick", chosen.item.target);
  };

  trigger.addEventListener("click", open);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  input.addEventListener("input", render);
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(Math.min(active + 1, shown.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(Math.max(active - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      pick(active);
    }
  });

  // One document-level shortcut handler, replaced on each rerun so it never doubles.
  if (window.__finsightSearchKeys) document.removeEventListener("keydown", window.__finsightSearchKeys);
  window.__finsightSearchKeys = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (overlay.hidden) open();
      else close();
    } else if (event.key === "Escape" && !overlay.hidden) {
      close();
    }
  };
  document.addEventListener("keydown", window.__finsightSearchKeys);
}
