import http.server
import socketserver
import sqlite3
import json
import urllib.parse
import os

PORT = 8000
DB_FILE = "D2019.01.06_S01372_I0521_D.pdb"

class PDBRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        if path == '/api/embryos':
            self.handle_embryos()
        elif path == '/api/timeline':
            self.handle_timeline(query)
        elif path == '/image':
            self.handle_image(query)
        elif path == '/api/annotations/global':
            self.handle_get_global_annotations()
        elif path == '/api/annotations/notes':
            self.handle_get_notes(query)
        else:
            super().do_GET()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON data")
            return

        if path == '/api/annotations/arrested':
            self.handle_post_arrested(data)
        elif path == '/api/annotations/grades':
            self.handle_post_grades(data)
        elif path == '/api/annotations/notes':
            self.handle_post_notes(data)
        else:
            self.send_error(404, "Endpoint not found")

    def init_annotations_db(self):
        conn = sqlite3.connect('annotations.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS embryo_data (
                embryo_id TEXT PRIMARY KEY,
                arrested INTEGER DEFAULT 0,
                grades TEXT,
                notes TEXT
            )
        ''')
        conn.commit()
        return conn

    def handle_get_global_annotations(self):
        try:
            conn = sqlite3.connect('annotations.db')
            c = conn.cursor()
            c.execute("SELECT embryo_id, arrested, grades FROM embryo_data")
            rows = c.fetchall()
            conn.close()

            arrested = {}
            grades = {}
            for row in rows:
                embryo_id, is_arrested, grades_json = row
                arrested[embryo_id] = bool(is_arrested)
                if grades_json:
                    try:
                        grades[embryo_id] = json.loads(grades_json)
                    except json.JSONDecodeError:
                        pass

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'arrested': arrested, 'grades': grades}).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def handle_get_notes(self, query):
        embryo_id = query.get('id', [None])[0]
        if not embryo_id:
            self.send_error(400, "Missing id parameter")
            return
            
        try:
            conn = sqlite3.connect('annotations.db')
            c = conn.cursor()
            c.execute("SELECT notes FROM embryo_data WHERE embryo_id = ?", (embryo_id,))
            row = c.fetchone()
            conn.close()

            notes = {}
            if row and row[0]:
                try:
                    notes = json.loads(row[0])
                except json.JSONDecodeError:
                    pass

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(notes).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def handle_post_arrested(self, data):
        embryo_id = data.get('id')
        arrested = data.get('arrested', False)
        
        if not embryo_id:
            self.send_error(400, "Missing id parameter")
            return

        try:
            conn = self.init_annotations_db()
            c = conn.cursor()
            c.execute('''
                INSERT INTO embryo_data (embryo_id, arrested) 
                VALUES (?, ?)
                ON CONFLICT(embryo_id) DO UPDATE SET arrested=excluded.arrested
            ''', (embryo_id, int(arrested)))
            conn.commit()
            conn.close()
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
        except Exception as e:
            self.send_error(500, str(e))

    def handle_post_grades(self, data):
        embryo_id = data.get('id')
        grades = data.get('grades')
        
        if not embryo_id or grades is None:
            self.send_error(400, "Missing parameters")
            return

        try:
            conn = self.init_annotations_db()
            c = conn.cursor()
            c.execute('''
                INSERT INTO embryo_data (embryo_id, grades) 
                VALUES (?, ?)
                ON CONFLICT(embryo_id) DO UPDATE SET grades=excluded.grades
            ''', (embryo_id, json.dumps(grades)))
            conn.commit()
            conn.close()
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
        except Exception as e:
            self.send_error(500, str(e))

    def handle_post_notes(self, data):
        embryo_id = data.get('id')
        notes = data.get('notes')
        
        if not embryo_id or notes is None:
            self.send_error(400, "Missing parameters")
            return

        try:
            conn = self.init_annotations_db()
            c = conn.cursor()
            c.execute('''
                INSERT INTO embryo_data (embryo_id, notes) 
                VALUES (?, ?)
                ON CONFLICT(embryo_id) DO UPDATE SET notes=excluded.notes
            ''', (embryo_id, json.dumps(notes)))
            conn.commit()
            conn.close()
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
        except Exception as e:
            self.send_error(500, str(e))

    def handle_embryos(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT DISTINCT Well FROM IMAGES ORDER BY Well")
            embryos = [row[0] for row in c.fetchall()]
            conn.close()

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(embryos).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def handle_timeline(self, query):
        embryo_id = query.get('id', [None])[0]
        if not embryo_id:
            self.send_error(400, "Missing id parameter")
            return

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            # Get all Time and Focal combinations for this embryo, filtering out artifacts
            c.execute("SELECT Time, Focal FROM IMAGES WHERE Well = ? AND Time >= 0 AND Focal BETWEEN -100 AND 100 ORDER BY Time, Focal", (embryo_id,))
            rows = c.fetchall()
            conn.close()

            # Group by Time
            timeline = {}
            for time, focal in rows:
                if time not in timeline:
                    timeline[time] = []
                timeline[time].append(focal)

            # Convert to list for easier frontend consumption
            # [{time: t, focals: [z1, z2...]}, ...]
            result = []
            for time in sorted(timeline.keys()):
                result.append({
                    'time': time,
                    'focals': sorted(timeline[time])
                })

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:
            self.send_error(500, str(e))

    def handle_image(self, query):
        embryo_id = query.get('id', [None])[0]
        time = query.get('time', [None])[0]
        z = query.get('z', [None])[0]

        if not (embryo_id and time and z):
            self.send_error(400, "Missing parameters")
            return

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT Image FROM IMAGES WHERE Well = ? AND Time = ? AND Focal = ?", (embryo_id, time, z))
            row = c.fetchone()
            conn.close()

            if row:
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(row[0])
            else:
                self.send_error(404, "Image not found")
        except Exception as e:
            self.send_error(500, str(e))

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

import socket

if __name__ == "__main__":
    # Use PORT from environment variable if available.
    # If not set, use 0 to let the OS pick a free port.
    env_port = os.environ.get('PORT')
    if env_port:
        PORT = int(env_port)
    else:
        PORT = 0
    
    # Allow address reuse to avoid "Address already in use" errors on restart
    ThreadingHTTPServer.allow_reuse_address = True
    
    with ThreadingHTTPServer(("", PORT), PDBRequestHandler) as httpd:
        # Get the actual port we are listening on (useful if PORT was 0)
        actual_port = httpd.server_address[1]
        
        # Find the LAN IP address
        try:
            # Connect to a public DNS server to determine the best local IP
            # This doesn't actually send data, just checks routing
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            lan_ip = "127.0.0.1"

        print(f"\n--- Embryo Viewer Started ---")
        print(f"Local access:   http://localhost:{actual_port}/pdb_viewer.html")
        print(f"Network access: http://{lan_ip}:{actual_port}/pdb_viewer.html")
        print(f"-----------------------------\n")
        
        httpd.serve_forever()
