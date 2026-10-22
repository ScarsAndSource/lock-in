/** The backend rejects images over ~4 MB. Big phone screenshots get re-encoded as a JPEG; small ones go untouched. */
export const MAX_UPLOAD_IMAGE_BYTES = 3_800_000;

export async function shrinkImageIfNeeded(file: File): Promise<Blob> {
  if (file.size <= MAX_UPLOAD_IMAGE_BYTES) return file;
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1800 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
  if (!blob || blob.size > MAX_UPLOAD_IMAGE_BYTES) throw new Error('That image is too large. Use a normal screenshot.');
  return blob;
}
