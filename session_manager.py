import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from api_client import DKHPAPIClient

class SessionManager:
    """Quản lý authentication và sessions cho từng user"""
    
    def __init__(self, api_client: DKHPAPIClient):
        self.api_client = api_client
        self.sessions: Dict[int, Dict[str, Any]] = {}  # user_id -> session_data
        self.auto_register_credentials: Dict[int, Dict[str, str]] = {}  # user_id -> {username, password}
        self._cleanup_task = None
    
    def start_cleanup_task(self):
        """Khởi động task để dọn dẹp sessions hết h���n"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
    
    async def _cleanup_expired_sessions(self):
        """Dọn dẹp sessions hết h���n định kỳ"""
        while True:
            try:
                await asyncio.sleep(60)  # Check mỗi ph��t
                now = datetime.now()
                expired_users = []
                
                for user_id, session in self.sessions.items():
                    # Session hết hạn sau 5 phút không ho���t động
                    if now - session.get('last_activity', now) > timedelta(minutes=5):
                        # Nếu có môn chờ ��ăng ký tự động, giữ lại credentials
                        if session.get('auto_register_classes'):
                            if user_id not in self.auto_register_credentials:
                                self.auto_register_credentials[user_id] = {
                                    'username': session.get('username'),
                                    'password': session.get('password')
                                }
                        else:
                            expired_users.append(user_id)
                
                for user_id in expired_users:
                    del self.sessions[user_id]
                    
            except Exception as e:
                print(f"Error in cleanup task: {e}")
    
    async def login(self, user_id: int, username: str, password: str) -> Dict[str, Any]:
        """
        Đăng nhập và tạo session mới
        Returns: Login response data
        """
        # Gọi API đăng nhập
        auth_data = await self.api_client.authenticate(username, password)
        
        # Lưu session
        self.sessions[user_id] = {
            'user_id': user_id,
            'username': username,
            'password': password,
            'student_id': auth_data['Id'],
            'full_name': auth_data['FullName'].strip(),  # Loại bỏ dấu cách thừa
            'token': auth_data['Token'],
            'expire': datetime.fromisoformat(auth_data['Expire'].replace('+07:00', '')),
            'last_activity': datetime.now(),
            'study_programs': None,
            'selected_program': None,
            'registration_info': None,
            'auto_register_classes': []  # List of {curriculum_id, class_id, loai_hinh}
        }
        
        return auth_data
    
    def get_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """L���y session của user"""
        return self.sessions.get(user_id)
    
    def update_activity(self, user_id: int):
        """Cập nhật th���i gian ho���t đ���ng cuối"""
        if user_id in self.sessions:
            self.sessions[user_id]['last_activity'] = datetime.now()
    
    async def refresh_token_if_needed(self, user_id: int) -> bool:
        """
        Kiểm tra và refresh token nếu cần
        Returns: True nếu token còn hiệu lực hoặc refresh thành công
        """
        session = self.sessions.get(user_id)
        if not session:
            return False
        
        # Kiểm tra token có h���t hạn kh��ng (refresh trước 1 phút)
        if datetime.now() >= session['expire'] - timedelta(minutes=1):
            try:
                # Re-authenticate
                auth_data = await self.api_client.authenticate(
                    session['username'],
                    session['password']
                )
                
                # Cập nh���t token mới
                session['token'] = auth_data['Token']
                session['expire'] = datetime.fromisoformat(auth_data['Expire'].replace('+07:00', ''))
                
                return True
            except Exception as e:
                print(f"Failed to refresh token for user {user_id}: {e}")
                return False
        
        return True
    
    def get_token(self, user_id: int) -> Optional[str]:
        """Lấy token của user"""
        session = self.sessions.get(user_id)
        return session['token'] if session else None
    
    def set_study_programs(self, user_id: int, programs: list):
        """Lưu danh sách mã ngành"""
        if user_id in self.sessions:
            self.sessions[user_id]['study_programs'] = programs
    
    def set_selected_program(self, user_id: int, program_id: str):
        """Chọn mã ngành"""
        if user_id in self.sessions:
            self.sessions[user_id]['selected_program'] = program_id
    
    def get_selected_program(self, user_id: int) -> Optional[str]:
        """L���y mã ngành đã chọn"""
        session = self.sessions.get(user_id)
        return session['selected_program'] if session else None
    
    def set_registration_info(self, user_id: int, info: Dict[str, Any]):
        """Lưu thông tin đ��ng ký học phần"""
        if user_id in self.sessions:
            self.sessions[user_id]['registration_info'] = info
    
    def get_registration_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin ��ăng ký học ph���n"""
        session = self.sessions.get(user_id)
        return session['registration_info'] if session else None
    
    def add_auto_register_class(self, user_id: int, curriculum_id: str, class_id: str, loai_hinh: str):
        """Thêm lớp vào danh sách đăng ký tự động"""
        session = self.sessions.get(user_id)
        if session:
            auto_class = {
                'curriculum_id': curriculum_id,
                'class_id': class_id,
                'loai_hinh': loai_hinh
            }
            if auto_class not in session['auto_register_classes']:
                session['auto_register_classes'].append(auto_class)
                
                # Lưu credentials đ��� dùng sau khi session UI hết h���n
                self.auto_register_credentials[user_id] = {
                    'username': session['username'],
                    'password': session['password']
                }
    
    def remove_auto_register_class(self, user_id: int, curriculum_id: str, class_id: str):
        """X��a lớp khỏi danh sách đăng ký tự động"""
        session = self.sessions.get(user_id)
        if session:
            session['auto_register_classes'] = [
                c for c in session['auto_register_classes']
                if not (c['curriculum_id'] == curriculum_id and c['class_id'] == class_id)
            ]
            
            # N���u không còn l���p nào ch��� đăng ký, xóa credentials
            if not session['auto_register_classes'] and user_id in self.auto_register_credentials:
                del self.auto_register_credentials[user_id]
    
    def get_auto_register_classes(self, user_id: int) -> list:
        """Lấy danh sách l���p đ��ng ký tự động"""
        session = self.sessions.get(user_id)
        return session['auto_register_classes'] if session else []
    
    def has_auto_register_classes(self, user_id: int) -> bool:
        """Ki���m tra có l���p chờ đăng ký t��� động không"""
        session = self.sessions.get(user_id)
        return bool(session and session['auto_register_classes'])
    
    async def restore_session_from_credentials(self, user_id: int) -> bool:
        """Khôi phục session từ credentials đã lưu"""
        if user_id not in self.auto_register_credentials:
            return False
        
        creds = self.auto_register_credentials[user_id]
        try:
            await self.login(user_id, creds['username'], creds['password'])
            return True
        except:
            return False
    
    def logout(self, user_id: int):
        """Đăng xuất v�� xóa session"""
        if user_id in self.sessions:
            # Nếu không có l���p ch��� đăng ký, xóa credentials
            if not self.sessions[user_id].get('auto_register_classes'):
                if user_id in self.auto_register_credentials:
                    del self.auto_register_credentials[user_id]
            
            del self.sessions[user_id]
