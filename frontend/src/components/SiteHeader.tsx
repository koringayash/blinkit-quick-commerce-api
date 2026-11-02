import { useEffect, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Search, Settings, ShoppingCart, Store as StoreIcon, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, inr, settings, type Serviceability, type Store, type Suggestions } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { useSession } from "@/lib/session";

function LocationDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { storeId, setStoreId } = useSession();
  const qc = useQueryClient();
  const [pincode, setPincode] = useState("");
  const [result, setResult] = useState<Serviceability | null>(null);
  const [busy, setBusy] = useState(false);

  const stores = useQuery({
    queryKey: ["stores"],
    queryFn: () => api<Store[]>("/stores"),
    enabled: open,
  });

  const applyStore = (store: Store, etaMinutes: number | null, labelSuffix?: string) => {
    setStoreId(store.id);
    const eta = etaMinutes ?? store.base_prep_minutes + 4;
    localStorage.setItem("qc_eta", String(eta));
    localStorage.setItem("qc_loc_label", `${store.city} · ${labelSuffix ?? store.pincode}`);
    window.dispatchEvent(new Event("qc-loc"));
    qc.invalidateQueries({ queryKey: ["search"] });
    qc.invalidateQueries({ queryKey: ["categories"] });
    qc.invalidateQueries({ queryKey: ["item"] });
    qc.invalidateQueries({ queryKey: ["cart"] });
  };

  const check = async (params: { pincode?: string; lat?: number; lng?: number }) => {
    setBusy(true);
    try {
      const r = await api<Serviceability>("/stores/serviceability", { params });
      setResult(r);
      if (r.serviceable && r.store) {
        applyStore(r.store, r.eta_minutes, params.pincode ?? r.store.pincode);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Where should we deliver?</DialogTitle>
          <DialogDescription>We'll find the nearest Dark Store within 3 km and show its real-time stock.</DialogDescription>
        </DialogHeader>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            navigator.geolocation.getCurrentPosition(
              (p) => check({ lat: p.coords.latitude, lng: p.coords.longitude }),
              () => toast.error("Couldn't get your location"),
            )
          }
        >
          <MapPin className="mr-2 h-4 w-4" /> Use my current GPS location
        </Button>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!/^\d{6}$/.test(pincode)) { toast.error("Enter a 6-digit pincode"); return; }
            check({ pincode });
          }}
        >
          <Input placeholder="Pincode, e.g. 560038" value={pincode} onChange={(e) => setPincode(e.target.value)} />
          <Button type="submit" disabled={busy}>Check</Button>
        </form>
        {result && (
          <div className={`rounded-lg p-3 text-sm ${result.serviceable ? "bg-secondary text-secondary-foreground" : "bg-muted"}`}>
            <p className="font-semibold">{result.message}</p>
            {result.store && <p className="mt-1 text-muted-foreground">{result.store.name} ({result.store.code})</p>}
          </div>
        )}
        {!!stores.data?.length && (
          <div className="space-y-1.5 pt-1">
            <p className="text-xs font-bold uppercase text-muted-foreground">Available neighborhood Dark Stores</p>
            <div className="max-h-44 space-y-1.5 overflow-y-auto">
              {stores.data.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => {
                    applyStore(s, s.base_prep_minutes + 4, s.pincode);
                    toast.success(`Switched to ${s.name}`);
                    onOpenChange(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs transition-colors hover:bg-muted ${
                    storeId === s.id ? "border-success bg-secondary/60 font-semibold" : ""
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <StoreIcon className="h-3.5 w-3.5 text-success" />
                    <span>
                      <span className="font-bold">{s.city} · {s.pincode}</span>
                      <span className="block text-[11px] text-muted-foreground">{s.name}</span>
                    </span>
                  </span>
                  <span className="font-semibold text-success">~{s.base_prep_minutes + 4} min</span>
                </button>
              ))}
            </div>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setStoreId(null);
            localStorage.removeItem("qc_loc_label");
            localStorage.removeItem("qc_eta");
            window.dispatchEvent(new Event("qc-loc"));
            qc.invalidateQueries({ queryKey: ["search"] });
            qc.invalidateQueries({ queryKey: ["categories"] });
            qc.invalidateQueries({ queryKey: ["item"] });
            qc.invalidateQueries({ queryKey: ["cart"] });
            onOpenChange(false);
          }}
        >
          Shop all stores (global inventory) instead
        </Button>
      </DialogContent>
    </Dialog>
  );
}

function SettingsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [base, setBase] = useState("");
  useEffect(() => { if (open) setBase(settings.getBase()); }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Server address</DialogTitle>
          <DialogDescription>Where your shop's server is running.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="base">API URL</Label>
          <Input id="base" value={base} onChange={(e) => setBase(e.target.value)} placeholder="http://localhost:8000" />
        </div>
        <DialogFooter>
          <Button onClick={() => { settings.setBase(base); location.reload(); }}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SearchBox() {
  const navigate = useNavigate();
  const { storeId } = useSession();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [focus, setFocus] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 200); return () => clearTimeout(t); }, [q]);
  const sug = useQuery({
    queryKey: ["suggest", debounced, storeId],
    queryFn: () => api<Suggestions>("/items/suggest", { params: { q: debounced, store_id: storeId } }),
    enabled: debounced.length >= 2,
  });
  const go = (term: string) => { setFocus(false); navigate({ to: "/search", search: { q: term } }); };
  return (
    <div className="relative flex-1">
      <form onSubmit={(e) => { e.preventDefault(); go(q); }}>
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder='Search "milk", "bread", "chips"…'
          className="h-11 bg-muted pl-9"
        />
      </form>
      {focus && sug.data && sug.data.products.length + sug.data.matching_categories.length > 0 && (
        <div className="absolute left-0 right-0 top-12 z-50 overflow-hidden rounded-xl border bg-popover shadow-card">
          {sug.data.matching_categories.map((c) => (
            <button key={c} className="block w-full px-4 py-2 text-left text-sm hover:bg-muted" onClick={() => navigate({ to: "/search", search: { category: c } })}>
              in <span className="font-semibold">{c}</span>
            </button>
          ))}
          {sug.data.products.map((p) => (
            <Link key={p.sku} to="/product/$sku" params={{ sku: p.sku }} className="flex justify-between px-4 py-2 text-sm hover:bg-muted">
              <span>{p.name}</span>
              <span className="text-muted-foreground">{inr(p.price)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function SiteHeader() {
  const { user, token, logout } = useSession();
  const cart = useCart();
  const navigate = useNavigate();
  const [locOpen, setLocOpen] = useState(false);
  const [setOpen, setSetOpen] = useState(false);
  const [loc, setLoc] = useState<{ label: string | null; eta: string | null }>({ label: null, eta: null });
  useEffect(() => {
    const read = () => setLoc({ label: localStorage.getItem("qc_loc_label"), eta: localStorage.getItem("qc_eta") });
    read();
    window.addEventListener("qc-loc", read);
    return () => window.removeEventListener("qc-loc", read);
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
        <Link to="/" className="font-display text-2xl font-extrabold tracking-tight">
          <span className="rounded-md bg-primary px-1.5">quick</span><span className="text-success">kart</span>
        </Link>
        <button onClick={() => setLocOpen(true)} className="hidden text-left md:block">
          <p className="font-display text-sm font-extrabold">
            {loc.eta ? `Delivery in ${loc.eta} minutes` : "Set delivery location"}
          </p>
          <p className="max-w-44 truncate text-xs text-muted-foreground">{loc.label ?? "Tap to check your area ▾"}</p>
        </button>
        <SearchBox />
        <Button variant="ghost" size="icon" aria-label="Settings" onClick={() => setSetOpen(true)}>
          <Settings className="h-5 w-5" />
        </Button>
        {token ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-2"><UserIcon className="h-5 w-5" /><span className="hidden sm:inline">{user?.full_name.split(" ")[0] ?? "Account"}</span></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => navigate({ to: "/orders" })}>My orders</DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate({ to: "/account" })}>Addresses & favourites</DropdownMenuItem>
              {user?.is_admin && <DropdownMenuItem onClick={() => navigate({ to: "/admin" })}>Admin dashboard</DropdownMenuItem>}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => { logout(); navigate({ to: "/" }); }}>Log out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <Button variant="ghost" asChild><Link to="/login">Login</Link></Button>
        )}
        <Button asChild className="h-11 gap-2 bg-success font-bold text-success-foreground hover:bg-success/90">
          <Link to="/cart">
            <ShoppingCart className="h-5 w-5" />
            {cart.data && cart.data.item_count > 0 ? (
              <span className="text-left text-xs leading-tight">{cart.data.item_count} items<br />{inr(cart.data.subtotal)}</span>
            ) : "My Cart"}
          </Link>
        </Button>
      </div>
      <LocationDialog open={locOpen} onOpenChange={setLocOpen} />
      <SettingsDialog open={setOpen} onOpenChange={setSetOpen} />
    </header>
  );
}
