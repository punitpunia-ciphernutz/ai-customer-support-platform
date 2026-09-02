import { Link, useLocation } from "react-router-dom";
import { cn } from "@/utils/cn";

const LINKS = [
  { to: "/settings", label: "AI Support", exact: true },
  { to: "/settings/business-hours", label: "Business Hours" },
  { to: "/settings/channels", label: "Channels" },
];

export function SettingsSubNav() {
  const location = useLocation();

  const isActive = (to: string, exact?: boolean) =>
    exact ? location.pathname === to : location.pathname.startsWith(to);

  return (
    <nav className="settings-subnav" aria-label="Settings sections">
      {LINKS.map(({ to, label, exact }) => (
        <Link key={to} to={to} className={cn("settings-subnav-link", isActive(to, exact) && "active")}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
