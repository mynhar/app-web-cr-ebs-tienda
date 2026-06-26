Costa Rica EBS S.A. - Correccion de imagenes incompletas

Uso:
1. Copie estos archivos dentro de la carpeta del paquete anterior:
   - generar_catalogo_final_con_imagenes_pdf_v2.py
   - ejecutar_catalogo_imagenes_completas_v2.bat
   - requirements_catalogo_imagenes_v2.txt

2. Confirme que en la misma carpeta existan:
   - productos_intcomex_ebs_final_iva13_margen30.json
   - portada_catalogo_tecnologia_2026.png
   - logo_costa_rica_ebs.png
   - pass.txt, opcional, solo localmente si desea login automatico

3. Ejecute:
   ejecutar_catalogo_imagenes_completas_v2.bat

Que corrige esta version:
- No usa el PDF anterior con placeholders.
- Genera el PDF directamente con ReportLab e incrusta las imagenes locales.
- Recalcula precio final con formula: precio Intcomex USD x 1.13 x 1.30.
- Muestra solo precio final USD y CRC.
- Muestra stock solo como cantidad de unidades, sin ubicacion.
- Usa enlace de "Ficha fabricante" hacia busqueda/ficha oficial del fabricante por MPN/modelo.
- Genera reporte_imagenes_catalogo.csv para ver que SKUs no tienen imagen real disponible.

Salidas:
- catalogo_costa_rica_ebs_final_iva13_margen30_imagenes_completas.pdf
- catalogo_costa_rica_ebs_final_iva13_margen30_imagenes_completas.html
- reporte_imagenes_catalogo.csv
- productos_catalogo_actualizado_imagenes.json

Notas:
- Algunos productos en Intcomex vienen con noimage o con imagen no disponible. El script intenta recuperar imagen desde la pagina de detalle. Si aun asi no existe imagen real, quedara en el reporte CSV.
- No incluya pass.txt en envios ni ZIPs. Mantengalo solo en su PC y elimine o cambie la clave tras pruebas.
