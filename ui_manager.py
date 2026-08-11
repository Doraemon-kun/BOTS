import discord
from discord import ui
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
import re

def clean_name(name: str) -> str:
    """Loại bỏ dấu cách th���a trong tên"""
    return re.sub(r'\s+', ' ', name).strip()

def parse_schedules(schedules_html: str) -> str:
    """Parse HTML schedules thành text dễ đọc"""
    # Loại bỏ HTML tags
    schedules = schedules_html.replace('<br/>', '\n').replace('<br>', '\n')
    schedules = re.sub(r'<[^>]+>', '', schedules)
    return schedules.strip()

def format_date(date_str: str) -> str:
    """Chuyển đổi MM/DD/YYYY sang DD/MM/YYYY"""
    try:
        parts = date_str.split(' ')
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else ''
        
        month, day, year = date_part.split('/')
        return f"{day}/{month}/{year}" + (f" {time_part}" if time_part else "")
    except:
        return date_str

class UIManager:
    """Quản lý UI của Discord bot"""
    
    @staticmethod
    def create_dashboard_embed(session: Dict[str, Any], registered_classes: Dict[str, Any], 
                               registration_info: Dict[str, Any]) -> discord.Embed:
        """T���o embed cho dashboard chính"""
        embed = discord.Embed(
            title="Bảng điều khiển Đăng ký h���c ph���n",
            color=discord.Color.blue()
        )
        
        # Lời chào
        full_name = clean_name(session['full_name'])
        embed.add_field(name="", value=f"Xin ch��o, **{full_name}**", inline=False)
        
        # Th��ng tin học kỳ
        year_study = registration_info.get('YearStudy', 'N/A')
        term_id = registration_info.get('TermID', 'N/A')
        begin_date = format_date(registration_info.get('BeginDate', ''))
        end_date = format_date(registration_info.get('EndDate', ''))
        
        embed.add_field(
            name="Học kỳ và thời gian",
            value=f"**Học kỳ:** {term_id} - **Năm học:** {year_study}\n"
                  f"**Thời gian đăng ký:** {begin_date} đến {end_date}",
            inline=False
        )
        
        # Thông tin ��ăng k��
        rows = registered_classes.get('Rows', [])
        total_classes = len(rows)
        total_credits = sum(c.get('Credits', 0) for c in rows)
        
        embed.add_field(
            name="Thông tin Đăng ký",
            value=f"**S��� học phần đã đăng ký:** {total_classes}\n**T���ng tín ch���:** {total_credits}",
            inline=False
        )
        
        # Chi tiết lớp đã đăng ký
        if rows:
            classes_text = ""
            conflict_classes = []
            
            for row in rows[:10]:  # Giới hạn 10 l���p để không vượt qu�� giới h���n embed
                curriculum_name = clean_name(row.get('CurriculumName', 'N/A'))
                class_id = row.get('ScheduleStudyUnitAlias', 'N/A')
                professor = clean_name(row.get('ProfessorName', 'N/A'))
                begin_date = format_date(row.get('BeginDate', ''))
                end_date = format_date(row.get('EndDate', ''))
                
                classes_text += f"• {curriculum_name} - {class_id}: {professor} ({begin_date} → {end_date})\n"
                
                if row.get('TrungLich', False):
                    conflict_classes.append(class_id)
            
            if len(rows) > 10:
                classes_text += f"\n... và {len(rows) - 10} lớp khác"
            
            embed.add_field(
                name="Chi ti���t l���p h���c phần đã đăng k��",
                value=classes_text or "Chưa có lớp nào",
                inline=False
            )
            
            # Cảnh báo tr��ng l���ch
            if conflict_classes:
                embed.add_field(
                    name="⚠️ CẢNH BÁO TRÙNG L���CH",
                    value="CÓ CÁC LỚP SAU B��� ĐĂNG KÝ TRÙNG L���CH. VUI LÒNG KIỂM TRA LẠI TRÊN WEB DKHP:\n" +
                          "\n".join(f"• {c}" for c in conflict_classes),
                    inline=False
                )
        
        # Footer với thông tin sinh vi��n
        embed.set_footer(text=f"{full_name} - {session['student_id']}")
        embed.timestamp = datetime.now()
        
        return embed
    
    @staticmethod
    def create_function_selection_embed() -> discord.Embed:
        """Tạo embed cho chọn chức năng"""
        embed = discord.Embed(
            title="Bảng đi���u khiển Đăng ký học phần",
            description="**Đăng ký học ph���n**\n\nVui lòng chọn chức năng:",
            color=discord.Color.green()
        )
        return embed
    
    @staticmethod
    def create_course_selection_embed(function_name: str, available_courses: List[Dict[str, Any]]) -> discord.Embed:
        """Tạo embed cho chọn học phần"""
        embed = discord.Embed(
            title="Bảng điều khiển Đăng ký h���c phần",
            description=f"**Đăng ký học phần ({function_name})**\n\n**Các học phần mở ��ăng ký:**",
            color=discord.Color.green()
        )
        
        # Group by CurriculumTypeGroupName
        for group in available_courses:
            group_name = group.get('CurriculumTypeGroupName', 'Khác')
            courses_list = []
            
            for class_study_unit in group.get('classStudyUnits', []):
                for selection in class_study_unit.get('Selections', []):
                    curriculum_name = clean_name(selection.get('CurriculumName', ''))
                    curriculum_id = selection.get('CurriculumID', '')
                    credits = selection.get('Credits', 0)
                    num_schedules = selection.get('NumberOfScheduleStudyUnit', 0)
                    
                    courses_list.append(f"• {curriculum_name} - {curriculum_id} ({credits} TC - {num_schedules} lớp)")
            
            if courses_list:
                # Chia thành nhiều field nếu quá dài
                courses_text = "\n".join(courses_list)
                if len(courses_text) > 1024:
                    # Split into multiple fields
                    chunks = []
                    current_chunk = []
                    current_length = 0
                    
                    for course in courses_list:
                        if current_length + len(course) + 1 > 1024:
                            chunks.append("\n".join(current_chunk))
                            current_chunk = [course]
                            current_length = len(course)
                        else:
                            current_chunk.append(course)
                            current_length += len(course) + 1
                    
                    if current_chunk:
                        chunks.append("\n".join(current_chunk))
                    
                    for i, chunk in enumerate(chunks):
                        field_name = f"{group_name}" if i == 0 else f"{group_name} (tiếp)"
                        embed.add_field(name=field_name, value=chunk, inline=False)
                else:
                    embed.add_field(name=group_name, value=courses_text, inline=False)
        
        return embed
    
    @staticmethod
    def create_class_selection_embed(function_name: str, course_name: str, course_id: str,
                                     schedule_units: List[Dict[str, Any]]) -> discord.Embed:
        """Tạo embed cho chọn lớp"""
        embed = discord.Embed(
            title="Bảng điều khi���n Đăng ký học phần",
            description=f"**Đăng ký h���c ph���n ({function_name})**\n\n**Môn:** {course_name} - {course_id}",
            color=discord.Color.green()
        )
        
        classes_text = "**Các lớp mở hiện tại:**\n\n"
        
        for idx, unit in enumerate(schedule_units, 1):
            class_id = unit.get('ScheduleStudyUnitAlias', unit.get('CurriculumID', 'N/A'))
            professor = clean_name(unit.get('ProfessorName', 'N/A'))
            num_students = unit.get('NumberOfStudents', 0)
            quotas = unit.get('StudentQuotas', '0-0')
            num_empty = unit.get('NumberRegistOfEmpty', '0')
            schedules = parse_schedules(unit.get('Schedules', ''))
            is_registered = unit.get('IsRegisted', False)
            
            # Parse quotas
            try:
                min_quota, max_quota = quotas.split('-')
                max_quota = int(max_quota)
            except:
                max_quota = num_students
            
            status = "��� Đã đăng ký" if is_registered else f"({num_students}/{max_quota}, trống {num_empty})"
            
            classes_text += f"**{idx}. {class_id}:** {status} - {professor}\n"
            
            # Add schedules (first 3 lines only)
            schedule_lines = schedules.split('\n')[:3]
            for line in schedule_lines:
                if line.strip():
                    classes_text += f"  {line.strip()}\n"
            
            if len(schedule_lines) > 3:
                classes_text += "  ...\n"
            
            classes_text += "\n"
        
        # Split into multiple fields if too long
        if len(classes_text) > 1024:
            parts = []
            current_part = ""
            
            for line in classes_text.split('\n'):
                if len(current_part) + len(line) + 1 > 1024:
                    parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            
            if current_part:
                parts.append(current_part)
            
            for i, part in enumerate(parts):
                field_name = "Danh sách lớp" if i == 0 else "Danh sách lớp (ti���p)"
                embed.add_field(name=field_name, value=part, inline=False)
        else:
            embed.add_field(name="Danh sách lớp", value=classes_text, inline=False)
        
        return embed
    
    @staticmethod
    def create_unregister_embed(registered_classes: List[Dict[str, Any]]) -> discord.Embed:
        """Tạo embed cho hủy học phần"""
        embed = discord.Embed(
            title="Bảng điều khiển Đ��ng ký học phần",
            description="**H���y học phần**\n\n**C��c lớp h���c phần đã đăng ký:**",
            color=discord.Color.orange()
        )
        
        classes_text = ""
        for idx, row in enumerate(registered_classes, 1):
            curriculum_name = clean_name(row.get('CurriculumName', 'N/A'))
            class_id = row.get('ScheduleStudyUnitAlias', 'N/A')
            professor = clean_name(row.get('ProfessorName', 'N/A'))
            begin_date = format_date(row.get('BeginDate', ''))
            end_date = format_date(row.get('EndDate', ''))
            
            classes_text += f"{idx}. {curriculum_name} - {class_id}: {professor} ({begin_date} → {end_date})\n"
        
        embed.add_field(name="Danh sách", value=classes_text or "Chưa có lớp nào", inline=False)
        
        return embed
    
    @staticmethod
    def create_auto_register_embed(auto_classes: List[Dict[str, str]]) -> discord.Embed:
        """Tạo embed cho t��� động đ��ng ký"""
        embed = discord.Embed(
            title="Bảng đi���u khiển Đăng ký học ph���n",
            description="**T��� đ���ng đ��ng ký học phần**",
            color=discord.Color.purple()
        )
        
        if auto_classes:
            classes_text = ""
            for cls in auto_classes:
                curriculum_id = cls.get('curriculum_id', 'N/A')
                class_id = cls.get('class_id', 'N/A')
                status = cls.get('status', '')
                
                status_text = f" ({status})" if status else ""
                classes_text += f"• {curriculum_id} - {class_id}{status_text}\n"
            
            embed.add_field(name="Các lớp đang chờ đăng ký t��� động", value=classes_text, inline=False)
        else:
            embed.add_field(name="Các lớp đang chờ đăng ký t��� động", value="(Trống)", inline=False)
        
        return embed
    
    @staticmethod
    def create_result_embed(title: str, message: str, success: bool = True) -> discord.Embed:
        """Tạo embed cho kết quả"""
        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(
            title=f"Bảng điều khiển Đăng ký học ph���n\n{title}",
            description=message,
            color=color
        )
        return embed


class DashboardView(ui.View):
    """View cho dashboard ch��nh"""
    
    def __init__(self, on_register: Callable, on_unregister: Callable, on_auto_register: Callable):
        super().__init__(timeout=300)  # 5 phút timeout
        self.on_register = on_register
        self.on_unregister = on_unregister
        self.on_auto_register = on_auto_register
    
    @ui.button(label="Đ��ng ký học phần", style=discord.ButtonStyle.green)
    async def register_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_register(interaction)
    
    @ui.button(label="Hủy h���c ph���n", style=discord.ButtonStyle.danger)
    async def unregister_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_unregister(interaction)
    
    @ui.button(label="Tự động đăng ký học phần", style=discord.ButtonStyle.primary)
    async def auto_register_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_auto_register(interaction)


class BackButton(ui.View):
    """View với nút quay về"""
    
    def __init__(self, on_back: Callable):
        super().__init__(timeout=300)
        self.on_back = on_back
    
    @ui.button(label="��� Quay về Dashboard", style=discord.ButtonStyle.gray)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_back(interaction)


class FunctionSelectView(ui.View):
    """View cho chọn chức năng ��ăng ký"""
    
    def __init__(self, functions: List[Dict[str, Any]], on_select: Callable, on_back: Callable):
        super().__init__(timeout=300)
        self.on_select = on_select
        self.on_back = on_back
        
        # Tạo select menu
        options = []
        for func in functions:
            label = func.get('TenChucNang', 'N/A')
            value = func.get('ChucNangID', '0')
            options.append(discord.SelectOption(label=label, value=value))
        
        select = ui.Select(placeholder="Chọn ch���c năng...", options=options, custom_id="function_select")
        select.callback = self._on_select
        self.add_item(select)
        
        # N��t quay về
        back_btn = ui.Button(label="��� Quay về Dashboard", style=discord.ButtonStyle.gray)
        back_btn.callback = self.on_back
        self.add_item(back_btn)
    
    async def _on_select(self, interaction: discord.Interaction):
        select = [item for item in self.children if isinstance(item, ui.Select)][0]
        await self.on_select(interaction, select.values[0])


class CourseSelectView(ui.View):
    """View cho ch���n học ph���n"""
    
    def __init__(self, courses: List[Dict[str, Any]], on_select: Callable, on_back: Callable):
        super().__init__(timeout=300)
        self.on_select = on_select
        self.on_back = on_back
        
        # T���o select menu (giới hạn 25 options)
        options = []
        for group in courses:
            for class_study_unit in group.get('classStudyUnits', []):
                for selection in class_study_unit.get('Selections', []):
                    if len(options) >= 25:
                        break
                    
                    curriculum_name = clean_name(selection.get('CurriculumName', ''))[:80]
                    study_unit_id = selection.get('StudyUnitID', '')
                    curriculum_id = selection.get('CurriculumID', '')
                    
                    options.append(discord.SelectOption(
                        label=f"{curriculum_name} - {curriculum_id}",
                        value=study_unit_id
                    ))
        
        if options:
            select = ui.Select(placeholder="Chọn học phần...", options=options, custom_id="course_select")
            select.callback = self._on_select
            self.add_item(select)
        
        # Nút quay về
        back_btn = ui.Button(label="��� Quay về Dashboard", style=discord.ButtonStyle.gray)
        back_btn.callback = self.on_back
        self.add_item(back_btn)
    
    async def _on_select(self, interaction: discord.Interaction):
        select = [item for item in self.children if isinstance(item, ui.Select)][0]
        await self.on_select(interaction, select.values[0])


class ClassSelectView(ui.View):
    """View cho chọn lớp"""
    
    def __init__(self, classes: List[Dict[str, Any]], on_select: Callable, on_back: Callable):
        super().__init__(timeout=300)
        self.on_select = on_select
        self.on_back = on_back
        
        # Tạo select menu
        options = []
        for idx, cls in enumerate(classes, 1):
            class_id = cls.get('ScheduleStudyUnitAlias', cls.get('CurriculumID', 'N/A'))
            professor = clean_name(cls.get('ProfessorName', 'N/A'))
            num_empty = cls.get('NumberRegistOfEmpty', '0')
            
            label = f"({idx}) {class_id} - {professor} (trống: {num_empty})"[:100]
            options.append(discord.SelectOption(label=label, value=str(idx - 1)))
        
        if options:
            select = ui.Select(placeholder="Chọn lớp...", options=options, custom_id="class_select")
            select.callback = self._on_select
            self.add_item(select)
        
        # Nút quay về
        back_btn = ui.Button(label="��� Quay về Dashboard", style=discord.ButtonStyle.gray)
        back_btn.callback = self.on_back
        self.add_item(back_btn)
    
    async def _on_select(self, interaction: discord.Interaction):
        select = [item for item in self.children if isinstance(item, ui.Select)][0]
        await self.on_select(interaction, int(select.values[0]))


class AutoRegisterView(ui.View):
    """View cho tự động đăng ký"""
    
    def __init__(self, on_add: Callable, on_remove: Callable, on_back: Callable):
        super().__init__(timeout=300)
        self.on_add = on_add
        self.on_remove = on_remove
        self.on_back = on_back
    
    @ui.button(label="��� Thêm lớp", style=discord.ButtonStyle.green)
    async def add_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_add(interaction)
    
    @ui.button(label="➖ Xóa lớp", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_remove(interaction)
    
    @ui.button(label="◀ Quay về Dashboard", style=discord.ButtonStyle.gray)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.on_back(interaction)


class AddAutoClassModal(ui.Modal, title="Thêm lớp tự ��ộng đăng ký"):
    """Modal ��ể thêm l���p tự động đăng ký"""
    
    curriculum_id = ui.TextInput(
        label="Mã học phần",
        placeholder="VD: PHYS1417",
        required=True
    )
    
    class_id = ui.TextInput(
        label="Mã l���p",
        placeholder="VD: 2611PHYS141702",
        required=True
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self._on_submit = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit(interaction, str(self.curriculum_id), str(self.class_id))


class LoginModal(ui.Modal, title="Đ��ng nhập hệ th���ng DKHP"):
    """Modal đ��� đ��ng nhập"""
    
    username = ui.TextInput(
        label="MSSV",
        placeholder="VD: 50.01.102.020",
        required=True
    )
    
    password = ui.TextInput(
        label="Mật kh���u web Online",
        style=discord.TextStyle.short,
        required=True
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self._on_submit = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit(interaction, str(self.username), str(self.password))
