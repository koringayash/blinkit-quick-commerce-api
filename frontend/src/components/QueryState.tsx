import { Link } from "@tanstack/react-router";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

export function ErrorBox({ error }: { error: unknown }) {
  const unauth =
    (error instanceof ApiError && error.status === 401) ||
    (!!error && typeof error === "object" && "status" in error && (error as { status?: number }).status === 401);
  const msg = error instanceof Error && error.message ? error.message : "Something went wrong";
  return (
    <div className="rounded-xl border border-dashed bg-card p-8 text-center">
      <p className="font-semibold">{unauth ? "Please log in to continue" : msg}</p>
      {unauth ? (
        <Button asChild className="mt-4"><Link to="/login">Login</Link></Button>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">Make sure the server is running, or change its address with the ⚙ button.</p>
      )}
    </div>
  );
}

export function GridSkeleton({ n = 10 }: { n?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
      {Array.from({ length: n }).map((_, i) => <Skeleton key={i} className="h-60 rounded-xl" />)}
    </div>
  );
}

export function RequireLogin({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
