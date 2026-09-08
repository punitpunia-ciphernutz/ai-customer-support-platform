import { Link, useLocation } from "react-router-dom";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/AuthContext";
import { useTheme } from "@/app/ThemeContext";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import {
  IconBook,
  IconChevronLeft,
  IconChevronRight,
  IconExternal,
  IconInbox,
  IconLogout,
  IconAutomation,
  IconMoon,
  IconSettings,
  IconSun,
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

const SIDEBAR_COLLAPSED_KEY = "sidebar_collapsed";

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const location = useLocation();
  const [profileOpen, setProfileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readSidebarCollapsed);
  const profileRef = useRef<HTMLDivElement>(null);

  const isActive = (to: string, exact?: boolean) =>
    exact ? location.pathname === to : location.pathname.startsWith(to);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  useEffect(() => {
    if (!profileOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setProfileOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [profileOpen]);

  return (
    <div className={cn("shell", collapsed && "is-sidebar-collapsed")}>
      <aside className={cn("shell-sidebar", collapsed && "is-collapsed")} aria-label="Primary">
        <div className="sidebar-brand-row">
          <div className="sidebar-brand">
            <IconSupport size={22} />
            <span className="sidebar-brand-text">Support</span>
          </div>
          <button
            type="button"
            className="sidebar-collapse-btn"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={toggleCollapsed}
          >
            {collapsed ? <IconChevronRight size={16} /> : <IconChevronLeft size={16} />}
          </button>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, label, icon: Icon, exact }) => (
            <Link
              key={to}
              to={to}
              className={cn("sidebar-link", isActive(to, exact) && "active")}
              aria-label={label}
            >
              <Icon size={18} />
              <span className="sidebar-link-label">{label}</span>
            </Link>
          ))}
          <a
            href="/chat"
            target="_blank"
            rel="noreferrer"
            className="sidebar-link"
            aria-label="Internal Web Chat (test)"
          >
            <IconExternal size={18} />
            <span className="sidebar-link-label">Internal Web Chat (test)</span>
          </a>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footer-bar">
            {user && (
              <div className="sidebar-profile" ref={profileRef}>
                <button
                  type="button"
                  className={cn("sidebar-profile-btn", profileOpen && "is-open")}
                  aria-label="Account menu"
                  aria-expanded={profileOpen}
                  aria-haspopup="menu"
                  title={collapsed ? user.full_name : undefined}
                  onClick={() => setProfileOpen((v) => !v)}
                >
                  <span className="sidebar-profile-avatar-wrap">
                    <Avatar name={user.full_name} size="sm" />
                    <span className="sidebar-profile-status" aria-hidden />
                  </span>
                </button>

                {profileOpen && (
                  <div className="sidebar-profile-menu" role="menu" aria-label="Account">
                    <div className="sidebar-profile-menu-header">
                      <div className="sidebar-user-name">{user.full_name}</div>
                      <div className="sidebar-user-email">{user.email}</div>
                    </div>
                    <div className="sidebar-theme-toggle" role="group" aria-label="Theme">
                      <button
                        type="button"
                        className={cn("sidebar-theme-option", theme === "light" && "is-active")}
                        aria-pressed={theme === "light"}
                        onClick={() => setTheme("light")}
                      >
                        <IconSun size={14} />
                        Light
                      </button>
                      <button
                        type="button"
                        className={cn("sidebar-theme-option", theme === "dark" && "is-active")}
                        aria-pressed={theme === "dark"}
                        onClick={() => setTheme("dark")}
                      >
                        <IconMoon size={14} />
                        Dark
                      </button>
                    </div>
                    <button
                      type="button"
                      className="sidebar-profile-menu-item is-danger"
                      role="menuitem"
                      onClick={() => {
                        setProfileOpen(false);
                        void logout();
                      }}
                    >
                      <IconLogout size={16} />
                      Log out
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="shell-content">
        <header className="shell-header">
          <div className="shell-header-actions">
            <NotificationBell compact placement="below" />
          </div>
        </header>
        <main className="shell-main">{children}</main>
      </div>
    </div>
  );
}
