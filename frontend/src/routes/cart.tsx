import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { api, inr, type Address, type Order, type PaymentInit } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { useSession } from "@/lib/session";
import { QtyControl } from "@/components/ProductTile";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";
import { AddressForm } from "@/components/AddressForm";

export const Route = createFileRoute("/cart")({
  head: () => ({
    meta: [
      { title: "Your cart — QuickKart" },
      { name: "description", content: "Review your cart, pick an address and pay." },
      { property: "og:title", content: "Your cart — QuickKart" },
      { property: "og:description", content: "Review your cart and check out." },
    ],
  }),
  component: CartPage,
});

const METHODS = [
  ["UPI", "UPI"],
  ["CARD", "Card"],
  ["WALLET", "Wallet"],
  ["COD", "Cash on delivery"],
] as const;

function CartPage() {
  const { token, ready, storeId } = useSession();
  const cart = useCart();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const addresses = useQuery({ queryKey: ["addresses", token], queryFn: () => api<Address[]>("/me/addresses"), enabled: !!token });
  const [addressId, setAddressId] = useState<string>("");
  const [method, setMethod] = useState("UPI");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (!addressId && addresses.data?.length) {
      const d = addresses.data.find((a) => a.is_default) ?? addresses.data[0];
      if (d) setAddressId(String(d.id));
    }
  }, [addresses.data, addressId]);

  const clear = useMutation({
    mutationFn: () => api<void>("/me/cart", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cart"] }),
  });

  const checkout = useMutation({
    mutationFn: async () => {
      const order = await api<Order>("/me/cart/checkout", {
        method: "POST",
        body: { address_id: Number(addressId), store_id: storeId ?? undefined },
      });
      const pay = await api<PaymentInit>(`/me/orders/${order.id}/payments`, { method: "POST", body: { payment_method: method } });
      return { order, pay };
    },
    onSuccess: ({ order, pay }) => {
      qc.invalidateQueries({ queryKey: ["cart"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
      toast.success(pay.message);
      navigate({ to: "/orders/$id", params: { id: String(order.id) } });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!ready) return null;
  if (!token) return <ErrorBox error={Object.assign(new Error(""), { status: 401, name: "ApiError" })} />;
  if (cart.isLoading) return <GridSkeleton n={4} />;
  if (cart.error) return <ErrorBox error={cart.error} />;
  const c = cart.data!;

  if (c.items.length === 0)
    return (
      <div className="py-20 text-center">
        <p className="text-6xl">🛒</p>
        <h1 className="mt-4 text-2xl font-extrabold">Your cart is empty</h1>
        <Button asChild className="mt-6 font-bold"><Link to="/">Start shopping</Link></Button>
      </div>
    );

  const blocked = c.items.some((l) => !l.in_stock);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <section className="rounded-2xl border bg-card p-5">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-2xl font-extrabold">My cart <span className="text-base text-muted-foreground">({c.item_count})</span></h1>
          <Button variant="ghost" size="sm" onClick={() => clear.mutate()}><Trash2 className="mr-1 h-4 w-4" />Clear</Button>
        </div>
        {c.store_code && <p className="mb-3 text-xs text-muted-foreground">Stock checked at store {c.store_code}</p>}
        <ul className="divide-y">
          {c.items.map((l) => (
            <li key={l.sku} className="flex items-center gap-4 py-3">
              <div className="flex-1">
                <Link to="/product/$sku" params={{ sku: l.sku }} className="font-semibold hover:underline">{l.name}</Link>
                <p className="text-sm text-muted-foreground">{inr(l.unit_price)} each</p>
                {!l.in_stock && <p className="text-xs font-semibold text-destructive">Only {l.available_qty} available — reduce quantity</p>}
              </div>
              <QtyControl sku={l.sku} inStock />
              <span className="w-20 text-right font-bold">{inr(l.line_total)}</span>
            </li>
          ))}
        </ul>
      </section>

      <aside className="space-y-4">
        <div className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 font-extrabold">Deliver to</h2>
          {addresses.data?.length ? (
            <RadioGroup value={addressId} onValueChange={setAddressId} className="space-y-2">
              {addresses.data.map((a) => (
                <Label key={a.id} className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 font-normal">
                  <RadioGroupItem value={String(a.id)} />
                  <span>
                    <span className="font-bold">{a.label}</span> · {a.line1 ? `${a.line1}, ` : ""}{a.city} {a.pincode}
                  </span>
                </Label>
              ))}
            </RadioGroup>
          ) : <p className="text-sm text-muted-foreground">No saved addresses yet.</p>}
          {adding ? (
            <div className="mt-3"><AddressForm onDone={() => setAdding(false)} /></div>
          ) : (
            <Button variant="link" className="px-0 text-success" onClick={() => setAdding(true)}>+ Add new address</Button>
          )}
        </div>

        <div className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 font-extrabold">Pay with</h2>
          <RadioGroup value={method} onValueChange={setMethod} className="grid grid-cols-2 gap-2">
            {METHODS.map(([v, l]) => (
              <Label key={v} className="flex cursor-pointer items-center gap-2 rounded-lg border p-3 font-semibold">
                <RadioGroupItem value={v} />{l}
              </Label>
            ))}
          </RadioGroup>
        </div>

        <div className="rounded-2xl border bg-card p-5">
          <div className="flex justify-between text-lg font-extrabold"><span>Total</span><span>{inr(c.subtotal)}</span></div>
          <Button
            className="mt-4 h-12 w-full bg-success text-base font-bold text-success-foreground hover:bg-success/90"
            disabled={!addressId || blocked || checkout.isPending}
            onClick={() => checkout.mutate()}
          >
            {checkout.isPending ? "Placing order…" : `Place order · ${inr(c.subtotal)}`}
          </Button>
          {!addressId && <p className="mt-2 text-xs text-muted-foreground">Add an address to continue.</p>}
        </div>
      </aside>
    </div>
  );
}
