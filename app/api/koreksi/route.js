import { gerbangKoreksi } from "@/lib/gerbang";
import { bacaKoreksi, tulisKoreksi } from "@/lib/berkas";

/* Baca dan tulis koreksi manual.
 *
 * KEDUANYA lewat gerbangKoreksi(), bukan hanya yang menulis. Daftar koreksi
 * memperlihatkan baris mana yang angkanya diragukan, dan itu bukan sesuatu
 * yang perlu dibaca semua member.
 */
export const dynamic = "force-dynamic";

function tolak(izin) {
  return Response.json(
    { galat: izin.galat || "Tidak diizinkan.", sebab: izin.sebab },
    { status: izin.sebab === "belum-masuk" ? 401 : 403 }
  );
}

export async function GET() {
  const izin = await gerbangKoreksi();
  if (!izin.boleh) return tolak(izin);
  return Response.json(await bacaKoreksi(), {
    headers: { "cache-control": "no-store" },
  });
}

export async function POST(req) {
  const izin = await gerbangKoreksi();
  if (!izin.boleh) return tolak(izin);

  let isi;
  try {
    isi = await req.json();
  } catch {
    return Response.json({ galat: "Bukan JSON yang sah." }, { status: 400 });
  }
  if (!isi || typeof isi !== "object" || Array.isArray(isi)) {
    return Response.json({ galat: "Isi harus objek." }, { status: 400 });
  }

  /* Pemeriksaan bentuk, bukan sekadar percaya kiriman. Satu nilai yang bukan
     angka akan menyebar ke seluruh statistik sebagai NaN dan baru ketahuan
     berhari-hari kemudian sebagai kolom kosong yang tidak jelas sebabnya. */
  const ANGKA = ["entry", "entryAtas", "tp1", "tp2", "tp3", "tp4", "sl", "persen"];
  const STATUS = ["ongoing", "TP1", "TP2", "TP3", "TP4", "SL", "BEP", "Closed"];
  const bersih = {};
  for (const [kunci, nilai] of Object.entries(isi)) {
    if (typeof kunci !== "string" || kunci.split("|").length !== 3) {
      return Response.json({ galat: `Kunci tidak sah: ${kunci}` }, { status: 400 });
    }
    if (!nilai || typeof nilai !== "object") continue;
    const baris = {};
    for (const [f, v] of Object.entries(nilai)) {
      if (ANGKA.includes(f)) {
        const n = Number(v);
        if (!Number.isFinite(n)) {
          return Response.json({ galat: `${kunci}: ${f} bukan angka` }, { status: 400 });
        }
        baris[f] = n;
      } else if (f === "status") {
        if (!STATUS.includes(v)) {
          return Response.json({ galat: `${kunci}: status "${v}" tidak dikenal` }, { status: 400 });
        }
        baris[f] = v;
      } else if (f === "dibatalkan") {
        baris[f] = !!v;
      } else if (f === "catatan" || f === "timeframe") {
        baris[f] = String(v).slice(0, 200);
      }
      /* Bidang lain dibuang diam-diam: kiriman tidak boleh menambah bidang
         baru ke dataset hanya dengan mengirimnya. */
    }
    if (Object.keys(baris).length) bersih[kunci] = baris;
  }

  const n = await tulisKoreksi(bersih);
  return Response.json({ ok: true, jumlah: n, oleh: izin.nama || izin.userId });
}
