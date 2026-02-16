import socket, sys, threading, uuid, time, json, os
from pathlib import Path

class Aether:
    def __init__(self, port=5000):
        self.port = port
        self.sock = None
        self.running = False
        self.node_id = str(uuid.uuid4())
        self.node_name = socket.gethostname() # Nombre del dispositivo (ej: "Laptop-Rodrigo")
        
        self.pool_path = None      # Ruta física local
        self.pool_folder_name = "" # Nombre de la carpeta (ej: "mis_datos") para enviarlo
        self.distinct = False      # Modo jerárquico

    def __enter__(self):
        self.activate()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return True if exc_type is KeyboardInterrupt else None

    # --- 1. ACTIVACIÓN (SOCKETS) ---
    def activate(self):
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
                data_bytes, addr = self.sock.recvfrom(65536)
                
                envelope = json.loads(data_bytes.decode('utf-8'))
                sender_id = envelope.get("node_id", "unknown") # Ojo: key corregida a node_id
                
                # Ignorar eco
                if sender_id == self.node_id:
                    continue

                # Extraer datos
                filename = envelope.get("filename")
                payload = envelope.get("payload")
                remote_ts = envelope.get("ts", 0)
                
                # METADATOS NUEVOS PARA DISTINCT
                sender_hostname = envelope.get("hostname", "unknown_host")
                sender_pool_name = envelope.get("pool_name", "default_pool")

                print(f"📨 Recibido '{filename}' de {sender_hostname} ({addr[0]})")

                if self.pool_path and filename:
                    self._save_to_pool(filename, payload, remote_ts, sender_hostname, sender_pool_name)

            except OSError:
                break
            except Exception as e:
                print(f"⚠️ Paquete corrupto o error: {e}")

    # --- 3. CONFIGURACIÓN DEL POOL ---
    def pool(self, path, distinct=False):
        """
        Configura la carpeta espejo.
        :param path: Ruta local "./mi_carpeta"
        :param distinct: Si es True, separa los archivos recibidos por subcarpetas de host.
        """
        self.pool_path = Path(path)
        self.pool_folder_name = self.pool_path.name # Guardamos el nombre "mi_carpeta"
        self.distinct = distinct
        
        if not self.pool_path.exists():
            self.pool_path.mkdir(parents=True, exist_ok=True)
            print(f"📁 Directorio POOL creado: {self.pool_path.absolute()}")
        else:
            print(f"📁 Directorio POOL vinculado: {self.pool_path.absolute()}")
            
        if self.distinct:
            print("   🗂️ Modo DISTINCT activo: Se crearán subcarpetas por dispositivo.")
        
        return self

    def _save_to_pool(self, filename, content, remote_ts, sender_hostname, sender_pool_name):
        """
        Guarda el archivo. Si distinct=True, crea estructura jerárquica.
        """
        safe_name = os.path.basename(filename)
        
        # --- LÓGICA DE RUTAS ---
        if self.distinct:
            # Estructura: POOL / HOSTNAME / POOL_NAME_ORIGEN / archivo.json
            # Ejemplo: ./mis_datos / PC-Rodrigo / json_source / data.json
            final_folder = Path(self.pool_path / sender_hostname / sender_pool_name)
            
            # Crear subcarpetas si no existen
            if not final_folder.exists():
                final_folder.mkdir(parents=True, exist_ok=True)
                
            target_file = Path(final_folder / safe_name)
        else:
            # Estructura Plana (Mezclado): POOL / archivo.json
            target_file = self.pool_path / safe_name
        # -----------------------

        should_write = True

        # LWW (Last Write Wins)
        if target_file.exists():
            local_ts = target_file.stat().st_mtime
            # Si el archivo remoto es más viejo o igual, no sobrescribimos
            # (Salvo que sea distinct, ahí quizás queramos sobrescribir siempre la versión de ESE host)
            if local_ts >= remote_ts:
                # print(f"   ⏭️ Ignorado (Old): {target_file.name}") # Comentado para menos ruido
                should_write = False
        
        if should_write:
            try:
                with open(target_file, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=4)
                os.utime(target_file, (remote_ts, remote_ts))
                print(f"   💾 Guardado en: {target_file}")
            except Exception as e:
                print(f"   ❌ Error escribiendo: {e}")

    # --- 4. ENVÍO Y SINCRONIZACIÓN ---
    def send(self, data, filename_virtual):
        self._dispatch(data, filename_virtual, time.time())

    def sync(self, target=None):
        if not self.pool_path:
            print("❌ Error: Define .pool() primero")
            return

        if target:
            self._sync_file(target)
        else:
            print(f"🔄 Sincronizando todo desde {self.pool_path}...")
            # Enviar todos los json del raíz
            for item in self.pool_path.glob("*.json"):
                if item.is_file():
                    self._sync_file(item.name)
            
            # (Opcional) Si quieres enviar recursivamente subcarpetas, necesitarías lógica extra aquí.
            # Por ahora solo envía el nivel raíz del pool.

    def _sync_file(self, filename):
        file_path = self.pool_path / filename
        if not file_path.exists():
            print(f"⚠️ Archivo no existe: {filename}")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            timestamp = file_path.stat().st_mtime
            
            print(f"📤 Enviando: {filename}")
            self._dispatch(content, filename, timestamp)
            
        except Exception as e:
            print(f"❌ Error leyendo {filename}: {e}")

    def _dispatch(self, payload, filename, timestamp):
        if self.sock:
            envelope = {
                "filename": filename,
                "payload": payload,
                "ts": timestamp,
                "node_id": self.node_id,        # ID único
                "hostname": self.node_name,     # Nombre PC (ej: "PC1")
                "pool_name": self.pool_folder_name # Nombre carpeta (ej: "json_source")
            }
            msg_bytes = json.dumps(envelope).encode('utf-8')
            self.sock.sendto(msg_bytes, ('255.255.255.255', self.port))

    def close(self):
        self.running = False
        if self.sock:
            self.sock.close()