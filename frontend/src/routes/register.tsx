import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/register")({
  head: () => ({
    meta: [
      { title: "Create account — QuickKart" },
      { name: "description", content: "Sign up to get groceries delivered in minutes." },
      { property: "og:title", content: "Create account — QuickKart" },
      { property: "og:description", content: "Sign up to get groceries delivered in minutes." },
    ],
  }),
  component: RegisterPage,
});

function RegisterPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const [f, setF] = useState({ full_name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);

  return (
    <div className="mx-auto mt-10 max-w-sm rounded-2xl border bg-card p-8 shadow-card">
      <h1 className="text-2xl font-extrabold">Create your account</h1>
      <form
        className="mt-6 space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          if (f.password.length < 8) { toast.error("Password must be at least 8 characters"); return; }
          setBusy(true);
          try {
            await api("/auth/register", { method: "POST", body: f });
            const r = await api<{ access_token: string }>("/auth/login", { method: "POST", form: { username: f.email, password: f.password } });
            login(r.access_token);
            toast.success("Account created");
            navigate({ to: "/" });
          } catch (err) {
            toast.error((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="space-y-1.5"><Label htmlFor="n">Full name</Label><Input id="n" required value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></div>
        <div className="space-y-1.5"><Label htmlFor="e">Email</Label><Input id="e" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="space-y-1.5"><Label htmlFor="p">Password</Label><Input id="p" type="password" required minLength={8} maxLength={72} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
        <Button type="submit" className="w-full font-bold" disabled={busy}>Sign up</Button>
      </form>
      <p className="mt-4 text-center text-sm">Have an account? <Link to="/login" className="font-bold text-success">Log in</Link></p>
    </div>
  );
}
