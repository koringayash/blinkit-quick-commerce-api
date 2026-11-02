import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, type SearchResponse } from "@/lib/api";
import { useSession } from "@/lib/session";
import { ProductTile } from "@/components/ProductTile";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";

type S = { q?: string | undefined; category?: string | undefined; brand?: string | undefined; sort?: string | undefined; instock?: boolean | undefined };

export const Route = createFileRoute("/search")({
  validateSearch: (s: Record<string, unknown>): S => ({
    q: typeof s["q"] === "string" ? s["q"] as string : undefined,
    category: typeof s["category"] === "string" ? s["category"] as string : undefined,
    brand: typeof s["brand"] === "string" ? s["brand"] as string : undefined,
    sort: typeof s["sort"] === "string" ? s["sort"] as string : undefined,
    instock: s["instock"] === true || s["instock"] === "true" ? true : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Search products — QuickKart" },
      { name: "description", content: "Search groceries by name, brand or category and filter by price and stock." },
      { property: "og:title", content: "Search products — QuickKart" },
      { property: "og:description", content: "Find groceries and essentials fast." },
    ],
  }),
  component: SearchPage,
});

const SORTS: [string, string][] = [
  ["relevance", "Relevance"],
  ["price_asc", "Price: low to high"],
  ["price_desc", "Price: high to low"],
  ["name_asc", "Name A–Z"],
  ["name_desc", "Name Z–A"],
];

function SearchPage() {
  const s = Route.useSearch();
  const navigate = useNavigate({ from: "/search" });
  const { storeId } = useSession();
  const [limit, setLimit] = useState(24);
  const cats = s.category ? s.category.split(",") : [];
  const brands = s.brand ? s.brand.split(",") : [];

  const q = useQuery({
    queryKey: ["search", s, storeId, limit],
    queryFn: () =>
      api<SearchResponse>("/items/search", {
        params: {
          q: s.q, category: cats, brand: brands, sort_by: s.sort ?? "relevance",
          in_stock: s.instock ? true : undefined, store_id: storeId, limit,
        },
      }),
    placeholderData: keepPreviousData,
  });

  const toggle = (key: "category" | "brand", list: string[], v: string) => {
    const next = list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
    navigate({ search: (p) => ({ ...p, [key]: next.length ? next.join(",") : undefined }) });
  };

  return (
    <div className="grid gap-6 md:grid-cols-[220px_1fr]">
      <aside className="space-y-6">
        <div className="flex items-center gap-2">
          <Switch id="instock" checked={!!s.instock} onCheckedChange={(v) => navigate({ search: (p) => ({ ...p, instock: v || undefined }) })} />
          <Label htmlFor="instock">In stock only</Label>
        </div>
        {(["category", "brand"] as const).map((key) => {
          const facets = key === "category" ? q.data?.facets.categories : q.data?.facets.brands;
          const list = key === "category" ? cats : brands;
          if (!facets?.length) return null;
          return (
            <div key={key}>
              <h3 className="mb-2 text-sm font-extrabold uppercase">{key === "category" ? "Categories" : "Brands"}</h3>
              <div className="space-y-2">
                {facets.map((f) => (
                  <label key={f.name} className="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox checked={list.includes(f.name)} onCheckedChange={() => toggle(key, list, f.name)} />
                    <span className="flex-1">{f.name}</span>
                    <span className="text-xs text-muted-foreground">{f.total_items}</span>
                  </label>
                ))}
              </div>
            </div>
          );
        })}
      </aside>
      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-extrabold">
            {s.q ? `Results for "${s.q}"` : cats.length ? cats.join(", ") : "All products"}
            {q.data && <span className="ml-2 text-sm font-medium text-muted-foreground">{q.data.total} items</span>}
          </h1>
          <Select value={s.sort ?? "relevance"} onValueChange={(v) => navigate({ search: (p) => ({ ...p, sort: v }) })}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>{SORTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {q.isLoading ? <GridSkeleton /> : q.error ? <ErrorBox error={q.error} /> : q.data!.items.length === 0 ? (
          <p className="py-16 text-center text-muted-foreground">No products found.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {q.data!.items.map((i) => <ProductTile key={i.sku} item={i} />)}
            </div>
            {q.data!.has_more && (
              <div className="mt-6 text-center">
                <Button variant="outline" disabled={limit >= 100} onClick={() => setLimit((l) => Math.min(l + 24, 100))}>Load more</Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
