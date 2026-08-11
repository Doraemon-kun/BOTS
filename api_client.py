import aiohttp
import json
from typing import Dict, Any, Optional, List

class DKHPAPIClient:
    """Client để giao tiếp v���i hệ thống đăng ký học phần HCMUE"""
    
    BASE_URL = "https://dkhpapi.hcmue.edu.vn/api"
    
    def __init__(self, api_key: str, client_id: str):
        self.api_key = api_key
        self.client_id = client_id
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        """Đ���m bảo session đư���c tạo"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Đóng session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _get_headers(self, token: Optional[str] = None, include_content_type: bool = False) -> Dict[str, str]:
        """Tạo headers cho request"""
        headers = {
            'Origin': 'https://dkhp.hcmue.edu.vn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
            'apiKey': self.api_key,
            'clientId': self.client_id
        }
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        if include_content_type:
            headers['Content-Type'] = 'application/json'
        
        return headers
    
    async def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Bước 1: Đăng nhập
        Returns: {"Id", "FullName", "Token", "Expire", ...}
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Authen/Authenticate"
        headers = self._get_headers(include_content_type=True)
        data = {
            "username": username,
            "password": password
        }
        
        async with self.session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"Đăng nh���p th���t bại: {text}")
    
    async def get_study_programs(self, token: str) -> List[Dict[str, Any]]:
        """
        Bước 2: Xem mã ngành
        Returns: [{"StudyProgramID", "StudyProgramName"}]
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Authen/GetAllStudyProgramRegist"
        headers = self._get_headers(token)
        
        async with self.session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"L���y mã ngành thất b���i: {text}")
    
    async def get_registration_info(self, token: str, study_program_id: str) -> Dict[str, Any]:
        """
        Bước 3: Tra cứu thông tin ngành của sinh viên
        Returns: {"IdDot", "YearStudy", "TermID", "BeginDate", "EndDate", "RandID", ...}
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Regist/GetRegistSemesterCreditQuota"
        headers = self._get_headers(token)
        params = {"StudyProgramID": study_program_id}
        
        async with self.session.get(url, headers=headers, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"Lấy thông tin đăng ký thất bại: {text}")
    
    async def get_registered_classes(self, token: str, rand_id: str, turn_id: str) -> Dict[str, Any]:
        """
        Bước 4: Tra cứu thông tin lớp học phần đ�� đăng ký
        Returns: {"Rows": [...], "Reval": ""}
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Regist/GetAllClassRegisted"
        headers = self._get_headers(token, include_content_type=True)
        data = {
            "ReqParam1": rand_id,
            "ReqParam2": turn_id
        }
        
        async with self.session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"Lấy danh sách lớp đã đăng ký thất bại: {text}")
    
    async def get_study_types(self, token: str) -> List[Dict[str, Any]]:
        """
        Bước 5: Tra th��ng tin đăng ký của đ���t này
        Returns: [{"ChucNangID", "TenChucNang", "LoaiHinh", "MapID", "HienThi"}]
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Authen/GetAllStudyType"
        headers = self._get_headers(token)
        
        async with self.session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"Lấy danh sách chức n��ng th���t bại: {text}")
    
    async def get_available_courses(self, token: str, study_program_id: str, loai_hinh: str, 
                                   year_study: str, term_id: str) -> List[Dict[str, Any]]:
        """
        Bư���c 6: Tra cứu thông tin học phần đư���c đăng k�� theo từng ChucNangID
        Returns: [{"CurriculumTypeGroupName", "classStudyUnits": [...]}]
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Regist/GetAllClassAllowRegist"
        headers = self._get_headers(token, include_content_type=True)
        data = {
            "ReqParam1": study_program_id,
            "ReqParam2": loai_hinh,
            "ReqParam3": year_study,
            "ReqParam4": term_id,
            "ReqParam5": ""
        }
        
        async with self.session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"Lấy danh sách môn học thất b���i: {text}")
    
    async def get_available_schedule_units(self, token: str, study_program_id: str, 
                                          loai_hinh: str, study_unit_id: str) -> List[Dict[str, Any]]:
        """
        Bước 7: Tra cứu l���p học phần c��� thể cho một học phần
        Returns: [{"ScheduleStudyUnitID", "CurriculumName", "NumberOfStudents", ...}]
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Regist/GetAllScheduleUnitAllowRegist"
        headers = self._get_headers(token, include_content_type=True)
        data = {
            "ReqParam1": study_program_id,
            "ReqParam2": loai_hinh,
            "ReqParam3": study_unit_id
        }
        
        async with self.session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                raise Exception(f"Lấy danh sách l���p học ph���n th���t bại: {text}")
    
    async def register_class(self, token: str, turn_id: str, study_program_id: str, 
                            regist_type: str, class_data: Dict[str, Any]) -> str:
        """
        Bước 9: Đăng ký học phần
        Returns: Success message or error
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Regist/RegistScheduleStudyUnit"
        headers = self._get_headers(token, include_content_type=True)
        params = {
            "TurnID": turn_id,
            "Action": "REGIST",
            "StudyProgramID": study_program_id,
            "RegistType": regist_type
        }
        
        # ��ảm bảo class_data là list
        data = [class_data] if isinstance(class_data, dict) else class_data
        
        async with self.session.post(url, headers=headers, params=params, json=data) as response:
            text = await response.text()
            if response.status == 200:
                return text
            else:
                raise Exception(f"Đăng ký thất bại: {text}")
    
    async def remove_class(self, token: str, turn_id: str, study_program_id: str, 
                          class_data: Dict[str, Any]) -> str:
        """
        Bước 8: Hủy lớp học phần đã đăng ký
        Returns: Success message or error
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/Regist/RemoveScheduleStudyUnit"
        headers = self._get_headers(token, include_content_type=True)
        params = {
            "TurnID": turn_id,
            "StudyProgramID": study_program_id
        }
        
        async with self.session.post(url, headers=headers, params=params, json=class_data) as response:
            text = await response.text()
            if response.status == 200:
                return text
            else:
                raise Exception(f"Hủy lớp thất bại: {text}")
