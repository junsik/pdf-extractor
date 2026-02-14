import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { AuthProvider } from "@/lib/auth";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RegistryParser - 등기부등본 PDF 파싱 서비스",
  description: "등기부등본 PDF를 업로드하면 표제부, 갑구, 을구를 자동 분석. 말소사항까지 완벽하게 추적합니다.",
  keywords: ["등기부등본", "PDF 파싱", "부동산", "갑구", "을구", "말소사항"],
  authors: [{ name: "RegistryParser Team" }],
  icons: {
    icon: "/logo.svg",
  },
  openGraph: {
    title: "RegistryParser - 등기부등본 PDF 파싱 서비스",
    description: "등기부등본 PDF를 업로드하면 표제부, 갑구, 을구를 자동 분석",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        <AuthProvider>
          {children}
        </AuthProvider>
        <Toaster />
      </body>
    </html>
  );
}
