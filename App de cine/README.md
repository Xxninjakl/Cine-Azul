# CineAzul

Aplicación de escritorio para organizar y reproducir tu colección de películas. Está hecha con Python y Tkinter; la base de datos usa SQLite, incluido con Python.

## Iniciar

1. Instala Python 3.10 o posterior.
2. Instala Pillow para mostrar portadas JPG, redimensionar imágenes y usar un fondo personalizado:

   ```powershell
   py -m pip install Pillow
   ```

3. Ejecuta la app desde esta carpeta:

   ```powershell
   py cine_azul.py
   ```

Para abrirla sin una ventana de terminal y mantenerla independiente de VS Code, abre `iniciar_cineazul.vbs` con doble clic. `iniciar_cineazul.bat` también usa `pyw` o `pythonw.exe`, que ejecutan la ventana sin consola. La plantilla `plantilla_peliculas.csv` muestra los encabezados para importar varias películas.

Si no instalas Pillow, todavía puedes añadir películas; Tkinter mostrará los formatos de imagen que admita tu instalación.

## Funciones

- Barra de título nativa para mover y redimensionar la ventana con estabilidad; en Windows 11 usa el azul del tema de CineAzul.
- Añadir películas con título, año, género, director, calificación y sinopsis.
- Vincular un archivo de video y una portada desde el equipo.
- Hacer clic en la portada o ficha para abrir el video. CineAzul busca VLC; si no lo encuentra, usa la aplicación asociada al archivo en Windows, o el reproductor predeterminado en macOS/Linux.
- Buscar por título, año, género o director, y editar una ficha desde su tarjeta.
- Cambiar entre tema oscuro y claro, ambos con acentos azules.
- Abrir el menú lateral animado con el botón ☰ para acceder a la biblioteca y la personalización.
- Elegir una imagen propia como fondo; la elección y el tema se conservan al volver a abrir la app. Los fondos personalizados requieren Pillow.
- Animaciones suaves en la apertura del menú y en los botones.
- Abrir otra base SQLite creada por CineAzul.
- Importar y exportar CSV. Los encabezados aceptados incluyen `titulo`, `año`, `genero`, `director`, `calificacion`, `sinopsis`, `archivo` y `portada` (también se aceptan los nombres en inglés equivalentes). Para vincular archivos durante la importación, incluye rutas absolutas en las columnas `archivo` y `portada`.

La base de datos inicial se guarda en la carpeta de datos del usuario: `%LOCALAPPDATA%\CineAzul\peliculas.db` en Windows, `~/Library/Application Support/CineAzul/peliculas.db` en macOS, o `~/.local/share/CineAzul/peliculas.db` en Linux (salvo que `XDG_DATA_HOME` esté definido).
