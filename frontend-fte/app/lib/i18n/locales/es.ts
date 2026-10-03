/**
 * Spanish translation dictionary.
 *
 * Same scope as en.ts — see that file's header comment. Any key missing
 * here silently falls back to English rather than breaking the page.
 */
import type { TranslationKey } from "./en";

const es: Partial<Record<TranslationKey, string>> = {
  "common.language": "Idioma",
  "common.retry": "Reintentar",
  "common.loading": "Cargando…",
  "common.days_7": "7 días",
  "common.days_30": "30 días",
  "common.days_90": "90 días",

  "analytics.title": "Ingresos y análisis",
  "analytics.subtitle": "Datos reales de los pedidos sincronizados de {{storeName}} — nada estimado.",
  "analytics.period_label": "Período",
  "analytics.revenue": "Ingresos",
  "analytics.orders": "Pedidos",
  "analytics.average_order_value": "Valor promedio del pedido",
  "analytics.vs_previous_period": "vs. período anterior",
  "analytics.no_previous_data": "Aún no hay datos del período anterior",
  "analytics.trend_title": "Tendencia de ingresos",
  "analytics.trend_empty": "Aún no se registraron ingresos en este período.",
  "analytics.top_products_title": "Productos más vendidos por ingresos",
  "analytics.top_products_empty": "Aún no hay ventas de productos en este período.",
  "analytics.table_product": "Producto",
  "analytics.table_units_sold": "Unidades vendidas",
  "analytics.table_revenue": "Ingresos",
  "analytics.order_status_title": "Pedidos por estado",
  "analytics.order_status_empty": "Aún no hay pedidos en este período.",
  "analytics.error_loading": "No se pudieron cargar los datos de análisis.",
  "analytics.no_store": "Conecta una tienda para ver el análisis de ingresos.",
};

export default es;
