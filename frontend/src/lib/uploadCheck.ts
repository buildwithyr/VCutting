/**
 * Voruebergehende Pruefung im Browser.
 *
 * Verbindlich ist die serverseitige Pruefung: dort wird der tatsaechliche
 * Dateiinhalt gelesen, nicht der vom Browser gemeldete MIME-Type.
 */

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
export const ACCEPTED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp'];

export function describeUploadProblem(file: File): string | null {
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  const typeOk = ACCEPTED_TYPES.includes(file.type);
  const extensionOk = ACCEPTED_EXTENSIONS.includes(extension);
  if (!typeOk && !extensionOk) {
    return `"${file.name}" wird nicht unterstuetzt. Erlaubt sind PNG, JPG und WebP.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `Die Datei ist ${(file.size / 1024 / 1024).toFixed(1)} MB gross. Erlaubt sind hoechstens 20 MB.`;
  }
  if (file.size === 0) {
    return 'Die Datei ist leer.';
  }
  return null;
}
