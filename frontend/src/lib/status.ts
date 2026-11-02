export const STATUS_LABEL: Record<string, string> = {
  PLACED: "Placed",
  PENDING_PAYMENT: "Awaiting payment",
  PAID: "Paid",
  CONFIRMED: "Confirmed",
  ASSIGNED: "Rider assigned",
  REACHED_DARK_STORE: "Rider at store",
  PICKED_UP: "Picked up",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered",
  CANCELLED: "Cancelled",
  EXPIRED: "Expired",
};
export const label = (s: string | null | undefined) => (s ? STATUS_LABEL[s] ?? s.replaceAll("_", " ") : "—");
export const DELIVERY_STEPS = ["ASSIGNED", "REACHED_DARK_STORE", "PICKED_UP", "OUT_FOR_DELIVERY", "DELIVERED"];
