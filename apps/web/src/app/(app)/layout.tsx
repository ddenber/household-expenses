import { Shell } from "@/components/app/shell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
