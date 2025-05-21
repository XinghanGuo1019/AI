Run server: .\.venv\Scripts\activate; cd mcp-workday; python get_worker_server.py
Run client: .\.venv\Scripts\activate; cd mcp-client-workday; python get_worker_client.py ../mcp-workday/get_worker_server.py
Stop program: Stop-Process -Name "python" -Force