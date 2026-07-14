/**
 * Dashboard Electoral — Boyacá 2026 · UTL Senado · Reto 4
 * Sirve el archivo HTML "dashboard" como aplicación web.
 *
 * Estructura del proyecto en Apps Script:
 *   - Código.gs      → SOLO este código de servidor
 *   - dashboard.html → todo el dashboard (datos y librerías incluidos)
 */

function doGet() {
  return HtmlService.createHtmlOutputFromFile('dashboard')
    .setTitle('Dashboard Electoral · Boyacá 2026 — UTL Senado')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
