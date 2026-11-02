import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, inr, type AnalyticsSummary, type Store } from "@/lib/api";
import { label } from "@/lib/status";
import { useSession } from "@/lib/session";
import { ErrorBox, GridSkeleton } from "@/components/QueryState";

export const Route = createFileRoute("/admin")({
  head: () => ({
    meta: [
      { title: "Admin dashboard — QuickKart" },
      { name: "description", content: "Sales, top products, dark stores and stock health." },
      { property: "og:title", content: "Admin dashboard — QuickKart" },
      { property: "og:description", content: "Sales, top products and stock health." },
    ],
  }),
  component: AdminPage,
});

interface Top { sku: string; name: string; [k: string]: unknown }
interface Health { [k: string]: unknown }

function Stat({ k, v }: { k: string; v: string | number }) {
  return <div className="rounded-xl border bg-card p-4"><p className="text-xs font-semibold uppercase text-muted-foreground">{k}</p><p className="mt-1 text-2xl font-extrabold">{v}</p></div>;
}

function Breakdown({ title, data }: { title: string; data: Record<string, number> }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="rounded-xl border bg-card p-4">
      <h3 className="mb-3 font-extrabold">{title}</h3>
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="mb-2 text-sm">
          <div className="flex justify-between"><span>{label(k)}</span><span className="font-bold">{v}</span></div>
          <div className="mt-1 h-2 rounded-full bg-muted"><div className="h-2 rounded-full bg-success" style={{ width: `${(v / total) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

function AdminPage() {
  const { token, ready } = useSession();
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: ["a-sum", token], queryFn: () => api<AnalyticsSummary>("/admin/analytics/summary"), enabled: !!token });
  const top = useQuery({ queryKey: ["a-top", token], queryFn: () => api<Top[]>("/admin/analytics/top-selling"), enabled: !!token });
  const health = useQuery({ queryKey: ["a-health", token], queryFn: () => api<Health>("/admin/analytics/inventory-health"), enabled: !!token });
  const stores = useQuery({ queryKey: ["stores"], queryFn: () => api<Store[]>("/stores", { params: { active_only: false } }), enabled: !!token });

  const [newItem, setNewItem] = useState({
    sku: "",
    name: "",
    category: "Dairy & Breakfast",
    brand: "",
    description: "",
    price: "",
    available_qty: "20",
  });

  const [restock, setRestock] = useState({
    store_id: "",
    sku: "",
    delta_qty: "15",
  });

  const [newStore, setNewStore] = useState({
    code: "",
    name: "",
    address: "",
    city: "Bengaluru",
    pincode: "",
    latitude: "12.9784",
    longitude: "77.6408",
    service_radius_km: "3.0",
    base_prep_minutes: "3",
  });

  const createItemMut = useMutation({
    mutationFn: () =>
      api("/items", {
        method: "POST",
        body: {
          sku: newItem.sku.trim().toUpperCase(),
          name: newItem.name.trim(),
          category: newItem.category.trim() || null,
          brand: newItem.brand.trim() || null,
          description: newItem.description.trim() || null,
          price: Number(newItem.price),
          available_qty: Number(newItem.available_qty),
        },
      }),
    onSuccess: () => {
      toast.success("Product created");
      setNewItem({ sku: "", name: "", category: "Dairy & Breakfast", brand: "", description: "", price: "", available_qty: "20" });
      qc.invalidateQueries({ queryKey: ["a-health"] });
      qc.invalidateQueries({ queryKey: ["search"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const restockMut = useMutation({
    mutationFn: () => {
      const sku = restock.sku.trim().toUpperCase();
      const delta_qty = Number(restock.delta_qty);
      if (restock.store_id) {
        return api(`/stores/${Number(restock.store_id)}/items/${encodeURIComponent(sku)}/stock`, {
          method: "PATCH",
          body: { delta_qty },
        });
      }
      return api(`/items/${encodeURIComponent(sku)}/stock`, {
        method: "PATCH",
        body: { delta_qty },
      });
    },
    onSuccess: () => {
      toast.success("Stock updated");
      qc.invalidateQueries({ queryKey: ["a-health"] });
      qc.invalidateQueries({ queryKey: ["search"] });
      qc.invalidateQueries({ queryKey: ["item"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createStoreMut = useMutation({
    mutationFn: () =>
      api("/stores", {
        method: "POST",
        body: {
          code: newStore.code.trim().toUpperCase(),
          name: newStore.name.trim(),
          address: newStore.address.trim(),
          city: newStore.city.trim(),
          pincode: newStore.pincode.trim(),
          latitude: Number(newStore.latitude),
          longitude: Number(newStore.longitude),
          service_radius_km: Number(newStore.service_radius_km),
          base_prep_minutes: Number(newStore.base_prep_minutes),
        },
      }),
    onSuccess: () => {
      toast.success("Dark Store created");
      setNewStore({
        code: "",
        name: "",
        address: "",
        city: "Bengaluru",
        pincode: "",
        latitude: "12.9784",
        longitude: "77.6408",
        service_radius_km: "3.0",
        base_prep_minutes: "3",
      });
      qc.invalidateQueries({ queryKey: ["stores"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!ready) return null;
  if (!token || summary.error) return <ErrorBox error={summary.error ?? Object.assign(new Error(""), { status: 401 })} />;
  if (!summary.data) return <GridSkeleton n={4} />;
  const s = summary.data;
  const scalarHealth = Object.entries(health.data ?? {}).filter(([, v]) => typeof v === "number");
  const listHealth = Object.entries(health.data ?? {}).filter(([, v]) => Array.isArray(v)) as [string, Record<string, unknown>[]][];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Admin dashboard</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat k="Revenue (GMV)" v={inr(s.total_gmv)} />
        <Stat k="Orders" v={`${s.total_orders} (${s.paid_orders} paid)`} />
        <Stat k="Avg order" v={inr(s.average_order_value)} />
        <Stat k="Customers" v={s.total_customers} />
        <Stat k="Active deliveries" v={s.active_deliveries} />
        {scalarHealth.map(([k, v]) => <Stat key={k} k={k.replaceAll("_", " ")} v={k.includes("valuation") ? inr(v as number) : (v as number)} />)}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Breakdown title="Payment methods" data={s.payment_methods_breakdown} />
        <Breakdown title="Order status" data={s.order_status_breakdown} />
      </div>

      {/* Catalog & Dark Store Management Forms */}
      <div className="grid gap-4 md:grid-cols-3">
        <form
          className="space-y-2.5 rounded-xl border bg-card p-4"
          onSubmit={(e) => {
            e.preventDefault();
            createItemMut.mutate();
          }}
        >
          <h3 className="font-extrabold">Add Catalog Product</h3>
          <Input placeholder="SKU (e.g. MILK-AMUL-500ML)" required value={newItem.sku} onChange={(e) => setNewItem({ ...newItem, sku: e.target.value })} />
          <Input placeholder="Product Name" required value={newItem.name} onChange={(e) => setNewItem({ ...newItem, name: e.target.value })} />
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Category" value={newItem.category} onChange={(e) => setNewItem({ ...newItem, category: e.target.value })} />
            <Input placeholder="Brand" value={newItem.brand} onChange={(e) => setNewItem({ ...newItem, brand: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input type="number" step="0.01" min="1" placeholder="Price (₹)" required value={newItem.price} onChange={(e) => setNewItem({ ...newItem, price: e.target.value })} />
            <Input type="number" min="0" placeholder="Initial Qty" required value={newItem.available_qty} onChange={(e) => setNewItem({ ...newItem, available_qty: e.target.value })} />
          </div>
          <Button type="submit" size="sm" className="w-full font-bold" disabled={createItemMut.isPending}>Create Product</Button>
        </form>

        <form
          className="space-y-2.5 rounded-xl border bg-card p-4"
          onSubmit={(e) => {
            e.preventDefault();
            restockMut.mutate();
          }}
        >
          <h3 className="font-extrabold">Restock SKU (Global or Dark Store)</h3>
          <Input placeholder="SKU (e.g. MILK-NANDINI-500ML)" required value={restock.sku} onChange={(e) => setRestock({ ...restock, sku: e.target.value })} />
          <select
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            value={restock.store_id}
            onChange={(e) => setRestock({ ...restock, store_id: e.target.value })}
          >
            <option value="">Global Inventory Only</option>
            {stores.data?.map((st) => (
              <option key={st.id} value={String(st.id)}>{st.code} — {st.name}</option>
            ))}
          </select>
          <Input type="number" placeholder="Delta Qty (e.g. +20)" required value={restock.delta_qty} onChange={(e) => setRestock({ ...restock, delta_qty: e.target.value })} />
          <Button type="submit" size="sm" className="w-full font-bold" disabled={restockMut.isPending}>Apply Stock Change</Button>
        </form>

        <form
          className="space-y-2.5 rounded-xl border bg-card p-4"
          onSubmit={(e) => {
            e.preventDefault();
            createStoreMut.mutate();
          }}
        >
          <h3 className="font-extrabold">Add Neighborhood Dark Store</h3>
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Code (BLR-HSR-01)" required value={newStore.code} onChange={(e) => setNewStore({ ...newStore, code: e.target.value })} />
            <Input placeholder="Pincode (560102)" required pattern="\d{6}" value={newStore.pincode} onChange={(e) => setNewStore({ ...newStore, pincode: e.target.value })} />
          </div>
          <Input placeholder="Store Name" required value={newStore.name} onChange={(e) => setNewStore({ ...newStore, name: e.target.value })} />
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Address" required value={newStore.address} onChange={(e) => setNewStore({ ...newStore, address: e.target.value })} />
            <Input placeholder="City" required value={newStore.city} onChange={(e) => setNewStore({ ...newStore, city: e.target.value })} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Input type="number" step="any" placeholder="Lat" required value={newStore.latitude} onChange={(e) => setNewStore({ ...newStore, latitude: e.target.value })} />
            <Input type="number" step="any" placeholder="Lng" required value={newStore.longitude} onChange={(e) => setNewStore({ ...newStore, longitude: e.target.value })} />
            <Input type="number" step="0.1" placeholder="Radius km" required value={newStore.service_radius_km} onChange={(e) => setNewStore({ ...newStore, service_radius_km: e.target.value })} />
          </div>
          <Button type="submit" size="sm" className="w-full font-bold" disabled={createStoreMut.isPending}>Create Dark Store</Button>
        </form>
      </div>

      {!!stores.data?.length && (
        <div className="rounded-xl border bg-card p-4">
          <h3 className="mb-3 font-extrabold">Active Dark Stores ({stores.data.length})</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {stores.data.map((st) => (
              <div key={st.id} className="rounded-lg border p-3 text-xs">
                <p className="font-bold text-success">{st.code} · {st.city} ({st.pincode})</p>
                <p className="mt-0.5 font-semibold">{st.name}</p>
                <p className="text-muted-foreground">{st.address}</p>
                <p className="mt-1 text-muted-foreground">
                  GPS: ({st.latitude}, {st.longitude}) · Radius: {st.service_radius_km} km · Prep: {st.base_prep_minutes}m
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-xl border bg-card p-4">
        <h3 className="mb-3 font-extrabold">Top-selling products</h3>
        <table className="w-full text-sm">
          <tbody className="divide-y">
            {top.data?.map((t, i) => (
              <tr key={t.sku}><td className="py-2 font-bold">{i + 1}</td><td>{t.name}</td>
                {Object.entries(t).filter(([k, v]) => typeof v === "number" && k !== "item_id").map(([k, v]) => (
                  <td key={k} className="text-right">{k.includes("revenue") ? inr(v as number) : String(v)} <span className="text-xs text-muted-foreground">{k.replaceAll("_", " ")}</span></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {listHealth.map(([k, rows]) => rows.length > 0 && (
        <div key={k} className="rounded-xl border bg-card p-4">
          <h3 className="mb-3 font-extrabold capitalize">{k.replaceAll("_", " ")}</h3>
          <ul className="divide-y text-sm">
            {rows.map((r, i) => <li key={i} className="flex justify-between py-2"><span>{String(r["name"] ?? r["sku"])}</span><span className="font-bold">{String(r["available_qty"] ?? "")}</span></li>)}
          </ul>
        </div>
      ))}
    </div>
  );
}
