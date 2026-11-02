import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Bike, MapPin, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, inr, settings, type Order, type Payment, type PaymentInit, type Tracking } from "@/lib/api";
import { DELIVERY_STEPS, label } from "@/lib/status";
import { useSession } from "@/lib/session";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";

export const Route = createFileRoute("/orders/$id")({
  head: () => ({
    meta: [
      { title: "Order details — QuickKart" },
      { name: "description", content: "Track your delivery and manage payment." },
      { property: "og:title", content: "Order details — QuickKart" },
      { property: "og:description", content: "Track your delivery live." },
    ],
  }),
  component: OrderPage,
});

function OrderPage() {
  const { id } = Route.useParams();
  const { token, ready } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [sseConnected, setSseConnected] = useState(false);

  const order = useQuery({
    queryKey: ["order", id, token],
    queryFn: () => api<Order>(`/me/orders/${id}`),
    enabled: !!token,
    refetchInterval: (q) => (q.state.data?.status === "DELIVERED" || q.state.data?.status === "CANCELLED" ? false : 3000),
  });
  const payments = useQuery({ queryKey: ["payments", id, token], queryFn: () => api<Payment[]>(`/me/orders/${id}/payments`), enabled: !!token });
  const o = order.data;
  const dispatched = !!o && !["PENDING_PAYMENT", "PLACED", "CANCELLED", "EXPIRED"].includes(o.status);

  const tracking = useQuery({
    queryKey: ["tracking", id],
    queryFn: () => api<Tracking>(`/me/orders/${id}/tracking`),
    enabled: !!token && dispatched,
    // Poll as fallback only if SSE is not active
    refetchInterval: (q) => (q.state.data?.status === "DELIVERED" || sseConnected ? false : 2500),
    retry: false,
  });

  // Live 1-Hz Server-Sent Events (SSE) stream from /me/orders/{id}/tracking/stream
  useEffect(() => {
    if (!token || !dispatched || o?.status === "DELIVERED" || typeof EventSource === "undefined") {
      setSseConnected(false);
      return;
    }
    const url = `${settings.getBase()}/me/orders/${encodeURIComponent(id)}/tracking/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);

    const onTracking = (ev: MessageEvent) => {
      try {
        const snapshot = JSON.parse(ev.data) as Tracking;
        setSseConnected(true);
        qc.setQueryData(["tracking", id], snapshot);
        if (snapshot.status === "DELIVERED") {
          qc.invalidateQueries({ queryKey: ["order", id] });
          qc.invalidateQueries({ queryKey: ["orders"] });
        }
      } catch {
        /* ignore malformed event */
      }
    };

    const onComplete = () => {
      setSseConnected(false);
      es.close();
      qc.invalidateQueries({ queryKey: ["order", id] });
      qc.invalidateQueries({ queryKey: ["orders"] });
    };

    es.addEventListener("tracking", onTracking as EventListener);
    es.addEventListener("complete", onComplete as EventListener);
    es.onerror = () => {
      setSseConnected(false);
    };

    return () => {
      setSseConnected(false);
      es.close();
    };
  }, [id, token, dispatched, o?.status, qc]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["order", id] });
    qc.invalidateQueries({ queryKey: ["payments", id] });
    qc.invalidateQueries({ queryKey: ["tracking", id] });
    qc.invalidateQueries({ queryKey: ["orders"] });
  };
  const onErr = (e: Error) => toast.error(e.message);
  const pending = payments.data?.find((p) => p.status === "PENDING");

  const pay = useMutation({
    mutationFn: (m: string) => api<PaymentInit>(`/me/orders/${id}/payments`, { method: "POST", body: { payment_method: m } }),
    onSuccess: (r) => { toast.success(r.message); refresh(); }, onError: onErr,
  });
  const simulate = useMutation({
    mutationFn: ({ pid, ok }: { pid: number; ok: boolean }) =>
      api<Payment>(`/me/orders/${id}/payments/${pid}/simulate-${ok ? "success" : "failure"}`, { method: "POST" }),
    onSuccess: (p) => { toast[p.status === "SUCCESS" ? "success" : "error"](p.status === "SUCCESS" ? "Payment successful" : p.error_reason ?? "Payment failed"); refresh(); }, onError: onErr,
  });
  const cancel = useMutation({ mutationFn: () => api<Order>(`/me/orders/${id}/cancel`, { method: "POST" }), onSuccess: () => { toast.success("Order cancelled"); refresh(); }, onError: onErr });
  const reorder = useMutation({
    mutationFn: () => api<{ message: string }>(`/me/orders/${id}/reorder`, { method: "POST" }),
    onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ["cart"] }); navigate({ to: "/cart" }); }, onError: onErr,
  });

  if (!ready) return null;
  if (!token || order.error) return <ErrorBox error={order.error ?? Object.assign(new Error(""), { status: 401 })} />;
  if (!o) return <GridSkeleton n={2} />;

  const t = tracking.data;
  const stepIdx = t ? DELIVERY_STEPS.indexOf(t.status) : -1;

  return (
    <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-6">
        <div className="rounded-2xl bg-primary p-6">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Order #{o.id}{o.store_code ? ` · ${o.store_code}` : ""}</p>
            {sseConnected && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-success px-2.5 py-0.5 text-xs font-bold text-success-foreground">
                <Radio className="h-3 w-3 animate-pulse" /> 1-Hz Live GPS
              </span>
            )}
          </div>
          <h1 className="mt-1 text-3xl font-extrabold">
            {t ? (t.status === "DELIVERED" ? "Delivered 🎉" : `Arriving in ${t.eta_minutes} min`) : label(o.status)}
          </h1>
          {o.store_name && <p className="mt-1 text-sm">Fulfilled by {o.store_name}</p>}
        </div>

        {t && (
          <div className="rounded-2xl border bg-card p-5">
            <ol className="space-y-3">
              {DELIVERY_STEPS.map((s, i) => (
                <li key={s} className="flex items-center gap-3">
                  <span className={`flex h-7 w-7 items-center justify-center rounded-full ${i <= stepIdx ? "bg-success text-success-foreground" : "bg-muted text-muted-foreground"}`}>
                    {i <= stepIdx ? <Check className="h-4 w-4" /> : i + 1}
                  </span>
                  <span className={i <= stepIdx ? "font-bold" : "text-muted-foreground"}>{label(s)}</span>
                </li>
              ))}
            </ol>
            <div className="mt-5 flex items-center gap-3 rounded-xl bg-secondary p-4 text-secondary-foreground">
              <Bike className="h-8 w-8 shrink-0" />
              <div className="text-sm">
                <p className="font-bold">{t.rider.name} · {t.rider.vehicle_type}</p>
                <p>{t.rider.phone} · {t.partner_name}</p>
              </div>
            </div>
            <div className="mt-4 grid gap-2 rounded-xl border bg-muted/40 p-3 text-xs">
              <div className="flex items-start gap-2">
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                <div>
                  <span className="font-bold">Pickup:</span> {t.pickup_address}
                </div>
              </div>
              <div className="flex items-start gap-2">
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                <div>
                  <span className="font-bold">Drop:</span> {t.delivery_address}
                </div>
              </div>
              <p className="text-muted-foreground">
                Live Rider GPS: ({t.current_location.latitude.toFixed(4)}, {t.current_location.longitude.toFixed(4)}) · Tracking ID {t.tracking_id} · updated {new Date(t.last_updated_at).toLocaleTimeString()}
              </p>
            </div>
          </div>
        )}

        <div className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 font-extrabold">Items</h2>
          <ul className="divide-y">
            {o.items.map((l) => (
              <li key={l.sku} className="flex justify-between py-2 text-sm">
                <span>{l.quantity} × {l.name}</span><span className="font-semibold">{inr(l.line_total)}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex justify-between border-t pt-3 font-extrabold"><span>Total</span><span>{inr(o.total)}</span></div>
        </div>
      </div>

      <aside className="space-y-4">
        <div className="rounded-2xl border bg-card p-5 text-sm">
          <h2 className="mb-2 font-extrabold">Payment</h2>
          <p>Status: <Badge variant="secondary">{o.payment_status ?? "Not started"}</Badge></p>
          {o.payment_method && <p className="mt-1">Method: {o.payment_method}</p>}
          {o.delivery_address && <p className="mt-3 text-muted-foreground">Delivering to {o.delivery_address}</p>}

          {o.status === "PENDING_PAYMENT" && (
            <div className="mt-4 space-y-2">
              {pending ? (
                <>
                  <p className="text-xs text-muted-foreground">Test payment ({pending.payment_method} via {pending.gateway_name})</p>
                  <Button className="w-full bg-success font-bold text-success-foreground hover:bg-success/90" disabled={simulate.isPending} onClick={() => simulate.mutate({ pid: pending.id, ok: true })}>Complete payment</Button>
                  <Button variant="outline" className="w-full" disabled={simulate.isPending} onClick={() => simulate.mutate({ pid: pending.id, ok: false })}>Simulate failure</Button>
                </>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {["UPI", "CARD", "WALLET", "COD"].map((m) => (
                    <Button key={m} variant="outline" size="sm" disabled={pay.isPending} onClick={() => pay.mutate(m)}>Pay {m}</Button>
                  ))}
                </div>
              )}
              <Button variant="ghost" className="w-full text-destructive" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Cancel order</Button>
            </div>
          )}
        </div>
        <Button variant="outline" className="w-full font-bold" disabled={reorder.isPending} onClick={() => reorder.mutate()}>Order again</Button>
      </aside>
    </div>
  );
}
