/**
 * Embeddable chat widget loader.
 * Usage:
 *   <script async src="https://HOST/widget.js" data-widget-id="wgt_xxx"></script>
 *
 * Appearance (position, colors, launcher text) is applied from the public widget
 * config once the iframe reports it — dashboard settings take effect without
 * re-pasting the snippet.
 */
(function () {
  var script =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      for (var i = scripts.length - 1; i >= 0; i--) {
        if (scripts[i].src && scripts[i].src.indexOf("widget.js") !== -1) return scripts[i];
      }
      return null;
    })();

  if (!script) return;

  var widgetId = script.getAttribute("data-widget-id");
  if (!widgetId) {
    console.error("[SupportWidget] missing data-widget-id");
    return;
  }

  var srcUrl = new URL(script.src);
  var origin = srcUrl.origin;
  var position = script.getAttribute("data-position") || "bottom-right";
  var primary = script.getAttribute("data-primary-color") || "#3B66F5";
  var textColor = script.getAttribute("data-text-color") || "#FFFFFF";
  var launcherText = script.getAttribute("data-launcher-text") || "Chat";
  var zIndex = 999999;

  if (document.getElementById("sp-widget-root-" + widgetId)) return;

  var root = document.createElement("div");
  root.id = "sp-widget-root-" + widgetId;
  document.body.appendChild(root);

  var open = false;
  var bubble = document.createElement("button");
  bubble.type = "button";
  bubble.setAttribute("aria-label", "Open chat");

  var panel = document.createElement("div");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Support chat");

  var iframe = document.createElement("iframe");
  iframe.title = "Support chat";
  iframe.allow = "clipboard-write";
  iframe.style.cssText = "border:0;width:100%;height:100%;display:block;background:#fff;";
  iframe.src =
    origin +
    "/widget-frame.html?widget_id=" +
    encodeURIComponent(widgetId) +
    "&page_host=" +
    encodeURIComponent(window.location.hostname);

  panel.appendChild(iframe);
  root.appendChild(panel);
  root.appendChild(bubble);

  function applyLayout() {
    var isLeft = String(position).indexOf("left") !== -1;
    root.style.cssText =
      "all:initial;position:fixed;z-index:" +
      zIndex +
      ";font-family:system-ui,-apple-system,sans-serif;" +
      "bottom:20px;" +
      (isLeft ? "left:20px;right:auto;" : "right:20px;left:auto;");

    bubble.textContent = open ? "Close" : launcherText;
    bubble.setAttribute("aria-label", open ? "Close chat" : "Open chat");
    bubble.style.cssText =
      "all:initial;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;" +
      "min-width:56px;min-height:56px;padding:0 20px;border-radius:999px;cursor:pointer;" +
      "background:" +
      primary +
      ";color:" +
      textColor +
      ";font:600 14px/1 system-ui,-apple-system,sans-serif;" +
      "box-shadow:0 10px 28px rgba(15,23,42,.22);letter-spacing:0.01em;";

    panel.style.cssText =
      "display:" +
      (open ? "block" : "none") +
      ";position:absolute;bottom:72px;width:min(400px,calc(100vw - 24px));" +
      "height:min(620px,calc(100vh - 110px));border-radius:16px;overflow:hidden;" +
      "box-shadow:0 18px 50px rgba(15,23,42,.28);background:#fff;border:1px solid rgba(15,23,42,.08);" +
      (isLeft ? "left:0;right:auto;" : "right:0;left:auto;");
  }

  function setOpen(next) {
    open = next;
    applyLayout();
    if (open) {
      iframe.contentWindow &&
        iframe.contentWindow.postMessage(
          { type: "WIDGET_INIT", host: window.location.hostname, href: window.location.href },
          origin
        );
    }
  }

  function applyAppearance(appearance) {
    if (!appearance || typeof appearance !== "object") return;
    if (appearance.launcher_position) position = appearance.launcher_position;
    if (appearance.primary_color) primary = appearance.primary_color;
    if (appearance.text_color) textColor = appearance.text_color;
    if (appearance.launcher_text) launcherText = appearance.launcher_text;
    if (appearance.z_index != null && !isNaN(Number(appearance.z_index))) {
      zIndex = Number(appearance.z_index);
    }
    applyLayout();
  }

  bubble.addEventListener("click", function () {
    setOpen(!open);
  });

  window.addEventListener("message", function (event) {
    if (event.origin !== origin) return;
    var data = event.data || {};
    if (data.widgetId && data.widgetId !== widgetId) return;
    if (data.type === "WIDGET_CLOSE") setOpen(false);
    if (data.type === "WIDGET_APPEARANCE") applyAppearance(data.appearance);
    if (data.type === "WIDGET_READY") {
      iframe.contentWindow &&
        iframe.contentWindow.postMessage(
          { type: "WIDGET_INIT", host: window.location.hostname, href: window.location.href },
          origin
        );
    }
  });

  applyLayout();
})();
