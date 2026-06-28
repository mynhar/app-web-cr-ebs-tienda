// calPrecioCliente.ts
// Cálculo del precio final al cliente para Costa Rica EBS.
//
// Orden correcto del cálculo: costo → margen → IVA.
// Reglas:
//   - El costo base es el precio del producto en Intcomex (en US$).
//   - El IVA (13%) que el proveedor le cobra a EBS NO es un costo: es crédito
//     fiscal que se recupera, así que se IGNORA para fijar el precio.
//   - El margen de ganancia (30%) se aplica sobre el costo base (sin IVA del proveedor).
//   - El IVA al cliente (13%) se aplica UNA sola vez, de último, sobre el precio
//     con margen (SubTotal).
//
//   SubTotal (venta sin IVA) = precioBase * 1.30
//   IVA al cliente           = SubTotal * 0.13
//   Precio Total al Cliente  = SubTotal * 1.13 = precioBase * 1.469

/** Constantes de negocio. */
const MARGEN = 0.30; // 30% de margen de ganancia
const IVA = 0.13;    // 13% de IVA (Costa Rica)

/**
 * Tipo de cambio de Intcomex (₡ por US$). El catálogo de Intcomex está en dólares
 * y este es el tipo de cambio que Intcomex usa para mostrar los colones. En la tienda
 * se deriva automáticamente del catálogo; aquí queda como valor por defecto.
 */
export const TIPO_CAMBIO_INTCOMEX = 456;

/** Un monto expresado en dólares y en colones. Los colones NO se redondean. */
export interface Monto {
  usd: number;      // monto en dólares, sin redondear
  crc: number;      // monto en colones, sin redondear (= usd * tipo de cambio)
  crcTexto: string; // colones formateados con al menos 2 decimales (para mostrar)
}

/** Resultado del cálculo del precio al cliente. */
export interface PrecioCliente {
  subtotal: Monto;     // precio de venta con margen, SIN IVA
  iva: Monto;          // IVA que se le cobra al cliente (débito fiscal)
  totalCliente: Monto; // precio total al cliente (= precioBase * 1.469)
  ivaARemitir: Monto;  // IVA a pagar a Hacienda = débito fiscal − crédito fiscal
}

/**
 * Calcula el precio final al cliente a partir del costo base (precio Intcomex en US$).
 *
 * @param precioBase  Costo base en dólares (precio del producto en Intcomex).
 * @param tipoCambio  Tipo de cambio ₡/US$ de Intcomex (por defecto TIPO_CAMBIO_INTCOMEX).
 * @returns Desglose con subtotal, IVA, total al cliente e IVA a remitir; cada monto
 *          en dólares y colones (colones sin redondear, con 2 decimales al mostrar).
 */
export function calPrecioCliente(
  precioBase: number,
  tipoCambio: number = TIPO_CAMBIO_INTCOMEX,
): PrecioCliente {
  // costo → margen → IVA
  const subtotal = precioBase * (1 + MARGEN); // precio con margen 30%, sin IVA
  const iva = subtotal * IVA;                 // IVA al cliente (débito fiscal)
  const totalCliente = subtotal + iva;        // = precioBase * 1.469

  // El IVA pagado al proveedor (13% sobre el costo base) es crédito fiscal: se recupera,
  // por eso no entra en el precio. A Hacienda se le remite el débito menos ese crédito.
  const creditoFiscal = precioBase * IVA;
  const ivaARemitir = iva - creditoFiscal;

  // Convierte un monto en US$ a {usd, crc, crcTexto}. Los colones no se redondean;
  // crcTexto los muestra con al menos 2 decimales (formato de Costa Rica).
  const aMonto = (usd: number): Monto => {
    const crc = usd * tipoCambio;
    return {
      usd,
      crc,
      crcTexto: crc.toLocaleString("es-CR", { minimumFractionDigits: 2 }),
    };
  };

  return {
    subtotal: aMonto(subtotal),
    iva: aMonto(iva),
    totalCliente: aMonto(totalCliente),
    ivaARemitir: aMonto(ivaARemitir),
  };
}

// Ejemplo (precio base US$0.83, tipo de cambio Intcomex 456):
//   subtotal.usd     = 1.079      subtotal.crc     = 492.024
//   iva.usd          = 0.14027    iva.crc          = 63.96312
//   totalCliente.usd = 1.21927    totalCliente.crc = 555.98712   (US$1.22 redondeado)
//   ivaARemitir.usd  = 0.03237    ivaARemitir.crc  = 14.76072
