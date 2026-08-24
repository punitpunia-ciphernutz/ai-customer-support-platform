import { Link, useLocation } from "react-router-dom";
import { ReactNode } from "react";
import { useAuth } from "@/features/auth/AuthContext";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="shell">
      <aside>
        <div className="logo">Support</div>
        <nav>
          <Link className={location.pathname === "/" ? "active" : ""} to="/">
            Inbox
          </Link>
          <Link
            className={location.pathname.startsWith("/customers") ? "active" : ""}
            to="/customers"
          >
            Customers
          </Link>
          <a href="/chat" target="_blank" rel="noreferrer">
            Web Chat ↗
          </a>
        </nav>
        <div className="user">
          <div>{user?.full_name}</div>
          <button type="button" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </aside>
      <main>{children}</main>
      <style>{`
        .shell {
          display: grid;
          grid-template-columns: 220px 1fr;
          height: 100%;
        }
        aside {
          background: var(--bg-elevated);
          border-right: 1px solid var(--border);
          padding: 1.25rem 1rem;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }
        .logo {
          font-family: var(--font-display);
          font-size: 1.6rem;
          color: var(--accent);
        }
        nav { display: grid; gap: 0.35rem; flex: 1; }
        nav a {
          text-decoration: none;
          color: var(--text-muted);
          padding: 0.55rem 0.75rem;
          border-radius: 8px;
        }
        nav a.active, nav a:hover {
          background: var(--bg-panel);
          color: var(--text);
        }
        .user { font-size: 0.85rem; color: var(--text-muted); display: grid; gap: 0.5rem; }
        .user button {
          background: transparent;
          border: 1px solid var(--border);
          color: var(--text-muted);
          border-radius: 8px;
          padding: 0.4rem;
          cursor: pointer;
        }
        main { min-width: 0; height: 100%; overflow: hidden; }
        @media (max-width: 800px) {
          .shell { grid-template-columns: 1fr; }
          aside { flex-direction: row; align-items: center; border-right: none; border-bottom: 1px solid var(--border); }
          nav { display: flex; flex: 1; }
        }
      `}</style>
    </div>
  );
}
