// Thin client for the FastAPI backend (blinkit-quick-commerce-api). Backend logic lives there; this only calls it.
const BASE_KEY = "qc_api_base";
const TOKEN_KEY = "qc_token";
const STORE_KEY = "qc_store_id";

// Baked in at build time (Docker build arg / .env: VITE_API_BASE_URL); users can still override it in Settings.
export const DEFAULT_API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "") || "http://localhost:8000";

const isBrowser = () => typeof window !== "undefined";

export const settings = {
  getBase: () => (isBrowser() && localStorage.getItem(BASE_KEY)) || DEFAULT_API_BASE,
  setBase: (v: string) => localStorage.setItem(BASE_KEY, v.replace(/\/+$/, "")),
  getToken: () => (isBrowser() ? localStorage.getItem(TOKEN_KEY) : null),
  setToken: (t: string | null) =>
    t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY),
  getStoreId: (): number | null => {
    if (!isBrowser()) return null;
    const v = localStorage.getItem(STORE_KEY);
    return v ? Number(v) : null;
  },
  setStoreId: (id: number | null) =>
    id == null ? localStorage.removeItem(STORE_KEY) : localStorage.setItem(STORE_KEY, String(id)),
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

function qs(params?: Params) {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join(", ");
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === "string") {
      if (Array.isArray(obj.items) && obj.items.length > 0) {
        const itemsStr = obj.items
          .map((i: Record<string, unknown>) => `${i.sku} (avail: ${i.available ?? 0})`)
          .join(", ");
        return `${obj.message}: ${itemsStr}`;
      }
      return obj.message;
    }
  }
  return "Request failed";
}

export async function api<T>(
  path: string,
  opts: { method?: string; params?: Params; body?: unknown; form?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = settings.getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = new URLSearchParams(opts.form).toString();
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`${settings.getBase()}${path}${qs(opts.params)}`, {
      method: opts.method ?? "GET",
      headers,
      body: body ?? null,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check the API address in Settings.");
  }
  if (res.status === 401 && token) {
    settings.setToken(null);
    window.dispatchEvent(new Event("qc-auth"));
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = detailToMessage((await res.json()).detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------- Types mirroring backend schemas ----------
export interface Item {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  brand: string | null;
  description: string | null;
  image_url?: string | null;
  price: number;
  available_qty: number;
}
export interface Facet { name: string; total_items: number; in_stock_items: number }
export interface SearchResponse {
  store_id: number | null;
  store_code: string | null;
  eta_minutes: number | null;
  distance_km: number | null;
  items: Item[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  facets: { categories: Facet[]; brands: Facet[]; min_price: number | null; max_price: number | null };
}
export interface Suggestions {
  query: string;
  products: { sku: string; name: string; category: string | null; brand: string | null; price: number; in_stock: boolean }[];
  matching_categories: string[];
  matching_brands: string[];
}
export interface User { id: number; email: string; full_name: string; is_admin: boolean; created_at: string }
export interface CartLine {
  sku: string; name: string; unit_price: number; quantity: number; line_total: number;
  available_qty: number; in_stock: boolean; added_at: string;
}
export interface Cart { store_id: number | null; store_code: string | null; items: CartLine[]; item_count: number; subtotal: number }
export interface Address {
  id: number; label: string; line1?: string; line2?: string | null; city: string; pincode: string;
  latitude: number | null; longitude: number | null; is_default: boolean;
}
export interface Order {
  id: number; status: string; address_id: number | null; store_id: number | null;
  store_code: string | null; store_name: string | null; total: number; created_at: string;
  delivery_status: string | null; tracking_id: string | null; delivery_address: string | null;
  payment_status: string | null; payment_method: string | null;
  items: { sku: string; name: string; quantity: number; unit_price: number; line_total: number }[];
}
export interface PaymentInit {
  payment_id: number; order_id: number; amount: number; currency: string; payment_method: string;
  status: string; gateway_name: string; gateway_order_id: string | null; payment_token: string | null; message: string;
}
export interface Payment {
  id: number; order_id: number; amount: number; currency: string; payment_method: string; status: string;
  gateway_name: string; gateway_payment_id: string | null; error_reason: string | null; created_at: string;
}
export interface Tracking {
  order_id: number; tracking_id: string; status: string; partner_name: string;
  rider: { name: string; phone: string; vehicle_type: string };
  pickup_address: string; delivery_address: string;
  current_location: { latitude: number; longitude: number };
  pickup_location: { latitude: number; longitude: number };
  delivery_location: { latitude: number; longitude: number };
  eta_minutes: number; last_updated_at: string;
}
export interface Store {
  id: number; code: string; name: string; address: string; city: string; pincode: string;
  latitude: number; longitude: number; service_radius_km: number; base_prep_minutes: number; is_active: boolean;
}
export interface Serviceability {
  serviceable: boolean; matched_by: string | null; store: Store | null; distance_km: number | null;
  eta_minutes: number | null; message: string;
  nearby_stores: { store: Store; distance_km: number; within_service_radius: boolean; estimated_eta_minutes: number }[];
}
export interface Favorite { sku: string; name: string; price: number; available_qty: number; added_at: string }
export interface AnalyticsSummary {
  total_gmv: number; total_orders: number; paid_orders: number; average_order_value: number;
  payment_methods_breakdown: Record<string, number>; order_status_breakdown: Record<string, number>;
  total_customers: number; active_deliveries: number;
}

export const inr = (n: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n);
