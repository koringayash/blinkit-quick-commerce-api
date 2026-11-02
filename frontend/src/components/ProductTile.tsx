import { Link, useNavigate } from "@tanstack/react-router";
import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { inr, type Item } from "@/lib/api";
import { useCart, useSetCartQty } from "@/lib/cart";
import { useSession } from "@/lib/session";
import { categoryEmoji } from "@/lib/emoji";

export function QtyControl({ sku, inStock }: { sku: string; inStock: boolean }) {
  const { token } = useSession();
  const navigate = useNavigate();
  const cart = useCart();
  const setQty = useSetCartQty();
  const qty = cart.data?.items.find((l) => l.sku === sku)?.quantity ?? 0;

  if (!inStock) return <span className="text-xs font-semibold text-muted-foreground">Out of stock</span>;
  if (qty === 0)
    return (
      <Button
        size="sm"
        variant="outline"
        className="h-8 border-success px-5 font-bold text-success hover:bg-secondary hover:text-success"
        disabled={setQty.isPending}
        onClick={(e) => {
          e.preventDefault();
          if (!token) { navigate({ to: "/login" }); return; }
          setQty.mutate({ sku, qty: 1 });
        }}
      >
        ADD
      </Button>
    );
  return (
    <div
      className="flex h-8 items-center rounded-md bg-success text-success-foreground"
      onClick={(e) => e.preventDefault()}
    >
      <button aria-label="Decrease" className="px-2" onClick={() => setQty.mutate({ sku, qty: qty - 1 })}>
        <Minus className="h-3.5 w-3.5" />
      </button>
      <span className="min-w-5 text-center text-sm font-bold">{qty}</span>
      <button
        aria-label="Increase"
        className="px-2 disabled:opacity-50"
        disabled={qty >= 50}
        onClick={() => setQty.mutate({ sku, qty: qty + 1 })}
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function ProductTile({ item }: { item: Item }) {
  const inStock = item.available_qty > 0;
  return (
    <Link
      to="/product/$sku"
      params={{ sku: item.sku }}
      className="group flex flex-col rounded-xl border bg-card p-3 transition-shadow hover:shadow-card"
    >
      <div className="mb-3 flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-muted text-5xl transition-transform group-hover:scale-[1.02]">
        {item.image_url ? (
          <img
            src={item.image_url}
            alt={item.name}
            loading="lazy"
            className={`h-full w-full object-cover ${inStock ? "" : "opacity-40 grayscale"}`}
          />
        ) : (
          <span className={inStock ? "" : "opacity-40 grayscale"}>{categoryEmoji(item.category)}</span>
        )}
      </div>
      {item.brand && <p className="text-[11px] font-semibold uppercase text-muted-foreground">{item.brand}</p>}
      <p className="line-clamp-2 min-h-10 text-sm font-semibold leading-5">{item.name}</p>
      <div className="mt-auto flex items-center justify-between pt-3">
        <span className="text-sm font-bold">{inr(item.price)}</span>
        <QtyControl sku={item.sku} inStock={inStock} />
      </div>
    </Link>
  );
}
