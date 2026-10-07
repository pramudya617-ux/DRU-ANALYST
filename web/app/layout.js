export const metadata = {
  title: "DRU Analyst",
  description: "Rekam jejak call empat analyst DRU, di balik login Discord.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="id">
      <body style={{ margin: 0, background: "#09090b", color: "#f4f4f5",
        font: "15px/1.5 ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
