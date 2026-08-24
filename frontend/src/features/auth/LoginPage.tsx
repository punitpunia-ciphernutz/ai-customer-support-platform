import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "./AuthContext";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

type Form = z.infer<typeof schema>;

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { email: "agent@example.com", password: "agent123!" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await login(values.email, values.password);
      navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    }
  });

  return (
    <div className="login-page">
      <div className="login-card">
        <p className="brand">Support Platform</p>
        <h1>Sign in</h1>
        <p className="muted">Agent access to the shared inbox</p>
        <form onSubmit={onSubmit}>
          <label>
            Email
            <input type="email" {...register("email")} />
          </label>
          <label>
            Password
            <input type="password" {...register("password")} />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
      <style>{`
        .login-page {
          min-height: 100%;
          display: grid;
          place-items: center;
          padding: 2rem;
        }
        .login-card {
          width: min(420px, 100%);
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 2rem;
        }
        .brand {
          font-family: var(--font-display);
          font-size: 1.75rem;
          margin: 0 0 0.5rem;
          color: var(--accent);
        }
        .login-card h1 { margin: 0 0 0.25rem; font-size: 1.35rem; }
        .muted { color: var(--text-muted); margin: 0 0 1.5rem; }
        form { display: grid; gap: 1rem; }
        label { display: grid; gap: 0.35rem; font-size: 0.9rem; color: var(--text-muted); }
        input {
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 0.7rem 0.85rem;
          color: var(--text);
        }
        button {
          background: var(--accent);
          color: #06140f;
          border: none;
          border-radius: 8px;
          padding: 0.75rem;
          font-weight: 600;
          cursor: pointer;
        }
        button:hover { background: var(--accent-hover); }
        .error { color: var(--danger); margin: 0; }
      `}</style>
    </div>
  );
}
