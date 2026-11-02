import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { api, inr, type Order } from "@/lib/api";
import { label } from "@/lib/status";
import { useSession } from "@/lib/session";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";

export const Route = createFileRoute("/orders/")({
  head: () => ({
    meta: [
      { title: "My orders — QuickKart" },
      { name: "description", content: "See your past and current orders." },
      { property: "og:title", content: "My orders — QuickKart" },
      { property: "og:description", content: "See your past and current orders." },
    ],
  }),
  component: OrdersPage,
});

function OrdersPage() {
  const { token, ready } = useSession();
  const q = useQuery({ queryKey: ["orders", token], queryFn: () => api<Order[]>("/me/orders", { params: { limit: 50 } }), enabled: !!token });
  if (!ready) return null;
  if (!token || q.error) return <ErrorBox error={q.error ?? Object.assign(new Error(""), { status: 401 })} />;
  if (q.isLoading) return <GridSkeleton n={3} />;
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-4 text-2xl font-extrabold">My orders</h1>
      {q.data!.length === 0 ? <p className="text-muted-foreground">No orders yet.</p> : (
        <ul className="space-y-3">
          {q.data!.map((o) => (
            <li key={o.id}>
              <Link to="/orders/$id" params={{ id: String(o.id) }} className="flex items-center justify-between rounded-xl border bg-card p-4 hover:shadow-card">
                <div>
                  <p className="font-bold">Order #{o.id}</p>
                  <p className="text-sm text-muted-foreground">{new Date(o.created_at).toLocaleString()} · {o.items.length} items</p>
                </div>
                <div className="text-right">
                  <p className="font-bold">{inr(o.total)}</p>
                  <Badge variant="secondary">{label(o.delivery_status ?? o.status)}</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
