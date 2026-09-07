import { createRoot } from "react-dom/client";
import { WidgetFrameApp } from "@/widget/WidgetFrameApp";
import "@/widget/widget.css";

/* Shared MessageBubble / AI indicator classes (scoped overrides live in widget.css) */
import "@/styles.css";

document.documentElement.setAttribute("data-theme", "light");
document.documentElement.style.colorScheme = "light";

createRoot(document.getElementById("root")!).render(<WidgetFrameApp />);
