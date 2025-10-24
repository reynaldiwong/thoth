

import json
import subprocess
import select
import os
import time
import requests
from typing import Dict, Any, List, Optional, Literal
from threading import Thread, Lock
from .display import console


class MCPConnection:
    
    
    def __init__(
        self, 
        name: str, 
        transport: Literal["stdio", "http"] = "stdio",
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.transport = transport
        self.command = command
        self.args = args or []
        self.url = url
        self.env = env or {}
        self.process = None
        self.session = None  
        self.initialized = False
        self.capabilities = {}
        self.request_id = 0
        self.lock = Lock()
    
    def start(self) -> bool:
        
        if self.transport == "stdio":
            return self._start_stdio()
        elif self.transport == "http":
            return self._start_http()
        return False
    
    def _start_stdio(self) -> bool:
        
        try:
            if not self.command:
                return False
            
            full_command = [self.command] + self.args
            process_env = os.environ.copy()
            process_env.update(self.env)
            
            self.process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=process_env,
                text=True,
                bufsize=1
            )
            
            
            time.sleep(2)
            
            
            if self.process.poll() is not None:
                return False
            
            
            return self._initialize()
        except Exception:
            return False
    
    def _start_http(self) -> bool:
        
        try:
            if not self.url:
                return False
            
            self.session = requests.Session()
            
            
            try:
                
                response = self.session.get(f"{self.url}/health", timeout=5)
                if response.status_code != 200:
                    
                    pass
            except requests.exceptions.RequestException:
                
                pass
            
            
            return self._initialize()
        except requests.exceptions.ConnectionError:
            console.print(f"[yellow]Connection refused: {self.url}[/yellow]")
            return False
        except requests.exceptions.Timeout:
            console.print(f"[yellow]Connection timeout: {self.url}[/yellow]")
            return False
        except Exception as e:
            console.print(f"[yellow]HTTP connection error: {e}[/yellow]")
            return False
    
    def _initialize(self) -> bool:
        
        init_request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "thoth",
                    "version": "0.1.0"
                }
            }
        }
        
        response = self._send_request(init_request, timeout=15)
        
        if response and "result" in response:
            self.capabilities = response["result"].get("capabilities", {})
            self.initialized = True
            
            
            self._send_notification({
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            })
            
            return True
        
        return False
    
    def _next_id(self) -> int:
        
        with self.lock:
            self.request_id += 1
            return self.request_id
    
    def _send_request(self, request: Dict[str, Any], timeout: int = 10) -> Optional[Dict[str, Any]]:
        
        if self.transport == "stdio":
            return self._send_request_stdio(request, timeout)
        elif self.transport == "http":
            return self._send_request_http(request, timeout)
        return None
    
    def _send_request_stdio(self, request: Dict[str, Any], timeout: int = 10) -> Optional[Dict[str, Any]]:
        
        if not self.process or self.process.poll() is not None:
            return None
        
        try:
            
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str)
            self.process.stdin.flush()
            
            
            ready, _, _ = select.select([self.process.stdout], [], [], timeout)
            if ready:
                response_line = self.process.stdout.readline()
                if response_line:
                    try:
                        return json.loads(response_line)
                    except json.JSONDecodeError:
                        return None
        except Exception:
            pass
        
        return None
    
    def _send_request_http(self, request: Dict[str, Any], timeout: int = 10) -> Optional[Dict[str, Any]]:
        
        if not self.session or not self.url:
            return None
        
        try:
            response = self.session.post(
                f"{self.url}/message",
                json=request,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        
        return None
    
    def _send_notification(self, notification: Dict[str, Any]) -> None:
        
        if self.transport == "stdio":
            self._send_notification_stdio(notification)
        elif self.transport == "http":
            self._send_notification_http(notification)
    
    def _send_notification_stdio(self, notification: Dict[str, Any]) -> None:
        
        if not self.process or self.process.poll() is not None:
            return
        
        try:
            notification_str = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_str)
            self.process.stdin.flush()
        except Exception:
            pass
    
    def _send_notification_http(self, notification: Dict[str, Any]) -> None:
        
        if not self.session or not self.url:
            return
        
        try:
            self.session.post(
                f"{self.url}/message",
                json=notification,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
        except Exception:
            pass
    
    def list_resources(self) -> Optional[List[Dict[str, Any]]]:
        
        if not self.initialized:
            return None
        
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "resources/list"
        }
        
        response = self._send_request(request, timeout=15)
        
        if response and "result" in response:
            return response["result"].get("resources", [])
        
        return None
    
    def read_resource(self, uri: str) -> Optional[Dict[str, Any]]:
        
        if not self.initialized:
            return None
        
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "resources/read",
            "params": {
                "uri": uri
            }
        }
        
        response = self._send_request(request, timeout=15)
        if response and "result" in response:
            return response["result"]
        return None
    
    def list_tools(self) -> Optional[List[Dict[str, Any]]]:
        
        if not self.initialized:
            return None
        
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list"
        }
        
        response = self._send_request(request, timeout=15)
        
        if response and "result" in response:
            return response["result"].get("tools", [])
        
        return None
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        
        if not self.initialized:
            return None
        
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response = self._send_request(request, timeout=30)
        
        if response and "result" in response:
            return response["result"]
        
        return None
    
    def stop(self) -> None:
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            finally:
                self.process = None
        
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            finally:
                self.session = None
        
        self.initialized = False


class MCPManager:
    
    
    def __init__(self):
        self.connections: Dict[str, MCPConnection] = {}
        self.lock = Lock()
    
    def start_server(
        self, 
        name: str, 
        transport: Literal["stdio", "http"] = "stdio",
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> bool:
        
        with self.lock:
            if name in self.connections:
                return True  
            
            connection = MCPConnection(
                name=name,
                transport=transport,
                command=command,
                args=args,
                url=url,
                env=env
            )
            
            if connection.start():
                self.connections[name] = connection
                return True
            return False
    
    def stop_server(self, name: str) -> None:
        
        with self.lock:
            if name in self.connections:
                self.connections[name].stop()
                del self.connections[name]
    
    def stop_all(self) -> None:
        
        with self.lock:
            for connection in self.connections.values():
                connection.stop()
            self.connections.clear()
    
    def get_connection(self, name: str) -> Optional[MCPConnection]:
        
        return self.connections.get(name)
    
    def is_connected(self, name: str) -> bool:
        
        conn = self.connections.get(name)
        return conn is not None and conn.initialized
    
    def get_all_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        
        all_resources = {}
        for name, connection in self.connections.items():
            try:
                resources = connection.list_resources()
                if resources:
                    all_resources[name] = resources
            except Exception:
                pass
        return all_resources
    
    def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        
        all_tools = {}
        for name, connection in self.connections.items():
            try:
                tools = connection.list_tools()
                if tools:
                    all_tools[name] = tools
            except Exception:
                pass
        return all_tools