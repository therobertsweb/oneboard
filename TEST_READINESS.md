# Revisión de preparación para pruebas

## Resultado

Se revisaron rutas de edición y vista previa de sitios, entradas JSON, solicitudes entre orígenes, contexto de proyecto seleccionado, ejecución de eventos, límites de archivos y flujos de error. Se corrigieron fallos detectados en esas áreas y se añadieron regresiones en `tests/test_readiness.py`.

## Validación local

- 198 pruebas de 18 módulos pasaron al ejecutarse por módulo.
- `node --check static/js/preview-picker.js` pasó.
- `git diff --check` pasó.
- La ejecución conjunta de todos los módulos no es válida en el estado actual del harness: los tests fijan `ONEBOARD_DATA_DIR` durante la importación, pero comparten el módulo `app` en el mismo proceso. Por eso la ruta de SQLite queda ligada a un único directorio temporal que otros módulos limpian. En procesos separados todos los módulos pasan.

## Límites de esta revisión

Esto no demuestra que el producto esté libre de errores. No se probaron credenciales ni servicios externos reales (IA/Muse, Google, Buffer, SMTP o despliegue SSH/SFTP), ni una sesión completa en navegador con integraciones activadas. La comprobación JavaScript valida sintaxis, no interacciones visuales automatizadas.

## Recomendaciones antes de una prueba con usuarios

1. Probar en un entorno de staging con cuentas y claves de prueba, sin datos de producción.
2. Añadir pruebas E2E de navegador para selección de directorio, edición/preview, publicación y permisos de roles.
3. Aislar la base SQLite/configuración por test para que `unittest discover` pueda correr toda la suite en un único proceso y conservar el mismo resultado.
4. Definir un checklist de recuperación: copia de seguridad, restauración y verificación de cambios de sitio.
