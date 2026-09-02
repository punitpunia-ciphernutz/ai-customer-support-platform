import { Link, useLocation } from "react-router-dom";
import { ReactNode } from "react";
import { useAuth } from "@/features/auth/AuthContext";
import {
  IconBook,
  IconExternal,
  IconInbox,
  IconLogout,
  IconAutomation,
  IconSettings,
  IconSupport,
  IconTeam,
  IconTicket,
  IconUsers,
} from "@/components/ui/icons";
import { Avatar } from "@/components/ui";
import { cn } from "@/utils/cn";

const NAV = [
  { to: "/", label: "Inbox", icon: IconInbox, exact: true },
  { to: "/customers", label: "Customers", icon: IconUsers },
  { to: "/knowledge", label: "Knowledge", icon: IconBook },
  { to: "/tickets", label: "Tickets", icon: IconTicket },
  { to: "/teams", label: "Teams", icon: IconTeam },
  { to: "/automations", label: "Automations", icon: IconAutomation },
  { to: "/settings", label: "Settings", icon: IconSettings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  const isActive = (to: string, exact?: boolean) =>
    exact ? location.pathname === to : location.pathname.startsWith(to);

  return (
    <div className="shell">
      <aside className="shell-sidebar">
        <div className="sidebar-brand">
          <IconSupport size={22} />
          Support
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, label, icon: Icon, exact }) => (
            <Link
              key={to}
              to={to}
              className={cn("sidebar-link", isActive(to, exact) && "active")}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
          <a href="/chat" target="_blank" rel="noreferrer" className="sidebar-link">
            <IconExternal size={18} />
            Web Chat
          </a>
        </nav>

        <div className="sidebar-footer">
          {user && (
            <div className="sidebar-user">
              <Avatar name={user.full_name} size="sm" />
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">{user.full_name}</div>
                <div className="sidebar-user-email">{user.email}</div>
              </div>
            </div>
          )}
          <button type="button" className="sidebar-link" onClick={() => void logout()}>
            <IconLogout size={18} />
            Log out
          </button>
        </div>
      </aside>
      <main className="shell-main">{children}</main>
    </div>
  );
}
