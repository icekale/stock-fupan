import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "A 股每日复盘",
  description: "本地 A 股复盘生成工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
