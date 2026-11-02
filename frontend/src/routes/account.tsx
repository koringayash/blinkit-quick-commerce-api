import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, inr, type Address, type Favorite } from "@/lib/api";
import { useSession } from "@/lib/session";
import { AddressForm } from "@/components/AddressForm";
import { ErrorBox } from "@/components/QueryState";
import { QtyControl } from "@/components/ProductTile";

export const Route = createFileRoute("/account")({
  head: () => ({
    meta: [
      { title: "My account — QuickKart" },
      { name: "description", content: "Manage your addresses and favourite products." },
      { property: "og:title", content: "My account — QuickKart" },
      { property: "og:description", content: "Manage your addresses and favourites." },
    ],
  }),
  component: AccountPage,
});

function AccountPage() {
  const { token, ready, user } = useSession();
  const qc = useQueryClient();
  const addresses = useQuery({ queryKey: ["addresses", token], queryFn: () => api<Address[]>("/me/addresses"), enabled: !!token });
  const favs = useQuery({ queryKey: ["favorites", token], queryFn: () => api<Favorite[]>("/me/favorites"), enabled: !!token });
  const del = useMutation({
    mutationFn: (id: number) => api<void>(`/me/addresses/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["addresses"] }),
  });
  if (!ready) return null;
  if (!token) return <ErrorBox error={Object.assign(new Error(""), { status: 401 })} />;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {user && <div><h1 className="text-2xl font-extrabold">Hi, {user.full_name}</h1><p className="text-sm text-muted-foreground">{user.email}</p></div>}
      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 font-extrabold">Saved addresses</h2>
          <ul className="mb-4 space-y-2">
            {addresses.data?.map((a) => (
              <li key={a.id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                <span><span className="font-bold">{a.label}</span>{a.is_default && " (default)"} · {a.line1 ? `${a.line1}, ` : ""}{a.city} {a.pincode}</span>
                <Button variant="ghost" size="icon" aria-label="Delete address" onClick={() => del.mutate(a.id)}><Trash2 className="h-4 w-4" /></Button>
              </li>
            ))}
          </ul>
          <AddressForm />
        </section>
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 font-extrabold">Favourites</h2>
          {!favs.data?.length ? <p className="text-sm text-muted-foreground">Tap the heart on a product to save it here.</p> : (
            <ul className="divide-y">
              {favs.data.map((f) => (
                <li key={f.sku} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <Link to="/product/$sku" params={{ sku: f.sku }} className="flex-1 font-semibold hover:underline">{f.name}</Link>
                  <span>{inr(f.price)}</span>
                  <QtyControl sku={f.sku} inStock={f.available_qty > 0} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
