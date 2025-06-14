import socket
import asyncio
import ssl
import os
from dotenv import load_dotenv
from datetime import datetime


# 載入環境變數
load_dotenv()

class ChatClient:
    def __init__(self):
        self.reader = None
        self.writer = None
        self.nickname = None
        self.use_ssl = os.getenv('USE_SSL', 'false').lower() == 'true'
        self.ssl_context = None
        
        if self.use_ssl:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            # 如果是自簽名證書，需要禁用證書驗證
            if os.getenv('SSL_VERIFY', 'false').lower() == 'false':
                self.ssl_context.check_hostname = False
                self.ssl_context.verify_mode = ssl.CERT_NONE
            else:
                # 載入自定義 CA 證書
                ca_cert = os.getenv('SSL_CA_CERT')
                if ca_cert and os.path.exists(ca_cert):
                    self.ssl_context.load_verify_locations(ca_cert)

    def parse_host(self, host: str) -> tuple[str, int]:
        """解析主機地址，支援多種格式"""
        # 移除可能的協議前綴
        host = host.replace('tcp://', '').replace('https://', '').replace('http://', '')
        # 移除可能的尾部斜線
        host = host.rstrip('/')
        
        # 使用 rsplit 來處理可能包含多個冒號的地址
        try:
            hostname, port_str = host.rsplit(':', 1)
            port = int(port_str)
            if not (0 < port < 65536):
                raise ValueError("Port number must be between 1 and 65535")
            return hostname, port
        except ValueError as e:
            if "Port number" in str(e):
                raise ValueError(f"無效的端口號: {port_str}")
            raise ValueError("地址格式無效，請使用 'hostname:port' 格式")

    async def connect(self, host: str):
        """連接到伺服器"""
        try:
            hostname, port = self.parse_host(host)
            print(f"正在連接到 {hostname}:{port}...")
            
            if self.use_ssl:
                print("使用 SSL/TLS 加密連接")
                self.reader, self.writer = await asyncio.open_connection(
                    hostname, 
                    port,
                    ssl=self.ssl_context
                )
            else:
                print("警告：未使用加密連接，通信可能不安全")
                self.reader, self.writer = await asyncio.open_connection(
                    hostname, 
                    port
                )
            
            print("已成功連接到伺服器！")
            return True
        except ValueError as e:
            print(f"錯誤：{e}")
            return False
        except ConnectionRefusedError:
            print("錯誤：無法連接到伺服器，請確認伺服器是否正在運行")
            return False
        except ssl.SSLError as e:
            print(f"SSL 錯誤：{e}")
            print("請確認 SSL 證書配置是否正確")
            return False
        except Exception as e:
            print(f"連接時發生錯誤：{e}")
            return False

    async def send_message(self, message: str):
        """發送訊息到伺服器"""
        if not self.writer:
            print("錯誤：未連接到伺服器")
            return False
        try:
            self.writer.write(message.encode())
            await self.writer.drain()
            return True
        except Exception as e:
            print(f"發送訊息時發生錯誤：{e}")
            return False

    async def receive_messages(self):
        """接收伺服器訊息"""
        if not self.reader:
            print("錯誤：未連接到伺服器")
            return
        try:
            while True:
                data = await self.reader.readline()
                if not data:
                    break
                message = data.decode().strip()
                # 跳過 '請輸入您的暱稱'，不顯示
                if message.startswith("請輸入您的暱稱"):
                    continue
                # 系統訊息不加時間戳
                if message.startswith("[系統]") or message.startswith("暱稱無效"):
                    print(message)
                    continue
                # 取得當前時間
                current_time = datetime.now().strftime("%H:%M:%S")
                # 嘗試解析暱稱和內容
                if message.startswith("[") and "]：" in message:
                    try:
                        nickname = message.split("]：", 1)[0][1:]
                        content = message.split("]：", 1)[1]
                        # 跳過自己送出的訊息
                        if nickname == self.nickname:
                            continue
                        print(f"[{current_time}] <{nickname}> {content}")
                    except Exception:
                        print(f"[{current_time}] {message}")
                else:
                    print(f"[{current_time}] {message}")
        except Exception as e:
            print(f"接收訊息時發生錯誤：{e}")
        finally:
            await self.close()

    async def close(self):
        """關閉連接"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                print(f"關閉連接時發生錯誤：{e}")

    async def send_messages(self):
        """非同步發送訊息到伺服器"""
        try:
            while True:
                message = await asyncio.get_event_loop().run_in_executor(None, input, ">> ")
                if message.lower() == 'quit':
                    await self.close()
                    break
                if not await self.send_message(message + '\n'):
                    break
        except Exception as e:
            print(f"發送訊息時發生錯誤：{e}")

async def main():
    print("="*50)
    print("聊天室客戶端")
    print("="*50)
    print("\n連線方式選擇：")
    print("  1. 本機（localhost:8888）")
    print("  2. ngrok TCP（如 0.tcp.jp.ngrok.io:19110 或 tcp://0.tcp.jp.ngrok.io:19110）")
    print("  3. 其他（請輸入 IP:PORT 或 域名:PORT）")
    print("\n請直接輸入完整伺服器位址，或直接按 Enter 使用預設 localhost:8888")
    print("="*50 + "\n")
    
    address = input("請輸入完整伺服器位址: ").strip() or "localhost:8888"

    client = ChatClient()

    # 先連線
    if not await client.connect(address):
        print("無法連接到伺服器，請檢查地址和伺服器狀態。")
        return

    # 獲取暱稱
    while True:
        client.nickname = input("請輸入您的暱稱: ").strip()
        if client.nickname:
            break
        print("暱稱不能為空")

    # 發送暱稱
    await client.send_message(client.nickname + '\n')

    # 同時啟動收發訊息協程，任一結束就全部結束
    send_task = asyncio.create_task(client.send_messages())
    recv_task = asyncio.create_task(client.receive_messages())
    done, pending = await asyncio.wait(
        [send_task, recv_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    await client.close()
    print("客戶端已關閉")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n客戶端已關閉") 