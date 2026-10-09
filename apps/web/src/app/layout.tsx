import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/app/providers";

const geist = Geist({ variable: "--font-geist-sans", subsets: ["latin", "latin-ext"] });

export const metadata: Metadata = {
  title: "Menaxheri i Shpenzimeve të Shtëpisë",
  description: "Kontroll dixhital i parave cash të shtëpisë",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Shpenzimet", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-192.png" },
};

export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#059669" }, { media: "(prefers-color-scheme: dark)", color: "#0b1210" }],
  width: "device-width",
  initialScale: 1,
};

const themeScript = `try{var m=localStorage.getItem('theme');if(m==='dark'||(!m&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="sq" className={`${geist.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
