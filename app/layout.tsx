import type { Metadata } from "next";
import { Press_Start_2P } from "next/font/google";
import "./globals.css";

const pixel = Press_Start_2P({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-pixel",
});

export const metadata: Metadata = {
  title: "ModelMaker3D",
  description: "画像・複数視点・テキストから3Dモデル(GLB/FBX)を生成するローカルツール",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja" className={`${pixel.variable} h-full antialiased`}>
      <head>
        {/* GLB プレビュー用 model-viewer (Google) */}
        <script
          type="module"
          src="https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js"
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
