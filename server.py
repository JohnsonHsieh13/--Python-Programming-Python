import socket          # 用於網路通訊和獲取本機IP地址
import asyncio         # 用於實現非同步IO操作,是聊天伺服器的核心功能
import re             # 用於正則表達式,驗證暱稱格式
from pyngrok import ngrok, conf  # 用於建立ngrok隧道,實現外網訪問
import os             # 用於操作系統環境變數
from dotenv import load_dotenv   # 用於從.env檔案載入環境變數
import ssl            # 用於SSL/TLS加密連接

# 載入環境變數
load_dotenv()         # 從.env檔案載入環境變數到程式中使用
def setup_ngrok():
    try:
        # 設置 ngrok 配置
        config = conf.get_default()
        
        # 從環境變數讀取 authtoken
        auth_token = os.getenv('NGROK_AUTH_TOKEN')
        if auth_token:
            config.auth_token = auth_token
            print("已載入 ngrok authtoken")
        
        # 設置區域（可選）
        config.region = "jp"  # 可選值: "us", "eu", "ap", "au", "sa", "jp", "in"
        
        # 設置其他選項
        config.monitor_thread = False  # 關閉監控線程以減少資源使用
        
        # 啟動 TCP 隧道
        public_url = ngrok.connect(
            addr=8888,
            proto="tcp",
            name="chat_server"  # 給隧道一個名稱
        )
        
        print(f"\nngrok 隧道已啟動：")
        print(f"TCP 地址：{public_url}")
        print("你可以在 ngrok 官方後台查看所有隧道：")
        print("https://dashboard.ngrok.com/endpoints")
        print("（TCP 隧道不支援即時流量監控，只能看到隧道資訊）")
        # 顯示目前所有 ngrok 隧道狀態
        print("\n[ngrok 隧道狀態]")
        tunnels = ngrok.get_tunnels()
        if tunnels:
            for t in tunnels:
                print(f"- name: {t.name}, proto: {t.proto}, public_url: {t.public_url}, addr: {t.config.get('addr')}")
        else:
            print("目前沒有啟動中的 ngrok 隧道")
        return public_url
    except Exception as e:
        print(f"啟動 ngrok 隧道時發生錯誤: {e}")
        return None

def get_all_local_ips():
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except Exception:
        pass
    ips.add("127.0.0.1")
    return ips

class ChatServer:
    def __init__(self,host:str='0.0.0.0',port:int=8888,use_ssl:bool=False):
        self.host=host
        self.port=port
        self.clients:set[asyncio.StreamWriter]=set()
        self.nicknames:dict[asyncio.StreamWriter,str]={}
        self.server=None
        self.max_message_length = 1000
        self.max_nickname_length = 20
        self.ngrok_tunnel = None
        self.ngrok_url = None
        self.use_ssl = use_ssl
        self.ssl_context = None
        
        if self.use_ssl:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            # 載入 SSL 證書和私鑰
            cert_path = os.getenv('SSL_CERT_PATH', 'cert.pem')
            key_path = os.getenv('SSL_KEY_PATH', 'key.pem')
            try:
                self.ssl_context.load_cert_chain(cert_path, key_path)
                print("已載入 SSL 證書")
            except Exception as e:
                print(f"載入 SSL 證書時發生錯誤: {e}")
                print("將使用自簽名證書...")
                self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                self.ssl_context.check_hostname = False
                self.ssl_context.verify_mode = ssl.CERT_NONE

    def validate_nickname(self, nickname: str) -> bool:
        # 檢查暱稱長度
        if not nickname or len(nickname) > self.max_nickname_length:
            return False
        # 檢查暱稱是否只包含合法字符
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', nickname):
            return False
        # 檢查暱稱是否已被使用
        if nickname in self.nicknames.values():
            return False
        return True

    async def start(self):
        # 啟動 ngrok 隧道
        self.ngrok_url = setup_ngrok()
        if self.ngrok_url:
            self.ngrok_tunnel = ngrok.get_tunnels()[0]
        
        # 創建伺服器
        if self.use_ssl and self.ssl_context:
            self.server = await asyncio.start_server(
                self.handle_client, 
                self.host, 
                self.port,
                ssl=self.ssl_context
            )
            print("伺服器已啟用 SSL/TLS 加密")
        else:
            self.server = await asyncio.start_server(
                self.handle_client, 
                self.host, 
                self.port
            )
            print("警告：伺服器未啟用加密，通信可能不安全")
        
        print(f"\n伺服器已啟動於 {self.host}:{self.port}")
        print(f"本機所有可用IP：")
        for ip in get_all_local_ips():
            print(f"- {ip}:{self.port}")
        print(f"\n請根據客戶端所在網路選擇正確的IP連線")
        if self.ngrok_url:
            print(f"\nngrok TCP 地址：{self.ngrok_url}")
            print("其他用戶可以使用此地址連接到聊天室")
            if not self.use_ssl:
                print("警告：ngrok TCP 隧道未加密，建議啟用 SSL/TLS")
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.clients.add(writer)
        client_addr = writer.get_extra_info('peername')
        try:
            # 處理暱稱輸入
            while True:
                writer.write("請輸入您的暱稱: ".encode())
                await writer.drain()
                nickname_data = await reader.readline()
                nickname = nickname_data.decode().strip()
                
                if self.validate_nickname(nickname):
                    break
                writer.write("暱稱無效或已被使用，請重新輸入: ".encode())
                await writer.drain()

            self.nicknames[writer] = nickname
            print(f"新用戶已連接: {client_addr}，暱稱：{nickname}")
            print(f"目前在線人數：{len(self.clients)}")
            print("在線用戶：" + ", ".join(self.nicknames.values()))
            await self.broadcast(f"[系統] {nickname} 加入了聊天室！", exclude=writer)

            while True:
                data = await reader.read(1024)
                if not data:
                    break
                message = data.decode().strip()
                
                # 檢查訊息長度
                if len(message) > self.max_message_length:
                    writer.write(f"訊息太長，請限制在 {self.max_message_length} 字元以內\n".encode())
                    await writer.drain()
                    continue

                print(f"[{nickname}]：{message}")
                print(f"目前在線人數：{len(self.clients)}")
                print("在線用戶：" + ", ".join(self.nicknames.values()))
                await self.broadcast(f"[{nickname}]：{message}", exclude=None)

        except asyncio.CancelledError:
            print(f"客戶端 {client_addr} 連接被取消")
        except Exception as e:
            print(f"處理客戶端 {client_addr} 時發生錯誤: {e}")
        finally:
            await self.remove_client(writer, client_addr)

    async def remove_client(self, writer: asyncio.StreamWriter, client_addr):
        if writer in self.clients:
            self.clients.remove(writer)
            left_nickname = self.nicknames.pop(writer, str(client_addr))
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                print(f"關閉客戶端連接時發生錯誤: {e}")
            print(f"用戶已斷開連接: {client_addr}，暱稱：{left_nickname}")
            print(f"目前在線人數：{len(self.clients)}")
            if self.nicknames:
                print("在線用戶：" + ", ".join(self.nicknames.values()))
            else:
                print("目前無人在線")
            await self.broadcast(f"[系統] {left_nickname} 離開了聊天室。", exclude=None)

    async def broadcast(self, message: str, exclude=None):
        if not self.clients:
            return
        disconnected_clients = set()
        for client in self.clients:
            if client == exclude:
                continue
            try:
                client.write((message + '\n').encode())
                await client.drain()
            except Exception as e:
                print(f"廣播訊息時發生錯誤: {e}")
                disconnected_clients.add(client)
        
        # 清理斷開的客戶端
        for client in disconnected_clients:
            await self.remove_client(client, client.get_extra_info('peername'))

    async def cleanup(self):
        # 關閉 ngrok 隧道
        if self.ngrok_tunnel:
            try:
                print("\n正在關閉 ngrok 隧道...")
                ngrok.disconnect(self.ngrok_tunnel.public_url)
                ngrok.kill()
                print("ngrok 隧道已關閉")
            except Exception as e:
                print(f"關閉 ngrok 隧道時發生錯誤: {e}")

async def main():
    # 檢查是否啟用 SSL
    use_ssl = os.getenv('USE_SSL', 'false').lower() == 'true'
    server = ChatServer(use_ssl=use_ssl)
    try:
        await server.start()
    except asyncio.CancelledError:
        print("\n正在關閉伺服器...")
        await server.cleanup()
        if server.server:
            server.server.close()
            await server.server.wait_closed()
        print("伺服器已關閉")
    except KeyboardInterrupt:
        print("\n正在關閉伺服器...")
        await server.cleanup()
        if server.server:
            server.server.close()
            await server.server.wait_closed()
        print("伺服器已關閉")
    except Exception as e:
        print(f"發生錯誤: {e}")
        await server.cleanup()
        if server.server:
            server.server.close()
            await server.server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n伺服器已關閉") 