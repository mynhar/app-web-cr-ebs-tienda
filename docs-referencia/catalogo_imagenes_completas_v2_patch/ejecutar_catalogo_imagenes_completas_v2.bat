@echo off
setlocal
cd /d "%~dp0"
echo Instalando dependencias necesarias...
py -m pip install -r requirements_catalogo_imagenes_v2.txt
py -m playwright install chromium
echo.
echo Generando catalogo con imagenes incrustadas, precios IVA+Margen y enlaces fabricante...
py generar_catalogo_final_con_imagenes_pdf_v2.py --deep-image-discovery --headful
pause
