import { redirect } from "next/navigation";
import { gerbang } from "@/lib/gerbang";
import MasukDiscord from "@/components/MasukDiscord";

/* force-dynamic WAJIB. Tanpa itu Next.js akan merender halaman ini sekali saat
   build dan menyajikan hasil yang sama ke semua orang - termasuk hasil "sudah
   masuk" kepada pengunjung yang belum punya sesi. */
export const dynamic = "force-dynamic";

export default async function Halaman({ searchParams }) {
  const sp = await searchParams;
  const izin = await gerbang();
  if (izin.boleh) redirect("/dasbor");
  return <MasukDiscord sebab={izin.sebab} galat={izin.galat || sp?.galat} />;
}
