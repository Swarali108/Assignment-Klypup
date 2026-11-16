// "Copy brief": copies data.text to the clipboard and tells Python whether it worked,
// so Python can show a toast. Falls back to a hidden textarea where the clipboard API
// is blocked. The text is set with textContent/value only, never as HTML.

export default function ({ data, parentElement, setTriggerValue }) {
  parentElement.querySelectorAll("button").forEach((node) => node.remove());
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy";
  button.textContent = "Copy brief";
  button.setAttribute("aria-label", "Copy the brief to the clipboard");
  button.addEventListener("click", async () => {
    const text = (data && data.text) || "";
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (error) {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.cssText = "position:fixed;opacity:0;pointer-events:none";
      document.body.append(area);
      area.select();
      ok = document.execCommand("copy");
      area.remove();
    }
    setTriggerValue("copied", ok ? "ok" : "failed");
  });
  parentElement.append(button);
}
