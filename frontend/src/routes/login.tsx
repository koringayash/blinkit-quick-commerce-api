import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Log in — QuickKart" },
      { name: "description", content: "Log in to order groceries in minutes." },
      { property: "og:title", content: "Log in — QuickKart" },
      { property: "og:description", content: "Log in to order groceries in minutes." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submitLogin = async (uEmail: string, uPass: string) => {
    setBusy(true);
    try {
      const r = await api<{ access_token: string }>("/auth/login", {
        method: "POST",
        form: { username: uEmail, password: uPass },
      });
      login(r.access_token);
      navigate({ to: "/" });
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto mt-10 max-w-sm rounded-2xl border bg-card p-8 shadow-card">
      <h1 className="text-2xl font-extrabold">Welcome back</h1>
      <p className="mt-1 text-sm text-muted-foreground">Log in to start shopping.</p>
      <form
        className="mt-6 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submitLogin(email, password);
        }}
      >
        <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="pw">Password</Label><Input id="pw" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <Button type="submit" className="w-full font-bold" disabled={busy}>Log in</Button>
      </form>
      <div className="mt-4 border-t pt-4">
        <p className="mb-2 text-center text-xs font-semibold uppercase text-muted-foreground">Quick demo login</p>
        <div className="grid grid-cols-2 gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => {
              setEmail("demo@quickkart.com");
              setPassword("demo1234");
              void submitLogin("demo@quickkart.com", "demo1234");
            }}
          >
            Customer Demo
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => {
              setEmail("admin@quickkart.com");
              setPassword("admin1234");
              void submitLogin("admin@quickkart.com", "admin1234");
            }}
          >
            Admin Demo
          </Button>
        </div>
      </div>
      <p className="mt-4 text-center text-sm">New here? <Link to="/register" className="font-bold text-success">Create an account</Link></p>
    </div>
  );
}
