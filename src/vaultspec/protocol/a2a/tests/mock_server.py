import http.server
import json


class MockHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/.well-known/agent-card.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"name": "mock-agent"}).encode())
        else:
            self.send_response(404)
            self.end_headers()


def run(port=0):
    server_address = ("127.0.0.1", port)
    httpd = http.server.HTTPServer(server_address, MockHandler)
    assigned_port = httpd.server_port

    # Print PORT=... for ServerProcessManager discovery
    print(f"PORT={assigned_port}", flush=True)

    httpd.serve_forever()


if __name__ == "__main__":
    run()
