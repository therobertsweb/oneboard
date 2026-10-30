/* ONEBoard visual picker: runs inside the sandboxed site preview iframe.
 * The parent Studio tab toggles it via postMessage and receives the selection
 * the same way. One-shot: it deactivates after each pick. */
(() => {
  "use strict";
  const script = document.getElementById("oneboard-picker");
  if (!script || window.top === window.self) return;

  const hint = script.dataset.hint || "Click an element";
  const page = script.dataset.page || "";
  let active = false;
  let hovered = null;

  const style = document.createElement("style");
  style.textContent =
    ".oneboard-pick-hover{outline:2px solid #0d6efd !important;outline-offset:2px;cursor:crosshair !important}" +
    ".oneboard-picking,.oneboard-picking *{cursor:crosshair !important}";
  (document.head || document.documentElement).appendChild(style);

  const badge = document.createElement("div");
  badge.textContent = hint;
  badge.setAttribute(
    "style",
    "position:fixed;left:12px;bottom:12px;z-index:2147483647;display:none;" +
      "background:#0d6efd;color:#fff;font:12px/1.4 system-ui,sans-serif;" +
      "padding:6px 10px;border-radius:6px;pointer-events:none;"
  );
  document.documentElement.appendChild(badge);

  function setActive(value) {
    active = !!value;
    script.dataset.active = active ? "1" : "0";
    badge.style.display = active ? "block" : "none";
    document.documentElement.classList.toggle("oneboard-picking", active);
    if (!active && hovered) {
      hovered.classList.remove("oneboard-pick-hover");
      hovered = null;
    }
  }

  function selectorFor(element) {
    if (element.id) return `#${CSS.escape(element.id)}`;
    const parts = [];
    let node = element;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 8) {
      let name = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          (child) => child.tagName === node.tagName
        );
        if (siblings.length > 1) {
          name += `:nth-of-type(${siblings.indexOf(node) + 1})`;
        }
      }
      parts.unshift(name);
      node = parent;
    }
    parts.unshift("body");
    return parts.join(" > ");
  }

  function visibleText(element) {
    const text = (element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
    return text.slice(0, 500);
  }

  document.addEventListener(
    "mouseover",
    (event) => {
      if (!active) return;
      const target = event.target;
      if (!(target instanceof Element) || target === badge) return;
      if (hovered && hovered !== target) hovered.classList.remove("oneboard-pick-hover");
      hovered = target;
      hovered.classList.add("oneboard-pick-hover");
    },
    true
  );

  document.addEventListener(
    "mouseout",
    (event) => {
      if (!active) return;
      const target = event.target;
      if (target instanceof Element && target !== badge) {
        target.classList.remove("oneboard-pick-hover");
      }
      if (hovered === target) hovered = null;
    },
    true
  );

  document.addEventListener(
    "click",
    (event) => {
      if (!active) return;
      event.preventDefault();
      event.stopPropagation();
      const target = event.target;
      if (!(target instanceof Element)) return;
      const selection = {
        page,
        selector: selectorFor(target),
        tag: target.tagName.toLowerCase(),
        text: visibleText(target),
        html: target.outerHTML.slice(0, 2000),
        image_src:
          target.tagName === "IMG" ? (target.getAttribute("src") || "").slice(0, 500) : "",
      };
      window.parent.postMessage({ type: "oneboard-selection", selection }, "*");
      setActive(false);
    },
    true
  );

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || event.origin !== window.location.origin) return;
    const data = event.data || {};
    if (data.type === "oneboard-picker-toggle") setActive(data.active);
  });
})();
