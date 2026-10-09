"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Camera, ClipboardList, Home, Landmark, LayoutDashboard, LogOut, Moon, Scale, Sun, Users, BookOpen, Tags, BarChart3, ShieldCheck, WifiOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isAdminRole, useAuth } from "@/lib/auth";
import { useSync } from "@/lib/sync";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { Loading } from "@/components/app/bits";

const EMP_NAV = [
  { href: "/", label: "nav.home", icon: Home },
  { href: "/shto", label: "nav.add", icon: Camera },
  { href: "/shpenzimet", label: "nav.expenses", icon: ClipboardList },
  { href: "/pajtimi", label: "nav.reconciliation", icon: Scale },
];
const ADMIN_NAV = [
  { href: "/admin", label: "nav.dashboard", icon: LayoutDashboard },
  { href: "/admin/shpenzimet", label: "nav.approvals", icon: ClipboardList },
  { href: "/admin/llogarite", label: "nav.accounts", icon: Landmark },
  { href: "/admin/librat", label: "nav.ledger", icon: BookOpen },
  { href: "/admin/pajtimi", label: "nav.reconciliation", icon: Scale },
  { href: "/admin/analitika", label: "nav.analytics", icon: BarChart3 },
  { href: "/admin/perdoruesit", label: "nav.users", icon: Users },
  { href: "/admin/kategorite", label: "nav.categories", icon: Tags },
  { href: "/admin/auditimi", label: "nav.audit", icon: ShieldCheck },
];

function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  return (
    <Button variant="ghost" size="icon" aria-label={t("common.theme")} data-testid="theme-toggle" onClick={() => {
      const next = !dark;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("theme", next ? "dark" : "light");
      setDark(next);
    }}>
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

function SyncStatus() {
  const { online, pending, syncing, syncNow } = useSync();
  if (online && pending.length === 0 && !syncing) return <span className="hidden text-xs text-muted-foreground sm:inline" data-testid="sync-status">{t("sync.online")}</span>;
  return (
    <button type="button" onClick={() => void syncNow()} data-testid="sync-status" className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-xs text-amber-900 dark:bg-amber-900 dark:text-amber-100">
      {online ? <RefreshCw className={cn("size-3", syncing && "animate-spin")} /> : <WifiOff className="size-3" />}
      {syncing ? t("sync.syncing") : !online ? t("sync.offline") : t("sync.pending", { n: pending.length })}
    </button>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const admin = isAdminRole(user?.role) || user?.role === "auditor";

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    if (user && !admin && path.startsWith("/admin")) router.replace("/");
  }, [loading, user, admin, path, router]);

  if (loading || !user) return <Loading />;
  const nav = admin ? ADMIN_NAV : EMP_NAV;
  const active = (href: string) => (href === "/" || href === "/admin" ? path === href : path.startsWith(href));

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      {admin && (
        <aside className="hidden w-60 shrink-0 border-r bg-card md:block">
          <div className="p-4 text-sm font-semibold">{t("app.short")}</div>
          <nav className="grid gap-1 px-2" aria-label="Navigimi">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} className={cn("flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted", active(n.href) && "bg-muted font-medium")}>
                <n.icon className="size-4" /> {t(n.label)}
              </Link>
            ))}
          </nav>
        </aside>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        {user.is_demo && <div role="status" className="bg-amber-400 px-3 py-1 text-center text-xs font-medium text-black">{t("login.demoBanner")}</div>}
        <header className="sticky top-0 z-20 flex items-center justify-between gap-2 border-b bg-background/95 px-3 py-2 backdrop-blur">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{user.household_name}</div>
            <div className="truncate text-xs text-muted-foreground" data-testid="whoami">{user.name} · {t(`users.role.${user.role}`)}</div>
          </div>
          <div className="flex items-center gap-1">
            <SyncStatus />
            <ThemeToggle />
            <Button variant="ghost" size="icon" aria-label={t("common.logout")} data-testid="logout" onClick={async () => { await logout(); router.replace("/login"); }}>
              <LogOut className="size-4" />
            </Button>
          </div>
        </header>
        {admin && (
          <nav className="flex gap-1 overflow-x-auto border-b px-2 py-1 md:hidden" aria-label="Navigimi">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} className={cn("whitespace-nowrap rounded-md px-3 py-1.5 text-sm", active(n.href) ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>{t(n.label)}</Link>
            ))}
          </nav>
        )}
        <main className={cn("mx-auto w-full max-w-5xl flex-1 p-4", !admin && "pb-24")}>{children}</main>
        {!admin && (
          <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t bg-background pb-[env(safe-area-inset-bottom)]" aria-label="Navigimi">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} className={cn("flex flex-col items-center gap-0.5 py-2 text-xs", active(n.href) ? "text-primary font-semibold" : "text-muted-foreground")}>
                <n.icon className="size-5" /> {t(n.label)}
              </Link>
            ))}
          </nav>
        )}
      </div>
    </div>
  );
}
