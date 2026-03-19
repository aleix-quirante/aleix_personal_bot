# Guía de Uso: OpenClaw

Aleix, a partir de ahora vamos a pivotar hacia el uso del framework oficial de la comunidad, **OpenClaw**. Esto reemplazará el desarrollo manual que estábamos haciendo en el archivo `bot.py` (el cual conservaremos sólo por si acaso, congelando ese entorno).

## Conceptos Clave

1. **Gateway**: OpenClaw funciona mediante un "Gateway", lo que nos permitirá conectar nuestra lógica centralizada y los modelos de IA con múltiples canales y proveedores de forma estandarizada.
2. **CLI**: Ahora usaremos la interfaz de línea de comandos oficial. Para arrancar el proyecto o ejecutar tareas, usarás comandos de su CLI (como `npx openclaw`).

## Canales Listos para Usar

La integración con **WhatsApp** y **Telegram** ya viene preconfigurada de fábrica en este software. No necesitamos reinventar la rueda; bastará con configurar nuestras credenciales en los archivos correspondientes del entorno de OpenClaw y el sistema levantará esos canales automáticamente.

*Nota: La carpeta `openclaw` ya ha sido clonada en este repositorio.*