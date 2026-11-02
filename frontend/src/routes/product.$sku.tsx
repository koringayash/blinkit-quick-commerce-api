import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Heart } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, inr, type Favorite, type Item } from "@/lib/api";
import { categoryEmoji } from "@/lib/emoji";
import { useSession } from "@/lib/session";
import { ProductTile, QtyControl } from "@/components/ProductTile";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";

export const Route = createFileRoute("/product/$sku")({
  head: () => ({
    meta: [
      { title: "Product details — QuickKart" },
      { name: "description", content: "Product price, stock and similar items." },
      { property: "og:title", content: "Product details — QuickKart" },
      { property: "og:description", content: "Product price, stock and similar items." },
    ],
  }),
  component: ProductPage,
});

function ProductPage() {
  const { sku } = Route.useParams();
  const { token, storeId } = useSession();
  const qc = useQueryClient();
  const item = useQuery({
    queryKey: ["item", sku, storeId],
    queryFn: () => api<Item>(`/items/${encodeURIComponent(sku)}`, { params: { store_id: storeId } }),
  });
  const similar = useQuery({
    queryKey: ["similar", sku, storeId],
    queryFn: () => api<Item[]>(`/items/${encodeURIComponent(sku)}/similar`, { params: { store_id: storeId } }),
  });
  const favs = useQuery({ queryKey: ["favorites", token], queryFn: () => api<Favorite[]>("/me/favorites"), enabled: !!token });
  const isFav = !!favs.data?.some((f) => f.sku === sku);
  const fav = useMutation({
    mutationFn: () => api<void>(`/me/favorites/${encodeURIComponent(sku)}`, { method: isFav ? "DELETE" : "PUT" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["favorites"] }); toast.success(isFav ? "Removed from favourites" : "Saved to favourites"); },
    onError: (e: Error) => toast.error(e.message),
  });

  if (item.isLoading) return <GridSkeleton n={2} />;
  if (item.error) return <ErrorBox error={item.error} />;
  const i = item.data!;
  const inStock = i.available_qty > 0;

  return (
    <div>
      <div className="grid gap-8 md:grid-cols-2">
        <div className="flex aspect-square items-center justify-center overflow-hidden rounded-2xl border bg-card text-[10rem]">
          {i.image_url ? (
            <img src={i.image_url} alt={i.name} className="h-full w-full object-cover" />
          ) : (
            categoryEmoji(i.category)
          )}
        </div>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{[i.category, i.brand].filter(Boolean).join(" · ")}</p>
          <h1 className="text-3xl font-extrabold">{i.name}</h1>
          <p className="text-2xl font-bold">{inr(i.price)}</p>
          <p className={`text-sm font-semibold ${inStock ? "text-success" : "text-destructive"}`}>
            {inStock ? (i.available_qty <= 5 ? `Only ${i.available_qty} left` : "In stock") : "Out of stock"}
          </p>
          <div className="flex items-center gap-3">
            <div className="scale-125 origin-left"><QtyControl sku={i.sku} inStock={inStock} /></div>
            {token && (
              <Button variant="ghost" size="icon" className="ml-6" aria-label="Favourite" onClick={() => fav.mutate()}>
                <Heart className={`h-5 w-5 ${isFav ? "fill-destructive text-destructive" : ""}`} />
              </Button>
            )}
          </div>
          {i.description && <p className="leading-relaxed text-muted-foreground">{i.description}</p>}
        </div>
      </div>
      {!!similar.data?.length && (
        <section className="mt-12">
          <h2 className="mb-3 text-xl font-extrabold">You might also like</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {similar.data.map((s) => <ProductTile key={s.sku} item={s} />)}
          </div>
        </section>
      )}
    </div>
  );
}
