import socket, sys, threading, uuid, time, json, os
from pathlib import Path

class Aether:
    def __init__(self, port=5000):
        self.port = port
        self.sock = None
        self.running = False
        self.node_id = str(uuid.uuid4())
        self.pool_path = None  # Aquí guardaremos la ruta de la "Piscina"
        print(f"🆔 Nodo UUID: {self.node_id}")

    def __enter__(self):
        self.activate()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return True if exc_type is KeyboardInterrupt else None


    # --- 1. ACTIVACIÓN (SOCKETS) ---
    def activate(self):
        # ... (Igual que antes) ...
        print(f"🔌 Activando en puerto {self.port}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self.sock.bind(('0.0.0.0', self.port))
            self.running = True
        except PermissionError:
            print("❌ Error: Permisos denegados.")
            sys.exit(1)

        listen = threading.Thread(target=self._listen, daemon=True)
        listen.start()


    # --- 2. ESCUCHA Y ESCRITURA EN DISCO ---
    def _listen(self):
        while self.running:
            try:
                if self.sock is None: break
                data_bytes, addr = self.sock.recvfrom(65536) # Buffer grande para archivos
                
                envelope = json.loads(data_bytes.decode('utf-8'))
                sender_id = envelope.get("node", "unknown")
                
                # Ignorar eco (si soy yo mismo)
                if sender_id == self.node_id:
                    continue

                # Procesar el paquete
                filename = envelope.get("filename")   # ej: "config.json"
                payload = envelope.get("payload")     # El contenido (dict)
                remote_ts = envelope.get("ts", 0)     # Cuándo se modificó

                print(f"📨 Recibido '{filename}' de {addr}")

                # Si tenemos un POOL configurado, intentamos guardar en disco
                if self.pool_path and filename:
                    self._save_to_pool(filename, payload, remote_ts, addr)

            except OSError:
                break
            except Exception as e:
                print(f"⚠️ Paquete corrupto o error: {e}")


    # --- 3. CONFIGURACIÓN DEL POOL ---
    def pool(self, path):
        """
        Define el directorio local que funcionará como espejo de datos.
        Crea la carpeta si no existe.
        """
        self.pool_path = Path(path)
        if not self.pool_path.exists():
            self.pool_path.mkdir(parents=True, exist_ok=True)
            print(f"📁 Directorio POOL creado: {self.pool_path.absolute()}")
        else:
            print(f"📁 Directorio POOL vinculado: {self.pool_path.absolute()}")
        
        return self # Para permitir encadenamiento (Fluent Interface)

    def _save_to_pool(self, filename, content, remote_ts, addr, distict=False):
        """
        Lógica LWW (Last Write Wins) para persistencia en disco.
        """
        # SEGURIDAD: Evitar que nos hackeen con rutas relativas (ej: ../../passwords.txt)
        safe_name = os.path.basename(filename)
        if distict:
            pathId = os.path.join(str(self.pool_path), addr)
            self.pool_path = Path(pathId)
        target_file = Path(self.pool_path / safe_name)
        
        should_write = True

        # Si el archivo ya existe localmente, comparamos timestamps
        if target_file.exists():
            local_ts = target_file.stat().st_mtime
            if local_ts >= remote_ts:
                print(f"   ⏭️ Ignorado: Mi versión local de {safe_name} es más nueva o igual.")
                should_write = False
        
        if should_write:
            try:
                with open(target_file, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=4)
                # Actualizamos la fecha de modificación del archivo para coincidir con el remoto
                os.utime(target_file, (remote_ts, remote_ts))
                print(f"   💾 Sincronizado en disco: {safe_name}")
            except Exception as e:
                print(f"   ❌ Error escribiendo archivo: {e}")

    # --- 4. ENVÍO Y SINCRONIZACIÓN ---
    def send(self, data, filename_virtual):
        """
        Envía un dato JSON arbitrario (inline).
        send = sync('path/to/jsonfile.json') more optimized
        """
        self._dispatch(data, filename_virtual, time.time())

    def sync(self, target=None):
        """
        La función mágica del diagrama.
        sync('file.json') -> Lee disco y envía ese archivo.
        sync()            -> Lee el pool COMPLETO y envía todo.
        """
        if not self.pool_path:
            print("❌ Error: Debes definir .pool() antes de usar .sync()")
            return

        if target:
            # Opción A: Sincronizar un archivo específico
            self._sync_file(target)
        else:
            # Opción B: Sincronizar TODO el directorio (El diagrama "sync() --> all the pool")
            print(f"🔄 Sincronizando todo el pool {self.pool_path}...")
            for item in self.pool_path.glob("*.json"):
                if item.is_file():
                    self._sync_file(item.name)

    def _sync_file(self, filename):
        """Lee del disco y empaqueta"""
        file_path = Path(self.pool_path / filename)
        if not file_path.exists():
            print(f"⚠️ No puedo sincronizar {filename}: No existe en disco.")
            return

        try:
            # Leer contenido
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            # Leer fecha de modificación real del archivo
            timestamp = file_path.stat().st_mtime
            
            # Enviar
            print(f"📤 Enviando actualización de: {filename}")
            self._dispatch(content, filename, timestamp)
            
        except Exception as e:
            print(f"❌ Error leyendo {filename}: {e}")

    def _dispatch(self, payload, filename, timestamp):
        """Método interno de bajo nivel para enviar por UDP"""
        if self.sock:
            envelope = {
                "filename": filename,
                "payload": payload,
                "ts": timestamp,
                "node": self.node_id
            }
            msg_bytes = json.dumps(envelope).encode('utf-8')
            self.sock.sendto(msg_bytes, ('255.255.255.255', self.port))

    def close(self):
        self.running = False
        if self.sock:
            self.sock.close()