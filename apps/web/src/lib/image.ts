const MAX_DIM = 2000;
const QUALITY = 0.82;

export interface Prepared {
  blob: Blob;
  name: string;
  mime: string;
  compressed: boolean;
}

export function scaleDims(w: number, h: number, max = MAX_DIM): { w: number; h: number } {
  const r = Math.min(1, max / Math.max(w, h));
  return { w: Math.round(w * r), h: Math.round(h * r) };
}

/** Compress images client-side and bake in EXIF orientation. PDFs and undecodable files pass through unchanged. */
export async function prepareFile(file: File): Promise<Prepared> {
  const passthrough: Prepared = { blob: file, name: file.name, mime: file.type, compressed: false };
  if (file.type === "application/pdf" || typeof createImageBitmap !== "function") return passthrough;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const { w, h } = scaleDims(bmp.width, bmp.height);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return passthrough;
    ctx.drawImage(bmp, 0, 0, w, h);
    bmp.close?.();
    const blob: Blob | null = await new Promise((r) => canvas.toBlob(r, "image/jpeg", QUALITY));
    if (!blob || blob.size >= file.size * 1.05) return passthrough;
    return { blob, name: file.name.replace(/\.[^.]+$/, "") + ".jpg", mime: "image/jpeg", compressed: true };
  } catch {
    return passthrough;
  }
}
