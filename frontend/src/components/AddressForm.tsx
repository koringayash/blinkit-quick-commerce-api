import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";

export function AddressForm({ onDone }: { onDone?: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ label: "Home", line1: "", city: "", pincode: "", is_default: false });
  const [coords, setCoords] = useState<{ latitude: number; longitude: number } | null>(null);
  const save = useMutation({
    mutationFn: () => api("/me/addresses", { method: "POST", body: { ...f, ...(coords ?? {}) } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["addresses"] });
      toast.success("Address saved");
      setF({ label: "Home", line1: "", city: "", pincode: "", is_default: false });
      setCoords(null);
      onDone?.();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!/^\d{6}$/.test(f.pincode)) { toast.error("Pincode must be 6 digits"); return; }
        save.mutate();
      }}
    >
      <Input placeholder="Label (Home, Work…)" required maxLength={50} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
      <Input placeholder="Street / Flat / Building (e.g. 12, 100ft Rd, Indiranagar)" required maxLength={255} value={f.line1} onChange={(e) => setF({ ...f, line1: e.target.value })} />
      <div className="flex gap-2">
        <Input placeholder="City" required value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />
        <Input placeholder="Pincode (6 digits)" required value={f.pincode} onChange={(e) => setF({ ...f, pincode: e.target.value })} />
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => navigator.geolocation.getCurrentPosition(
          (p) => { setCoords({ latitude: p.coords.latitude, longitude: p.coords.longitude }); toast.success("Location added"); },
          () => toast.error("Couldn't get your location"),
        )}
      >
        {coords ? "📍 Location added" : "Add my GPS location"}
      </Button>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={f.is_default} onCheckedChange={(v) => setF({ ...f, is_default: !!v })} /> Make default
      </label>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={save.isPending}>Save address</Button>
        {onDone && <Button type="button" size="sm" variant="ghost" onClick={onDone}>Cancel</Button>}
      </div>
    </form>
  );
}
