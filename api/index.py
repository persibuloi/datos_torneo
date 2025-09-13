from http.server import BaseHTTPRequestHandler
import subprocess
import sys
import os

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Cambiar al directorio del proyecto
        os.chdir('/var/task')
        
        # Ejecutar Streamlit
        try:
            result = subprocess.run([
                sys.executable, '-m', 'streamlit', 'run', 'streamlit_app.py',
                '--server.headless', 'true',
                '--server.port', '8501',
                '--server.address', '0.0.0.0'
            ], capture_output=True, text=True, timeout=30)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Streamlit app is starting...')
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'Error: {str(e)}'.encode())
