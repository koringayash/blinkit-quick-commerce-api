import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import hero from "@/assets/hero-groceries.jpg";
import { api, type Facet, type SearchResponse } from "@/lib/api";
import { categoryEmoji } from "@/lib/emoji";
import { useSession } from "@/lib/session";
import { ProductTile } from "@/components/ProductTile";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "QuickKart — Groceries delivered in minutes" },
      { name: "description", content: "Fresh groceries, snacks and daily essentials from your nearest store, delivered in minutes." },
      { property: "og:title", content: "QuickKart — Groceries delivered in minutes" },
      { property: "og:description", content: "Fresh groceries and essentials from your nearest store, in minutes." },
    ],
  }),
  component: Home,
});

function CategoryRow({ cat, storeId }: { cat: string; storeId: number | null }) {
  const q = useQuery({
    queryKey: ["search", { category: cat, storeId, limit: 6 }],
    queryFn: () => api<SearchResponse>("/items/search", { params: { category: [cat], store_id: storeId, limit: 6, in_stock: true } }),
  });
  if (!q.data?.items.length) return null;
  return (
    <section className="mt-10">
      <div className="mb-3 flex items-end justify-between">
        <h2 className="text-xl font-extrabold">{cat}</h2>
        <Link to="/search" search={{ category: cat }} className="text-sm font-bold text-success">see all</Link>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {q.data.items.map((i) => <ProductTile key={i.sku} item={i} />)}
      </div>
    </section>
  );
}

function Home() {
  const { storeId } = useSession();
  const cats = useQuery({
    queryKey: ["categories", storeId],
    queryFn: () => api<Facet[]>("/items/categories", { params: { store_id: storeId } }),
  });

  return (
    <div>
      <div className="relative overflow-hidden rounded-2xl bg-primary">
        <img src={hero} alt="Groceries bursting out of a delivery bag" width={1280} height={640} className="h-56 w-full object-cover md:h-72" />
        <div className="absolute inset-0 flex flex-col justify-center bg-gradient-to-r from-primary via-primary/80 to-transparent p-6 md:p-10">
          <h1 className="max-w-md text-3xl font-extrabold md:text-5xl">Groceries at your door in minutes</h1>
          <p className="mt-2 max-w-sm font-medium">Milk, bread, snacks and more — straight from a store near you.</p>
        </div>
      </div>

      <h2 className="mt-8 mb-3 text-xl font-extrabold">Shop by category</h2>
      {cats.isLoading ? (
        <GridSkeleton n={6} />
      ) : cats.error ? (
        <ErrorBox error={cats.error} />
      ) : (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
          {cats.data!.map((c) => (
            <Link key={c.name} to="/search" search={{ category: c.name }} className="flex flex-col items-center rounded-xl bg-secondary p-3 text-center transition-transform hover:-translate-y-0.5">
              <span className="text-4xl">{categoryEmoji(c.name)}</span>
              <span className="mt-2 text-xs font-bold leading-tight">{c.name}</span>
            </Link>
          ))}
        </div>
      )}

      {cats.data?.slice(0, 6).map((c) => <CategoryRow key={c.name} cat={c.name} storeId={storeId} />)}
    </div>
  );
}
