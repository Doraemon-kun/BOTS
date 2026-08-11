import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from api_client import DKHPAPIClient
from session_manager import SessionManager
from response_cacher import ResponseCacher

class AutoRegistrationManager:
    """Qu���n lý t��� động ��ăng ký h���c ph���n"""
    
    def __init__(self, api_client: DKHPAPIClient, session_manager: SessionManager, 
                 response_cacher: ResponseCacher):
        self.api_client = api_client
        self.session_manager = session_manager
        self.response_cacher = response_cacher
        self.running_tasks: Dict[int, asyncio.Task] = {}
        self.status_callbacks: Dict[int, Callable] = {}
    
    def set_status_callback(self, user_id: int, callback: Callable):
        """Đặt callback để thông báo status update"""
        self.status_callbacks[user_id] = callback
    
    async def _notify_status(self, user_id: int, curriculum_id: str, class_id: str, status: str):
        """Thông báo status update"""
        if user_id in self.status_callbacks:
            try:
                await self.status_callbacks[user_id](curriculum_id, class_id, status)
            except:
                pass
    
    async def start_monitoring(self, user_id: int):
        """Bắt đ���u theo dõi và tự động đăng ký cho user"""
        if user_id in self.running_tasks:
            return  # Đ�� ch���y rồi
        
        task = asyncio.create_task(self._monitor_loop(user_id))
        self.running_tasks[user_id] = task
    
    async def stop_monitoring(self, user_id: int):
        """Dừng theo dõi cho user"""
        if user_id in self.running_tasks:
            self.running_tasks[user_id].cancel()
            try:
                await self.running_tasks[user_id]
            except asyncio.CancelledError:
                pass
            del self.running_tasks[user_id]
    
    async def _monitor_loop(self, user_id: int):
        """Vòng lặp theo dõi và tự động đăng ký"""
        while True:
            try:
                await asyncio.sleep(15)  # Check m���i 15 gi��y
                
                # Kiểm tra session còn t���n tại không
                session = self.session_manager.get_session(user_id)
                if not session:
                    # Thử khôi phục từ credentials
                    restored = await self.session_manager.restore_session_from_credentials(user_id)
                    if not restored:
                        break
                    session = self.session_manager.get_session(user_id)
                
                # Refresh token nếu cần
                await self.session_manager.refresh_token_if_needed(user_id)
                
                # Lấy danh sách lớp chờ đăng ký
                auto_classes = self.session_manager.get_auto_register_classes(user_id)
                if not auto_classes:
                    break  # Không còn lớp nào cần đăng ký
                
                # Lấy thông tin cần thiết
                token = self.session_manager.get_token(user_id)
                study_program_id = self.session_manager.get_selected_program(user_id)
                registration_info = self.session_manager.get_registration_info(user_id)
                
                if not token or not study_program_id or not registration_info:
                    continue
                
                turn_id = str(registration_info.get('IdDot', ''))
                year_study = registration_info.get('YearStudy', '')
                term_id = registration_info.get('TermID', '')
                
                # Ki���m tra từng l���p
                for auto_class in auto_classes[:]:  # Copy list đ��� có thể modify
                    curriculum_id = auto_class['curriculum_id']
                    class_id = auto_class['class_id']
                    loai_hinh = auto_class['loai_hinh']
                    
                    try:
                        # Kiểm tra xem môn h���c có tồn tại không (cache 5 ph��t)
                        available_courses = self.response_cacher.get_available_courses(user_id, loai_hinh)
                        
                        if not available_courses or self.response_cacher.is_expired(user_id, 'available_courses', loai_hinh):
                            # Refresh cache
                            available_courses = await self.api_client.get_available_courses(
                                token, study_program_id, loai_hinh, year_study, term_id
                            )
                            self.response_cacher.set_available_courses(user_id, loai_hinh, available_courses)
                        
                        # Tìm study_unit_id từ curriculum_id
                        study_unit_id = None
                        for group in available_courses:
                            for class_study_unit in group.get('classStudyUnits', []):
                                for selection in class_study_unit.get('Selections', []):
                                    if selection.get('CurriculumID') == curriculum_id:
                                        study_unit_id = selection.get('StudyUnitID')
                                        break
                                if study_unit_id:
                                    break
                            if study_unit_id:
                                break
                        
                        if not study_unit_id:
                            # Môn không tồn t���i
                            await self._notify_status(user_id, curriculum_id, class_id, "Lớp không tồn tại")
                            continue
                        
                        # L���y thông tin l���p học ph���n (cache 15 gi��y)
                        schedule_units = self.response_cacher.get_schedule_units(user_id, study_unit_id, loai_hinh)
                        
                        if not schedule_units or self.response_cacher.is_expired(user_id, 'schedule_units', study_unit_id, loai_hinh):
                            # Refresh cache
                            schedule_units = await self.api_client.get_available_schedule_units(
                                token, study_program_id, loai_hinh, study_unit_id
                            )
                            self.response_cacher.set_schedule_units(user_id, study_unit_id, loai_hinh, schedule_units)
                        
                        # Tìm lớp c��� thể
                        target_class = None
                        for unit in schedule_units:
                            unit_class_id = unit.get('ScheduleStudyUnitAlias', unit.get('CurriculumID', ''))
                            if unit_class_id == class_id:
                                target_class = unit
                                break
                        
                        if not target_class:
                            # Lớp không tồn tại
                            await self._notify_status(user_id, curriculum_id, class_id, "Lớp không tồn tại")
                            continue
                        
                        # Kiểm tra xem đã đăng ký chưa
                        if target_class.get('IsRegisted', False):
                            # Đ�� đăng ký rồi, xóa khỏi danh sách
                            self.session_manager.remove_auto_register_class(user_id, curriculum_id, class_id)
                            await self._notify_status(user_id, curriculum_id, class_id, "Đã đăng ký thành công")
                            continue
                        
                        # Kiểm tra còn chỗ không
                        num_empty = int(target_class.get('NumberRegistOfEmpty', '0'))
                        
                        if num_empty > 0:
                            # Còn chỗ, th��� đăng ký
                            # Chu���n bị data để đăng ký
                            register_data = {
                                'CurriculumID': target_class.get('CurriculumID', class_id),
                                'ScheduleStudyUnitAlias': target_class.get('ScheduleStudyUnitAlias', class_id),
                                'ScheduleStudyUnitID': target_class.get('ScheduleStudyUnitID', class_id),
                                'CurriculumName': target_class.get('CurriculumName', ''),
                                'StudyUnitID': study_unit_id,
                                'TypeName': target_class.get('TypeName', 'Lý thuyết'),
                                'Credits': target_class.get('Credits', 0),
                                'StudentQuotas': target_class.get('StudentQuotas', ''),
                                'StudyUnitTypeID': target_class.get('StudyUnitTypeID', 1),
                                'MaxStudentNumber': target_class.get('MaxStudentNumber'),
                                'NumberOfStudents': target_class.get('NumberOfStudents', 0),
                                'Schedules': target_class.get('Schedules', ''),
                                'ProfessorName': target_class.get('ProfessorName', ''),
                                'IsRegisted': False,
                                'ListOfClassStudentID': target_class.get('ListOfClassStudentID', ''),
                                'NumberOfChilds': target_class.get('NumberOfChilds', 0),
                                'FeeDebt': target_class.get('FeeDebt', ''),
                                'ParentID': target_class.get('ParentID', ''),
                                'UpdateDate': target_class.get('UpdateDate', ''),
                                'NumberRegistOfEmpty': str(num_empty),
                                'IsHocTrucTuyen': target_class.get('IsHocTrucTuyen'),
                                'Note': target_class.get('Note'),
                                'isOpen': True,
                                'isOpenChilrentTask': False
                            }
                            
                            # Kiểm tra xem môn này đã đăng k�� lớp khác chưa
                            registered_classes_data = self.response_cacher.get_registered_classes(user_id)
                            if registered_classes_data:
                                rows = registered_classes_data.get('Rows', [])
                                old_class = None
                                
                                for row in rows:
                                    # So sánh curriculum_id (không có prefix năm)
                                    row_curriculum_id = row.get('CurriculumID', '')
                                    if row_curriculum_id == curriculum_id or row_curriculum_id.endswith(curriculum_id):
                                        old_class = row
                                        break
                                
                                # Nếu đã ��ăng ký lớp khác của cùng môn, hủy trước
                                if old_class:
                                    try:
                                        await self.api_client.remove_class(token, turn_id, study_program_id, old_class)
                                        # Invalidate cache
                                        self.response_cacher.invalidate_registered_classes(user_id)
                                    except Exception as e:
                                        print(f"Failed to remove old class: {e}")
                                        # Ti���p tục thử đăng ký
                            
                            # Đăng k�� lớp mới
                            try:
                                result = await self.api_client.register_class(
                                    token, turn_id, study_program_id, loai_hinh, register_data
                                )
                                
                                # Thành công
                                self.session_manager.remove_auto_register_class(user_id, curriculum_id, class_id)
                                self.response_cacher.invalidate_registered_classes(user_id)
                                await self._notify_status(user_id, curriculum_id, class_id, "Đã đăng ký thành công")
                                
                            except Exception as e:
                                error_msg = str(e)
                                await self._notify_status(user_id, curriculum_id, class_id, f"Lỗi: {error_msg}")
                        else:
                            # Hết chỗ, tiếp t���c chờ
                            await self._notify_status(user_id, curriculum_id, class_id, "")
                    
                    except Exception as e:
                        print(f"Error processing auto register for {curriculum_id}-{class_id}: {e}")
                        await self._notify_status(user_id, curriculum_id, class_id, f"L���i: {str(e)}")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in monitor loop for user {user_id}: {e}")
                await asyncio.sleep(15)
    
    def is_monitoring(self, user_id: int) -> bool:
        """Ki���m tra có ��ang theo dõi user không"""
        return user_id in self.running_tasks
