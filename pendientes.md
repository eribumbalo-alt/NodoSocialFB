# PENDIENTES — Nodo Social

Ultima actualizacion: 2026-08-03

Este archivo existe para poder retomar el proyecto sin tener que
reconstruir el contexto de memoria. Cuando termines algo, borralo
de aca.

---

## Al volver a tener maquina

En este orden. No saltear pasos: cada uno verifica algo distinto.

```powershell
# 1. Traer los cambios del repositorio
git pull

# 2. Instalar la libreria nueva
pip install openai

# 3. Recrear el .env (NO esta en el repositorio, se perdio)
#    Copiar .env.ejemplo como .env y completar la API key
```

Despues, las tres pruebas, una por vez:

```powershell
# A. Conexion con NVIDIA (3 llamadas, no toca nada mas)
python scripts/proveedor.py

# B. Filtro local (no usa internet ni IA)
python scripts/filtro_rapido.py

# C. Captura de Facebook (no usa IA ni Sheets)
python scripts/rastrear_grupos.py --prueba
```

Si alguna falla, resolverla antes de seguir con la siguiente.

---

## Pendiente 1 — Actualizar categorias en el clasificador

**Estado:** sin hacer
**Archivo:** `scripts/clasificador_ia.py`

El `categorias.json` nuevo tiene tres categorias que el codigo
todavia no conoce:

- `Acequias`
- `Riego`
- `Otra jurisdicción`

Hay que agregarlas al `Literal` de la clase `ClasificacionReclamo`.
Si no, el modelo no puede devolverlas y Pydantic rechaza la respuesta.

Ademas, `construir_categorias()` lee el formato viejo
(`categorias[nombre]["subcategorias"]`). El archivo nuevo tiene otra
estructura: `datos["categorias"][nombre]` con `definicion`,
`incluye`, `no_incluye` y `terminos`.

Hay que reescribir esa funcion para que arme el bloque de categorias
usando `definicion` y sobre todo `no_incluye`, que es lo que mas
mejora la clasificacion.

---

## Pendiente 2 — Conectar proveedor.py al clasificador

**Estado:** sin hacer
**Archivos:** `scripts/clasificador_ia.py`

Hoy el clasificador llama a Ollama directamente. Hay que reemplazar
esa llamada por `proveedor.completar(...)`, que ya maneja reintentos,
limite de velocidad y el cambio entre NVIDIA y Ollama.

Se hace despues del Pendiente 1, y se prueba solo, para saber que
cambio causa que.

---

## Pendiente 3 — Enchufar el filtro en el scraper

**Estado:** sin hacer
**Archivo:** `scripts/rastrear_grupos.py`

`filtro_rapido.filtrar()` tiene que correr entre la captura y la
clasificacion, para no gastar llamadas a la API en ventas y saludos.

Despues de la primera corrida real, revisar
`data/descartes_filtro.jsonl`. Si hay reclamos ahi adentro, el filtro
esta descartando de mas y hay que suavizar la señal que los atrapo.

---

## Pendiente 4 — Usar ubicaciones.json

**Estado:** sin hacer
**Archivos:** `knowledge/ubicaciones.json`, `scripts/clasificador_ia.py`

El archivo esta creado pero nadie lo lee. Hay que sumar la lista de
distritos y barrios al prompt, con la regla de no inventar ubicaciones.

Idealmente tambien validar despues: si el modelo devuelve una
ubicacion que no esta en la lista, vaciar el campo.

---

## Pendiente 5 — Campo interpela_gestion

**Estado:** sin hacer

`categorias.json` define este campo pero el esquema de respuesta no lo
tiene. Hay que agregarlo como booleano en `ClasificacionReclamo`, y
como columna en las dos hojas de `guardar_sheet.py`.

Regla: solo puede ser verdadero cuando `es_reclamo` es verdadero.

---

## Pendiente 6 — Limpiar el dataset viejo

**Estado:** sin hacer

Las 30 validaciones que hay en `memoria_clasificador.json` se armaron
cuando el scraper capturaba comentarios sueltos con basura de interfaz
("Aaron Briisa · 20 h · Responder · Compartir"). No sirven como
ejemplos.

Correr `python scripts/revisar_memoria.py` para ver cuantas se salvan.
Lo mas probable es que haya que empezar el dataset de cero con
capturas limpias. No es un retroceso: recien ahi vas a estar
entrenando con material real.

---

## Pendiente 7 — Set de evaluacion congelado

**Estado:** sin hacer

Antes de meter ejemplos validados en la memoria, apartar un 30% que
NUNCA entre al prompt. Es la unica forma de medir si la memoria
mejora algo o si el modelo simplemente esta recordando las respuestas.

Se puede hacer con una columna `en_evaluacion` en la hoja Dataset IA.

---

## Decisiones ya tomadas (para no rediscutirlas)

- **Comentarios se analizan**, no solo publicaciones. Van con el texto
  del post padre como contexto, y se clasifica solo el comentario.
- **Los comentarios se detectan por el enlace** (`comment_id=` en la
  URL), no por la estructura del HTML. Facebook cambia el DOM seguido;
  el parametro de la URL es estable.
- **El intendente es un campo, no una categoria.** Un insulto sin
  reclamo concreto es "No corresponde". Marcar por categoria generaria
  una lista de personas identificables en vez de una lista de
  problemas.
- **Acequias y Riego van separados.** Acequia = limpieza del cauce.
  Riego = el agua (derroche, turno, falta).
- **El filtro local es deliberadamente conservador.** Descartar un
  reclamo real cuesta mucho mas que dejar pasar basura.
- **Nunca subir al repositorio:** credenciales, el perfil de
  Playwright, ni datos de vecinos. Ver `.gitignore`.

---

## Cosas a verificar con conocimiento del territorio

En `knowledge/categorias.json` quedaron supuestos que conviene
confirmar:

- **Agua y cloacas** figura como municipal. En varios distritos de
  Maipu presta AYSAM. ¿Se distingue por zona?
- **Riego** quedo como jurisdiccion mixta (municipio limpia la
  acequia, Irrigacion maneja el turno). ¿Es correcto?
- **Las areas sugeridas** son nombres genericos inventados. Si tenes
  los nombres reales de las direcciones del municipio, cambiarlos:
  es la diferencia entre un reclamo derivable y uno que hay que
  reasignar a mano.

---

## Mas adelante

- **Arquitectura en cascada:** primera pasada binaria (¿es reclamo?)
  y extraccion completa solo sobre los positivos. Reduce mucho el
  volumen de llamadas.
- **Calibrar la confianza:** agrupar las validaciones por nivel de
  confianza y ver el acierto real de cada una. Si la curva sube,
  hay umbral para auto-aprobar y se le saca carga al operador.
- **SQLite como fuente de verdad**, con Sheets solo como interfaz de
  validacion. Google Sheets se vuelve lento e inmanejable con miles
  de filas.
- **Trazabilidad:** guardar en cada fila `modelo`, `version_memoria`
  y los ejemplos usados. Permite saber que ejemplos ayudan y cuales
  contaminan.