import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api/client";
import type { Customer } from "@/types";

const schema = z.object({
  name: z.string().min(1),
  email: z.string().email().optional().or(z.literal("")),
  phone: z.string().optional(),
  company_name: z.string().optional(),
});

type Form = z.infer<typeof schema>;

export function CustomersPage() {
  const qc = useQueryClient();
  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => api<Customer[]>("/customers"),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const create = useMutation({
    mutationFn: (body: Form) =>
      api<Customer>("/customers", {
        method: "POST",
        body: JSON.stringify({
          name: body.name,
          email: body.email || null,
          phone: body.phone || null,
          company_name: body.company_name || null,
        }),
      }),
    onSuccess: () => {
      reset();
      void qc.invalidateQueries({ queryKey: ["customers"] });
    },
  });

  return (
    <div className="page">
      <h1>Customers</h1>
      <form
        className="create"
        onSubmit={handleSubmit((v) => create.mutate(v))}
      >
        <input placeholder="Name" {...register("name")} />
        <input placeholder="Email" {...register("email")} />
        <input placeholder="Phone" {...register("phone")} />
        <input placeholder="Company" {...register("company_name")} />
        <button type="submit" disabled={isSubmitting}>
          Create
        </button>
      </form>
      <ul>
        {customers.data?.map((c) => (
          <li key={c.id}>
            <strong>{c.name}</strong>
            <span>{c.email ?? "—"}</span>
            <code title="Use this ID in Web Chat">{c.id}</code>
          </li>
        ))}
      </ul>
      <style>{`
        .page { padding: 1.5rem; overflow: auto; height: 100%; }
        h1 { margin-top: 0; font-family: var(--font-display); font-weight: 400; }
        .create {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 0.5rem; margin-bottom: 1.5rem;
        }
        input, button {
          background: var(--bg-elevated); border: 1px solid var(--border); color: var(--text);
          border-radius: 8px; padding: 0.6rem 0.75rem;
        }
        button { background: var(--accent); color: #06140f; border: none; font-weight: 600; cursor: pointer; }
        ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.5rem; }
        li {
          display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 0.75rem;
          background: var(--bg-elevated); border: 1px solid var(--border);
          border-radius: 10px; padding: 0.85rem 1rem; align-items: center;
        }
        code { font-size: 0.75rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; }
      `}</style>
    </div>
  );
}
