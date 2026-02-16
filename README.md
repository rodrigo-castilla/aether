# ☁️ Aether: Serverless LAN Shared Memory

> **Slogan:** "Variables que flotan en el aire. Sincronización de estado Zero-Config para Python."
> **Estado:** 🚧 Fase de Diseño
> **Stack:** Python 3.10+, Sockets (UDP/TCP), JSON, Threading/Asyncio.

## ⚠️Disclaimer⚠️
Project in development

## 1. 🎯 Visión y Alcance
**El Problema:** Compartir datos entre scripts (PC, Raspberry Pi, Server) requiere configurar Redis/MQTT, abrir puertos y gestionar IPs. Es lento y tedioso.
**La Solución:** Un SDK que usa la red local (LAN) como memoria RAM compartida. Los dispositivos se autodescubren y sincronizan diccionarios automáticamente.

**Casos de Uso:**
- Domótica DIY (Sensores escriben, actuadores leen).
- Configuración distribuida (Cambiar flags en tiempo real).
- Chat simple P2P.

## 2. 🏗️ Arquitectura del Sistema
### Topología
El sistema funciona como una **Red Mesh (Malla)** no estructurada. No hay nodo maestro. Todos los nodos son iguales (Peers).

[Aquí insertarás un diagrama de Nodos interconectados]

### El Protocolo "Gossip" (Cotilleo)
1.  **Discovery (UDP):** "¡Hola! Estoy aquí y tengo la versión de datos X".
2.  **Sync (TCP):** "Tus datos son viejos, toma estos cambios".
3.  **Heartbeat:** "Sigo vivo".

## 3. 💾 Modelo de Datos (El Estado)
Aether no guarda strings simples. Guarda **Átomos de Estado** para resolver conflictos.

**Estructura del Almacén (Store):**
```json
{
  "temperatura_salon": {
    "value": 24.5,
    "timestamp": 1708992300.5,  // UNIX Time preciso
    "node_id": "rasp-pi-01"     // Quién lo escribió
  },
  "luces_on": {
    "value": true,
    "timestamp": 1708992305.1,
    "node_id": "pc-main"
  }
}
```

## 4. Funcionamiento del Flujo de Datos
### Diálogo
Supongamos la siguiente "discusión entre ordenadores" que usan Aether y comparten el recurso "source":
1 -> Oye! en *source* he añadido esta información en el id=X
2 -> Recibido! totalmente actualizado
### "Under the Hood"
1. Script base *Aether* corriendo en segundo plano.

2. *Aether* utiliza hilos para funcionar en escucha y escritura a la par.

3. Cuando el usuario ejecuta `db["source"] = "data"`, el método mágico `__setitem__` de la clase `Aether` intercepta la operación. No se guarda solo el valor "data", sino que se captura el **Timestamp preciso** (`time.time()`) y el **Node UUID** (identificador único del dispositivo).

4. Se crea un objeto "Átomo" en memoria: `{"key": "source", "val": "data", "ts": 170899.55, "node": "PC-01"}`.
    Este diccionario se serializa a **JSON String** y luego se codifica a **Bytes** (`utf-8`).

5. Antes de salir de la RAM, el payload de bytes se pasa por el motor de cifrado **Fernet** usando la `secret_key` compartida.
    El resultado es un bloque de bytes ininteligible para cualquier dispositivo que no tenga la llave (sniffers, vecinos, etc.).

6. El socket de _Aether_ envía el paquete cifrado a la dirección de broadcast `255.255.255.255` en el puerto configurado (ej: 5000).
    El router replica este paquete y lo entrega a **todos** los dispositivos conectados a la red local física.

7. En el "Ordenador 2", el hilo `daemon` que estaba bloqueado en `socket.recv()` se despierta al recibir los bytes.
    **Filtrado:** Intenta descifrar el paquete con su copia de la `secret_key`. Si falla (clave incorrecta o paquete corrupto), lo descarta silenciosamente.

8. Si el descifrado es exitoso, deserializa el JSON.
    Compara el `ts` (timestamp) recibido con el `ts` que ya tiene en su memoria local para la clave "source".
    **Lógica:** ¿Es el paquete entrante más nuevo que lo que yo sé?   
	- **SÍ:** Sobrescribo mi memoria local.
	- **NO:** Ignoro el paquete (es información vieja que llegó tarde).

9. El diccionario interno del "Ordenador 2" se actualiza.
    Si el usuario definió un decorador `@on_change("source")`, se dispara la función asociada en el hilo principal.

# POC (Proof Of Concept)
```python
# file: test.py
import aether, sys, os, json, socket, code

def initialization():
    # ---------- json folder path -------------
    pathjsonfolder = "./json"

    pathpc = os.path.join(os.getcwd(), sys.argv[1])
    # Create pc folder
    if not os.path.exists(pathpc):
        os.mkdir(pathpc)

    try:
        from IPython import embed
        HAS_IPYTHON=True
        print(f"Initialized cmdline with IPython\n")
    except ImportError:
        import code
        HAS_IPYTHON=False
        print(f"Initialized cmdline with code\n")
    
    return HAS_IPYTHON

# ---------- MAIN ------------
if __name__=="__main__":
    if len(sys.argv) < 2:
        print("❌ Usage: python test_diagram.py [pcX]")
        sys.exit(1)

    cmdinteractive = initialization()

    banner=f"""
    ======================================
    |           CMD-Inline               |
    ======================================
    """
    with aether.Aether() as ae:
        if cmdinteractive:
            from IPython import embed
            # PRO console 
            embed(
                colors="neutral",
                banner1=banner,
                user_ns=locals() # Pasamos las variables locales (ae, pool, touch)
            )
        else:
            # Fallback if not installed IPython
            print(banner)
            print("⚠️ AVISO: Instala 'ipython' para tener autocompletado y colores.")
            code.interact(local=locals(), banner="")
``` 

# Instalación

```python
pip install git+https://github.com/rodrigo-castilla/aether.git
```

Check if is installed succesfully
```python
pip list # check if appears "aether-sdk" 
```

# Desinstalación
```python
pip uninstall aether-sdk
```

# Extensiones
- Ampliar más allá de LAN (poder añadir "parametros" para acceso a subredes, ACL etc)
- Poder crear una interfaz para que optimice aun mas ya que no tiene que pasar por red fisica y cada uno de los dispositivos, sino broadcast de la nueva interfaz

