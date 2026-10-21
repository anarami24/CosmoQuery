# CosmoQuery — Cómo iniciar la aplicación

CosmoQuery es una aplicación web para responder preguntas en inglés sobre astronomía utilizando documentos de la NASA.

## Pasos para ejecutarla

1. Abrir una terminal en la carpeta `CosmoQuery`.
2. Instalar las dependencias (solo la primera vez):

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Iniciar la aplicación:

   ```bash
   python app.py
   ```

4. Abrir en el navegador la dirección local que aparezca en la terminal.

## Uso

Escribir una pregunta **en inglés**, seleccionar búsqueda **exacta** o **aproximada** y hacer clic en **Preguntar**. La interfaz permite ver la respuesta, su fuente y los fragmentos recuperados. También cuenta con autocompletado y una opción para comparar algoritmos.

**Notas:** La primera ejecución puede tardar porque se descarga el modelo de Hugging Face; se necesita conexión a internet. El ZIP ya contiene el índice de búsqueda. Si la aplicación indica que falta el índice, ejecutar `python index_builder.py` y volver a iniciar `python app.py`.
