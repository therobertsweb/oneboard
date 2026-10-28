# Revisión de integración entre secciones

## Flujo de trabajo

1. Selecciona la carpeta en Studio. En Configuración del sitio, guarda la web pública, la marca y, si corresponde, su propiedad de Search Console.
2. El análisis local detecta páginas incompletas, enlaces rotos y problemas de formularios. Desde esa sección puedes aplicar correcciones o pedir ayuda a la IA.
3. Seguridad propone el dominio configurado. Un análisis de ese dominio queda vinculado al proyecto; «Preparar correcciones en Studio» lleva sus hallazgos al editor. Revisa la tarea y envíala para editar los archivos con respaldo e historial.
4. Después de una edición en Studio se repite el análisis local sin consultar enlaces externos. Las sugerencias sociales vuelven a leer el contenido actual al abrir la sección.
5. Publica los cambios cuando corresponda y repite el análisis del dominio para verificar el sitio público. Las ediciones locales no renuevan certificados ni cambian DNS o configuraciones externas por sí solas.

## Problemas corregidos

- Las sugerencias sociales omitían la primera página: ahora incluyen la portada, incluso en sitios de una sola página sin marca configurada.
- El historial social mezclaba proyectos: las nuevas publicaciones guardan la carpeta y se consultan por proyecto. Los registros anteriores se conservan en «Publicaciones anteriores sin proyecto», sin asignarlos arbitrariamente.
- Seguridad estaba aislada: los resultados nuevos del dominio configurado se vinculan a la carpeta y se incluyen en el contexto de Studio. Analizar otro dominio no autoriza editar el proyecto activo a partir de ese resultado.
- El editor directo solo recibía la marca: ahora recibe también páginas, hallazgos, análisis de seguridad vinculado, eventos y cambios recientes. Cada sección tiene un límite para que páginas largas no eliminen los demás datos del contexto.
- Los hallazgos locales podían quedar desactualizados tras editar en Studio: ahora se reanaliza la carpeta después de una edición exitosa. Si el análisis falla, la respuesta incluye `terminal.health_warning`; la edición conserva su historial y respaldo.
- Las pestañas antiguas podían ejecutar acciones sobre otro proyecto: los formularios de Studio/análisis y las peticiones sociales envían la carpeta esperada. Los flujos protegidos comprueban la carpeta y mantienen el bloqueo de operación durante las llamadas de IA y publicación. Los clientes API antiguos que no envían ese campo conservan su comportamiento.
- Los informes podían usar la propiedad de Search Console elegida a nivel de cuenta para otro cliente: ahora solo consultan la propiedad guardada en el proyecto.
- Se añadió una cabecera común con el proyecto y accesos entre Studio, análisis local, Seguridad, Social y Configuración en las secciones de trabajo relacionadas.

## Alcance de la verificación

Pruebas de integración con archivos y base de datos temporales cubren el recorrido edición → análisis → sugerencias, el respaldo, la separación entre proyectos, los registros anteriores, el rechazo de pestañas antiguas y la vinculación de análisis por dominio y carpeta. Se comprueba también el renderizado de las páginas y el funcionamiento existente de Studio, equipos, marca, informes y Buffer.

Las respuestas de IA y servicios externos se simulan en estas pruebas: no se publican posts, no se despliegan archivos y no se cambian DNS ni certificados. La comprobación visual interactiva y una ejecución real con las credenciales del usuario siguen siendo comprobaciones de entorno, no resultados garantizados por estos tests.

Las migraciones añaden columnas a los historiales social y de seguridad al iniciar la aplicación. No eliminan registros. Los análisis antiguos no se vinculan automáticamente porque no registraron la carpeta del proyecto.
