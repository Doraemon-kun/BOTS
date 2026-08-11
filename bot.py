import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import asyncio
from dotenv import load_dotenv
from typing import Dict, Any, Optional

from api_client import DKHPAPIClient
from session_manager import SessionManager
from response_cacher import ResponseCacher
from ui_manager import (
    UIManager, DashboardView, FunctionSelectView, CourseSelectView,
    ClassSelectView, AutoRegisterView, AddAutoClassModal, LoginModal,
    BackButton
)
from auto_register_manager import AutoRegistrationManager

# Load environment variables
load_dotenv()

class DKHPBot(commands.Bot):
    """Discord Bot cho tự động hóa đ��ng ký học phần HCMUE"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(command_prefix='/', intents=intents)
        
        # Initialize components
        self.api_client = DKHPAPIClient(
            api_key=os.getenv('API_KEY'),
            client_id=os.getenv('CLIENT_ID')
        )
        self.session_manager = SessionManager(self.api_client)
        self.response_cacher = ResponseCacher()
        self.auto_register_manager = AutoRegistrationManager(
            self.api_client,
            self.session_manager,
            self.response_cacher
        )
        
        # Store current views for each user
        self.user_views: Dict[int, Any] = {}
        
        # Store current context for navigation
        self.user_context: Dict[int, Dict[str, Any]] = {}
    
    async def setup_hook(self):
        """Setup hook called when bot starts"""
        # Start cleanup tasks
        self.session_manager.start_cleanup_task()
        self.background_refresh_task.start()
        
        # Sync commands
        guild_id = os.getenv('GUILD_ID')
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
    
    @tasks.loop(seconds=15)
    async def background_refresh_task(self):
        """Background task để refresh cache và check auto registration"""
        # Implement background refresh logic here
        pass
    
    async def close(self):
        """Cleanup when bot closes"""
        await self.api_client.close()
        await super().close()

# Create bot instance
bot = DKHPBot()

@bot.event
async def on_ready():
    print(f'{bot.user} đã kết nối đ���n Discord!')
    print(f'Bot ID: {bot.user.id}')

@bot.tree.command(name="login", description="Đăng nhập v��o hệ thống DKHP")
async def login_command(interaction: discord.Interaction):
    """Lệnh đăng nhập"""
    async def on_login_submit(modal_interaction: discord.Interaction, username: str, password: str):
        await modal_interaction.response.defer(thinking=True)
        
        try:
            # Đ��ng nhập
            await bot.session_manager.login(modal_interaction.user.id, username, password)
            
            # Lấy th��ng tin cần thiết
            await load_user_data(modal_interaction.user.id)
            
            # Hi���n thị dashboard
            await show_dashboard(modal_interaction)
            
        except Exception as e:
            embed = UIManager.create_result_embed(
                "Đăng nhập thất bại",
                f"Lỗi: {str(e)}",
                success=False
            )
            await modal_interaction.followup.send(embed=embed, ephemeral=True)
    
    modal = LoginModal(on_login_submit)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="dashboard", description="Hi���n thị b���ng điều khiển")
async def dashboard_command(interaction: discord.Interaction):
    """L���nh hiển thị dashboard"""
    session = bot.session_manager.get_session(interaction.user.id)
    
    if not session:
        await interaction.response.send_message(
            "Bạn chưa đ��ng nhập. Vui lòng sử dụng /login để đăng nhập.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # Refresh token if needed
        await bot.session_manager.refresh_token_if_needed(interaction.user.id)
        
        # Hiển thị dashboard
        await show_dashboard(interaction)
    except Exception as e:
        await interaction.followup.send(f"Lỗi: {str(e)}", ephemeral=True)

async def load_user_data(user_id: int):
    """Load tất c��� d��� liệu cần thiết cho user"""
    token = bot.session_manager.get_token(user_id)
    
    # B��ớc 2: Lấy m�� ngành
    study_programs = await bot.api_client.get_study_programs(token)
    bot.session_manager.set_study_programs(user_id, study_programs)
    
    # T��� động chọn nếu chỉ có 1 ngành
    if len(study_programs) == 1:
        program_id = study_programs[0]['StudyProgramID']
        bot.session_manager.set_selected_program(user_id, program_id)
    
    # Bước 3: Lấy thông tin đăng ký
    program_id = bot.session_manager.get_selected_program(user_id)
    if program_id:
        registration_info = await bot.api_client.get_registration_info(token, program_id)
        bot.session_manager.set_registration_info(user_id, registration_info)
        
        # Bước 4: Lấy lớp đã ��ăng ký
        rand_id = str(registration_info.get('RandID', ''))
        turn_id = str(registration_info.get('IdDot', ''))
        
        registered_classes = await bot.api_client.get_registered_classes(token, rand_id, turn_id)
        bot.response_cacher.set_registered_classes(user_id, registered_classes)
        
        # Bư���c 5: Lấy các chức năng đăng ký
        study_types = await bot.api_client.get_study_types(token)
        bot.response_cacher.set_study_types(user_id, study_types)
        
        # B��ớc 6: Load các môn h���c cho từng chức năng (background)
        asyncio.create_task(load_available_courses(user_id, registration_info))

async def load_available_courses(user_id: int, registration_info: Dict[str, Any]):
    """Load các môn học có thể đăng ký (ch���y background)"""
    try:
        token = bot.session_manager.get_token(user_id)
        program_id = bot.session_manager.get_selected_program(user_id)
        study_types = bot.response_cacher.get_study_types(user_id)
        
        year_study = registration_info.get('YearStudy', '')
        term_id = registration_info.get('TermID', '')
        
        # Lấy các ch���c năng đư���c hiển th���
        for func in study_types:
            if not func.get('HienThi', False):
                continue
            
            map_id = func.get('MapID')
            if not map_id or not registration_info.get(map_id, False):
                continue
            
            loai_hinh = func.get('LoaiHinh', '')
            
            try:
                courses = await bot.api_client.get_available_courses(
                    token, program_id, loai_hinh, year_study, term_id
                )
                bot.response_cacher.set_available_courses(user_id, loai_hinh, courses)
            except Exception as e:
                print(f"Error loading courses for {loai_hinh}: {e}")
        
    except Exception as e:
        print(f"Error in load_available_courses: {e}")

async def show_dashboard(interaction: discord.Interaction):
    """Hiển thị dashboard"""
    user_id = interaction.user.id
    session = bot.session_manager.get_session(user_id)
    registered_classes = bot.response_cacher.get_registered_classes(user_id)
    registration_info = bot.session_manager.get_registration_info(user_id)
    
    # Update activity
    bot.session_manager.update_activity(user_id)
    
    # Tạo embed
    embed = UIManager.create_dashboard_embed(session, registered_classes, registration_info)
    
    # Tạo view với callbacks
    view = DashboardView(
        on_register=lambda i: handle_register_start(i),
        on_unregister=lambda i: handle_unregister_start(i),
        on_auto_register=lambda i: handle_auto_register_view(i)
    )
    
    # Gửi hoặc edit message
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def handle_register_start(interaction: discord.Interaction):
    """X��� lý khi b���t đầu đăng ký học phần"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    # Lấy danh sách chức năng
    study_types = bot.response_cacher.get_study_types(user_id)
    registration_info = bot.session_manager.get_registration_info(user_id)
    
    # Filter ch��� các ch���c năng đư���c hi���n thị
    available_functions = []
    for func in study_types:
        if not func.get('HienThi', False):
            continue
        
        map_id = func.get('MapID')
        if not map_id or not registration_info.get(map_id, False):
            continue
        
        available_functions.append(func)
    
    # Hiển th��� select function
    embed = UIManager.create_function_selection_embed()
    view = FunctionSelectView(
        functions=available_functions,
        on_select=lambda i, v: handle_function_selected(i, v),
        on_back=lambda i: handle_back_to_dashboard(i)
    )
    
    await interaction.edit_original_response(embed=embed, view=view)

async def handle_function_selected(interaction: discord.Interaction, function_id: str):
    """Xử lý khi chọn chức năng"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    # L���y thông tin chức n��ng
    study_types = bot.response_cacher.get_study_types(user_id)
    selected_function = next((f for f in study_types if f['ChucNangID'] == function_id), None)
    
    if not selected_function:
        await interaction.followup.send("Không tìm thấy chức năng.", ephemeral=True)
        return
    
    loai_hinh = selected_function['LoaiHinh']
    function_name = selected_function['TenChucNang']
    
    # Lưu context
    bot.user_context[user_id] = {
        'function_id': function_id,
        'loai_hinh': loai_hinh,
        'function_name': function_name
    }
    
    # Lấy danh sách môn h���c
    available_courses = bot.response_cacher.get_available_courses(user_id, loai_hinh)
    
    if not available_courses:
        # Refresh cache
        token = bot.session_manager.get_token(user_id)
        program_id = bot.session_manager.get_selected_program(user_id)
        registration_info = bot.session_manager.get_registration_info(user_id)
        
        available_courses = await bot.api_client.get_available_courses(
            token, program_id, loai_hinh,
            registration_info['YearStudy'],
            registration_info['TermID']
        )
        bot.response_cacher.set_available_courses(user_id, loai_hinh, available_courses)
    
    # Hiển th��� danh s��ch môn h���c
    embed = UIManager.create_course_selection_embed(function_name, available_courses)
    view = CourseSelectView(
        courses=available_courses,
        on_select=lambda i, v: handle_course_selected(i, v),
        on_back=lambda i: handle_back_to_dashboard(i)
    )
    
    await interaction.edit_original_response(embed=embed, view=view)

async def handle_course_selected(interaction: discord.Interaction, study_unit_id: str):
    """Xử lý khi chọn môn học"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    context = bot.user_context.get(user_id, {})
    loai_hinh = context.get('loai_hinh', '')
    function_name = context.get('function_name', '')
    
    # Lấy thông tin m��n học
    available_courses = bot.response_cacher.get_available_courses(user_id, loai_hinh)
    course_name = ""
    course_id = ""
    
    for group in available_courses:
        for class_study_unit in group.get('classStudyUnits', []):
            for selection in class_study_unit.get('Selections', []):
                if selection.get('StudyUnitID') == study_unit_id:
                    course_name = selection.get('CurriculumName', '')
                    course_id = selection.get('CurriculumID', '')
                    break
    
    # Lưu context
    bot.user_context[user_id].update({
        'study_unit_id': study_unit_id,
        'course_name': course_name,
        'course_id': course_id
    })
    
    # Lấy danh sách lớp
    schedule_units = bot.response_cacher.get_schedule_units(user_id, study_unit_id, loai_hinh)
    
    if not schedule_units or bot.response_cacher.is_expired(user_id, 'schedule_units', study_unit_id, loai_hinh):
        # Refresh cache
        token = bot.session_manager.get_token(user_id)
        program_id = bot.session_manager.get_selected_program(user_id)
        
        schedule_units = await bot.api_client.get_available_schedule_units(
            token, program_id, loai_hinh, study_unit_id
        )
        bot.response_cacher.set_schedule_units(user_id, study_unit_id, loai_hinh, schedule_units)
    
    # Lưu schedule units vào context
    bot.user_context[user_id]['schedule_units'] = schedule_units
    
    # Hiển thị danh sách lớp
    embed = UIManager.create_class_selection_embed(function_name, course_name, course_id, schedule_units)
    view = ClassSelectView(
        classes=schedule_units,
        on_select=lambda i, v: handle_class_selected(i, v),
        on_back=lambda i: handle_back_to_dashboard(i)
    )
    
    await interaction.edit_original_response(embed=embed, view=view)

async def handle_class_selected(interaction: discord.Interaction, class_index: int):
    """X��� lý khi chọn lớp để đăng ký"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    context = bot.user_context.get(user_id, {})
    loai_hinh = context.get('loai_hinh', '')
    study_unit_id = context.get('study_unit_id', '')
    schedule_units = context.get('schedule_units', [])
    
    if class_index >= len(schedule_units):
        await interaction.followup.send("Lớp kh��ng hợp lệ.", ephemeral=True)
        return
    
    selected_class = schedule_units[class_index]
    
    try:
        token = bot.session_manager.get_token(user_id)
        program_id = bot.session_manager.get_selected_program(user_id)
        registration_info = bot.session_manager.get_registration_info(user_id)
        turn_id = str(registration_info.get('IdDot', ''))
        
        # Chuẩn bị data đ��� đăng ký
        register_data = {
            'CurriculumID': selected_class.get('CurriculumID', ''),
            'ScheduleStudyUnitAlias': selected_class.get('ScheduleStudyUnitAlias', ''),
            'ScheduleStudyUnitID': selected_class.get('ScheduleStudyUnitID', ''),
            'CurriculumName': selected_class.get('CurriculumName', ''),
            'StudyUnitID': study_unit_id,
            'TypeName': selected_class.get('TypeName', 'Lý thuyết'),
            'Credits': selected_class.get('Credits', 0),
            'StudentQuotas': selected_class.get('StudentQuotas', ''),
            'StudyUnitTypeID': selected_class.get('StudyUnitTypeID', 1),
            'MaxStudentNumber': selected_class.get('MaxStudentNumber'),
            'NumberOfStudents': selected_class.get('NumberOfStudents', 0),
            'Schedules': selected_class.get('Schedules', ''),
            'ProfessorName': selected_class.get('ProfessorName', ''),
            'IsRegisted': False,
            'ListOfClassStudentID': selected_class.get('ListOfClassStudentID', ''),
            'NumberOfChilds': selected_class.get('NumberOfChilds', 0),
            'FeeDebt': selected_class.get('FeeDebt', ''),
            'ParentID': selected_class.get('ParentID', ''),
            'UpdateDate': selected_class.get('UpdateDate', ''),
            'NumberRegistOfEmpty': selected_class.get('NumberRegistOfEmpty', '0'),
            'IsHocTrucTuyen': selected_class.get('IsHocTrucTuyen'),
            'Note': selected_class.get('Note'),
            'isOpen': True,
            'isOpenChilrentTask': False
        }
        
        # Đăng ký
        result = await bot.api_client.register_class(token, turn_id, program_id, loai_hinh, register_data)
        
        # Invalidate cache
        bot.response_cacher.invalidate_registered_classes(user_id)
        
        # Hiển thị kết quả
        class_id = selected_class.get('ScheduleStudyUnitAlias', '')
        embed = UIManager.create_result_embed("Đăng ký học phần", result, success=True)
        
        await interaction.edit_original_response(embed=embed, view=None)
        
        # Quay về dashboard sau 3 gi��y
        await asyncio.sleep(3)
        await show_dashboard(interaction)
        
    except Exception as e:
        embed = UIManager.create_result_embed("Đăng ký học phần", f"Lỗi: {str(e)}", success=False)
        await interaction.edit_original_response(embed=embed, view=None)

async def handle_unregister_start(interaction: discord.Interaction):
    """Xử lý khi bắt đầu hủy học phần"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    # Lấy danh sách lớp đã đăng ký
    registered_classes_data = bot.response_cacher.get_registered_classes(user_id)
    rows = registered_classes_data.get('Rows', [])
    
    if not rows:
        await interaction.followup.send("Bạn chưa đăng ký l���p nào.", ephemeral=True)
        return
    
    # Hiển thị danh sách
    embed = UIManager.create_unregister_embed(rows)
    view = ClassSelectView(
        classes=rows,
        on_select=lambda i, v: handle_unregister_class(i, v),
        on_back=lambda i: handle_back_to_dashboard(i)
    )
    
    # Lưu context
    bot.user_context[user_id] = {'unregister_classes': rows}
    
    await interaction.edit_original_response(embed=embed, view=view)

async def handle_unregister_class(interaction: discord.Interaction, class_index: int):
    """Xử lý khi chọn l���p để h���y"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    context = bot.user_context.get(user_id, {})
    rows = context.get('unregister_classes', [])
    
    if class_index >= len(rows):
        await interaction.followup.send("Lớp kh��ng hợp lệ.", ephemeral=True)
        return
    
    selected_class = rows[class_index]
    
    try:
        token = bot.session_manager.get_token(user_id)
        program_id = bot.session_manager.get_selected_program(user_id)
        registration_info = bot.session_manager.get_registration_info(user_id)
        turn_id = str(registration_info.get('IdDot', ''))
        
        # H���y lớp
        result = await bot.api_client.remove_class(token, turn_id, program_id, selected_class)
        
        # Invalidate cache
        bot.response_cacher.invalidate_registered_classes(user_id)
        
        # Hi���n th��� kết qu���
        embed = UIManager.create_result_embed("Hủy học phần", result, success=True)
        await interaction.edit_original_response(embed=embed, view=None)
        
        # Quay về dashboard sau 3 giây
        await asyncio.sleep(3)
        await show_dashboard(interaction)
        
    except Exception as e:
        embed = UIManager.create_result_embed("H���y học phần", f"L���i: {str(e)}", success=False)
        await interaction.edit_original_response(embed=embed, view=None)

async def handle_auto_register_view(interaction: discord.Interaction):
    """Hiển thị trang tự động đăng ký"""
    await interaction.response.defer()
    
    user_id = interaction.user.id
    bot.session_manager.update_activity(user_id)
    
    # Lấy danh sách lớp chờ đăng ký
    auto_classes = bot.session_manager.get_auto_register_classes(user_id)
    
    # Hiển thị
    embed = UIManager.create_auto_register_embed(auto_classes)
    view = AutoRegisterView(
        on_add=lambda i: handle_add_auto_class(i),
        on_remove=lambda i: handle_remove_auto_class_start(i),
        on_back=lambda i: handle_back_to_dashboard(i)
    )
    
    await interaction.edit_original_response(embed=embed, view=view)

async def handle_add_auto_class(interaction: discord.Interaction):
    """Xử lý thêm lớp t��� động đăng ký"""
    async def on_submit(modal_interaction: discord.Interaction, curriculum_id: str, class_id: str):
        await modal_interaction.response.defer()
        
        user_id = modal_interaction.user.id
        
        # Thêm vào danh sách
        # TODO: Validate và lấy loai_hinh
        loai_hinh = "KH"  # Default
        bot.session_manager.add_auto_register_class(user_id, curriculum_id, class_id, loai_hinh)
        
        # Start monitoring nếu chưa ch���y
        if not bot.auto_register_manager.is_monitoring(user_id):
            await bot.auto_register_manager.start_monitoring(user_id)
        
        # Refresh view
        await handle_auto_register_view(modal_interaction)
    
    modal = AddAutoClassModal(on_submit)
    await interaction.response.send_modal(modal)

async def handle_remove_auto_class_start(interaction: discord.Interaction):
    """X��� lý xóa l���p tự động đ��ng ký"""
    # TODO: Implement remove logic similar to unregister
    await interaction.response.send_message("Chức năng đang ph��t triển.", ephemeral=True)

async def handle_back_to_dashboard(interaction: discord.Interaction):
    """Quay v��� dashboard"""
    await interaction.response.defer()
    await show_dashboard(interaction)

# Run bot
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print("Error: DISCORD_TOKEN không được tìm thấy trong file .env")
    else:
        bot.run(TOKEN)
