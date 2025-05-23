# app.py - Web服务包装器
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import os
import sys
from typing import Optional, Dict, Any
from contextlib import AsyncExitStack
import uvicorn

# 导入您的现有模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from get_worker_client import MCPClient

app = FastAPI(title="Workday MCP Service", version="1.0.0")

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 MCP 客户端实例
mcp_client: Optional[MCPClient] = None

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化 MCP 客户端"""
    global mcp_client
    try:
        mcp_client = MCPClient()
        # 使用相对路径连接到 MCP 服务器
        server_script_path = os.path.join(os.path.dirname(__file__), "get_worker_server.py")
        await mcp_client.connect_to_server(server_script_path)
        print("MCP Client connected successfully")
    except Exception as e:
        print(f"Failed to initialize MCP client: {e}")
        raise e

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    global mcp_client
    if mcp_client:
        await mcp_client.cleanup()

@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "message": "Workday MCP Service is running",
        "status": "healthy",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """详细健康检查"""
    global mcp_client
    return {
        "status": "healthy" if mcp_client else "unhealthy",
        "mcp_client_connected": mcp_client is not None,
        "service": "Workday MCP Service"
    }

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """处理查询请求"""
    global mcp_client
    
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")
    
    try:
        response = await mcp_client.process_query(request.query)
        return QueryResponse(success=True, response=response)
    except Exception as e:
        return QueryResponse(success=False, error=str(e))

@app.get("/capabilities")
async def get_capabilities():
    """获取 MCP 服务器能力"""
    global mcp_client
    
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")
    
    try:
        if hasattr(mcp_client, 'session') and mcp_client.session:
            response = await mcp_client.session.list_tools()
            tools = [{"name": tool.name, "description": tool.description} for tool in response.tools]
            return {"tools": tools}
        else:
            return {"error": "Session not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 用于本地测试的示例查询端点
@app.get("/test")
async def test_query():
    """测试查询端点"""
    test_query = "请帮我搜索所有员工信息"
    try:
        response = await process_query(QueryRequest(query=test_query))
        return response
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))  # IBM Cloud 通常使用 PORT 环境变量
    uvicorn.run(app, host="0.0.0.0", port=port)