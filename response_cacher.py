import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

class ResponseCacher:
    """Qu���n lý cache các response từ API với th���i gian hết hạn"""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._refresh_tasks: Dict[str, asyncio.Task] = {}
    
    def _get_key(self, user_id: int, cache_type: str, *args) -> str:
        """T���o cache key"""
        return f"{user_id}:{cache_type}:{':'.join(str(a) for a in args)}"
    
    def set(self, user_id: int, cache_type: str, data: Any, expiry_seconds: int, *args):
        """
        L��u data vào cache với thời gian hết hạn
        
        cache_type có th��� là:
        - 'study_programs': Danh sách mã ngành (kh��ng hết h���n)
        - 'registration_info': Thông tin đợt đăng ký (không hết hạn)
        - 'registered_classes': Lớp đã đ��ng ký (hết hạn khi đăng ký/h���y)
        - 'study_types': Các chức năng đăng ký (không hết hạn)
        - 'available_courses': Các môn mở đăng ký (hết h���n sau 5 phút)
        - 'schedule_units': Các lớp của một môn (hết hạn sau 15 giây)
        """
        key = self._get_key(user_id, cache_type, *args)
        
        self.cache[key] = {
            'data': data,
            'cached_at': datetime.now(),
            'expiry_seconds': expiry_seconds,
            'expires_at': datetime.now() + timedelta(seconds=expiry_seconds) if expiry_seconds > 0 else None
        }
    
    def get(self, user_id: int, cache_type: str, *args) -> Optional[Any]:
        """Lấy data từ cache, trả None n���u hết hạn hoặc không tồn t���i"""
        key = self._get_key(user_id, cache_type, *args)
        
        if key not in self.cache:
            return None
        
        cached = self.cache[key]
        
        # Kiểm tra hết hạn
        if cached['expires_at'] and datetime.now() >= cached['expires_at']:
            del self.cache[key]
            return None
        
        return cached['data']
    
    def is_expired(self, user_id: int, cache_type: str, *args) -> bool:
        """Ki���m tra cache có hết hạn không"""
        key = self._get_key(user_id, cache_type, *args)
        
        if key not in self.cache:
            return True
        
        cached = self.cache[key]
        if cached['expires_at'] and datetime.now() >= cached['expires_at']:
            return True
        
        return False
    
    def invalidate(self, user_id: int, cache_type: str, *args):
        """Xóa cache"""
        key = self._get_key(user_id, cache_type, *args)
        if key in self.cache:
            del self.cache[key]
    
    def invalidate_all(self, user_id: int):
        """Xóa tất cả cache c���a user"""
        keys_to_delete = [k for k in self.cache.keys() if k.startswith(f"{user_id}:")]
        for key in keys_to_delete:
            del self.cache[key]
    
    def get_expiring_caches(self, user_id: int) -> List[tuple]:
        """
        Lấy danh s��ch các cache sắp hết hạn trong 5 giây t���i
        Returns: List of (cache_type, args)
        """
        expiring = []
        now = datetime.now()
        threshold = now + timedelta(seconds=5)
        
        for key, cached in self.cache.items():
            if not key.startswith(f"{user_id}:"):
                continue
            
            if cached['expires_at'] and now < cached['expires_at'] <= threshold:
                parts = key.split(':', 2)
                cache_type = parts[1]
                args = tuple(parts[2].split(':')) if len(parts) > 2 and parts[2] else ()
                expiring.append((cache_type, args))
        
        return expiring
    
    def set_registered_classes(self, user_id: int, data: Any):
        """Cache lớp đã đ��ng ký (hết hạn khi đăng ký/hủy)"""
        self.set(user_id, 'registered_classes', data, -1)  # -1 = không tự ��ộng hết hạn
    
    def get_registered_classes(self, user_id: int) -> Optional[Any]:
        """Lấy danh sách lớp đ�� đăng ký"""
        return self.get(user_id, 'registered_classes')
    
    def invalidate_registered_classes(self, user_id: int):
        """Xóa cache lớp đã đ��ng ký (sau khi đăng ký hoặc hủy)"""
        self.invalidate(user_id, 'registered_classes')
    
    def set_study_types(self, user_id: int, data: Any):
        """Cache các chức năng đăng ký"""
        self.set(user_id, 'study_types', data, -1)
    
    def get_study_types(self, user_id: int) -> Optional[Any]:
        """Lấy các chức năng đăng ký"""
        return self.get(user_id, 'study_types')
    
    def set_available_courses(self, user_id: int, loai_hinh: str, data: Any):
        """Cache danh sách môn m��� đăng ký (hết hạn sau 5 phút)"""
        self.set(user_id, 'available_courses', data, 300, loai_hinh)
    
    def get_available_courses(self, user_id: int, loai_hinh: str) -> Optional[Any]:
        """L���y danh sách m��n mở đăng ký"""
        return self.get(user_id, 'available_courses', loai_hinh)
    
    def set_schedule_units(self, user_id: int, study_unit_id: str, loai_hinh: str, data: Any):
        """Cache danh sách lớp của một môn (hết hạn sau 15 gi��y)"""
        self.set(user_id, 'schedule_units', data, 15, study_unit_id, loai_hinh)
    
    def get_schedule_units(self, user_id: int, study_unit_id: str, loai_hinh: str) -> Optional[Any]:
        """Lấy danh sách lớp của một môn"""
        return self.get(user_id, 'schedule_units', study_unit_id, loai_hinh)
    
    def get_all_cached_schedule_units(self, user_id: int) -> Dict[tuple, Any]:
        """L���y tất cả cache schedule_units của user"""
        result = {}
        prefix = f"{user_id}:schedule_units:"
        
        for key, cached in self.cache.items():
            if key.startswith(prefix):
                parts = key.split(':', 3)
                if len(parts) >= 4:
                    study_unit_id, loai_hinh = parts[2], parts[3]
                    if not self.is_expired(user_id, 'schedule_units', study_unit_id, loai_hinh):
                        result[(study_unit_id, loai_hinh)] = cached['data']
        
        return result
