Run server: .venv_server\Scripts\activate; python get_worker_server.py
Run client: .venv_client\Scripts\activate; python get_worker_client.py ../mcp-workday/get_worker_server.py
Stop program: Stop-Process -Name "python" -Force

MCP server debug: mcp dev workday_mcp_server.py