import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "./AuthContext";
import { IconSupport } from "@/components/ui/icons";

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
        <div className="login-brand">
          <IconSupport size={24} />
          Support Platform
        </div>
        <h1 className="page-title" style={{ fontSize: "1.25rem", marginBottom: "0.25rem" }}>
          Sign in
        </h1>
        <p className="page-desc" style={{ marginBottom: "1.5rem" }}>
          Agent access to the shared inbox
        </p>
        <form onSubmit={onSubmit} style={{ display: "grid", gap: "1rem" }}>
          <div className="form-field">
            <label className="form-label" htmlFor="email">Email</label>
            <input id="email" type="email" className="form-input" {...register("email")} />
          </div>
          <div className="form-field">
            <label className="form-label" htmlFor="password">Password</label>
            <input id="password" type="password" className="form-input" {...register("password")} />
          </div>
          {error && <div className="alert alert-error">{error}</div>}
          <button type="submit" className="btn btn-primary" disabled={isSubmitting} style={{ width: "100%" }}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
