import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Cart } from "./api";
import { useSession } from "./session";

export function useCart() {
  const { token, storeId } = useSession();
  return useQuery({
    queryKey: ["cart", token, storeId],
    queryFn: () => api<Cart>("/me/cart", { params: { store_id: storeId } }),
    enabled: !!token,
  });
}

export function useSetCartQty() {
  const qc = useQueryClient();
  const { storeId } = useSession();
  return useMutation({
    mutationFn: ({ sku, qty }: { sku: string; qty: number }) =>
      qty <= 0
        ? api<void>(`/me/cart/${encodeURIComponent(sku)}`, { method: "DELETE" })
        : api<void>(`/me/cart/${encodeURIComponent(sku)}`, {
            method: "PUT",
            body: { quantity: qty },
            params: { store_id: storeId },
          }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cart"] }),
    onError: (e: Error) => toast.error(e.message),
  });
}
