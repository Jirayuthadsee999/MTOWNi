import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import json, os, shutil
from datetime import datetime, time
import pytz

# ================= ตั้งค่า =================
TOKEN = "MTM5ODYxODIwNzc2NTM5NzYxNQ.GtG4f7.om6a8fL0PUSKO2-cjfYrB3B-Xe2SBN24QnQX6M"

DEPARTMENT_CHANNELS = {  # ห้องแจ้งเตือน
    "ตำรวจ": 1337754520335290431,
    "หมอ": 1308459559047663636,
    "สภา": 1337974934638690386
}

DEPARTMENTS = {  # ยศของหน่วยงาน
    "ตำรวจ": 1309903906171650111,
    "หมอ": 1309905561378095225,
    "สภา": 1329732963914747936
}

DEPARTMENT_IMAGES = {  # โลโก้หน่วยงาน
    "ตำรวจ": "https://cdn.discordapp.com/attachments/1385580108739379360/1408306378191409242/1394955799368830996.jpg?ex=68a94305&is=68a7f185&hm=cf6511772244abe3321035c34bbadaf616324e240b433ce94c9c823f248ed528&",
    "หมอ": "https://cdn.discordapp.com/attachments/1385580108739379360/1408306378191409242/1394955799368830996.jpg?ex=68a94305&is=68a7f185&hm=cf6511772244abe3321035c34bbadaf616324e240b433ce94c9c823f248ed528&",
    "สภา": "https://cdn.discordapp.com/attachments/1385580108739379360/1408306378191409242/1394955799368830996.jpg?ex=68a94305&is=68a7f185&hm=cf6511772244abe3321035c34bbadaf616324e240b433ce94c9c823f248ed528&"
}

ADMIN_CHANNEL_ID = 1400060987834368042  # ห้องแอดมิน
tz = pytz.timezone('Asia/Bangkok')
DATA_FILE = "checkin_data.json"
BACKUP_FILE = "checkin_data_backup.json"

MIN_HOURS = 3
MAX_ABSENT_DAYS = 3
MAX_SHORT_HOURS = 2  # เตือน 2 ครั้ง ครั้งที่ 3 ปลดยศ
# ===========================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= จัดการไฟล์ =================
def backup_data():
    if os.path.exists(DATA_FILE):
        shutil.copy(DATA_FILE, BACKUP_FILE)
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"daily_checkins": {}, "work_hours": {}, "checkin_times": {}, "absent_count": {}, "short_hours_count": {}}, f)
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(DATA_FILE, "w") as f:
            json.dump({"daily_checkins": {}, "work_hours": {}, "checkin_times": {}, "absent_count": {}, "short_hours_count": {}}, f)
        return {"daily_checkins": {}, "work_hours": {}, "checkin_times": {}, "absent_count": {}, "short_hours_count": {}}
def save_data(data):
    backup_data()
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
data = load_data()

def thai_time():
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

async def send_warning(member, msg, guild):
    try:
        await member.send(msg)
    except:
        admin_channel = guild.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(f"ไม่สามารถส่ง DM ถึง {member.mention} ได้: {msg}")

async def remove_role_and_reset(member, role_id, guild):
    role = guild.get_role(role_id)
    if role in member.roles:
        await member.remove_roles(role)
    uid = str(member.id)
    data["work_hours"].pop(uid, None)
    data["absent_count"].pop(uid, None)
    data["short_hours_count"].pop(uid, None)
    save_data(data)
    # DM แจ้งผู้ถูกปลดยศ
    try:
        await member.send(f"❌ คุณถูกปลดยศ **{role.name}** เนื่องจากเข้าเวรไม่ครบตามกำหนด หรือขาดเวรเกิน {MAX_ABSENT_DAYS} วัน ข้อมูลถูกรีเซ็ตแล้ว")
    except:
        pass
    # แจ้งแอดมิน
    admin_channel = guild.get_channel(ADMIN_CHANNEL_ID)
    if admin_channel:
        embed = discord.Embed(
            title="ปลดยศ",
            description=f"{member.mention} ถูกปลดยศ {role.name} เนื่องจากเข้าเวรไม่ครบหรือขาดเวร",
            color=discord.Color.red()
        )
        await admin_channel.send(embed=embed)

# ================= Modal =================
class CheckinModal(Modal):
    def __init__(self, action, department):
        super().__init__(title=f"{action}เวร ({department})")
        self.action = action
        self.department = department
        self.name_input = TextInput(label="ชื่อในเกม (Firstname_Lastname)", placeholder="ตัวอย่าง: Firstname_Lastname")
        self.add_item(self.name_input)
    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value
        if not name or "_" not in name:
            await interaction.response.send_message("**รูปแบบชื่อไม่ถูกต้อง** ต้องเป็น Firstname_Lastname", ephemeral=True)
            return
        first, last = name.split("_", 1)
        if not (first[0].isupper() and last[0].isupper() and first.isalpha() and last.isalpha()):
            await interaction.response.send_message("**ชื่อไม่ถูกต้อง** ต้องเป็นภาษาอังกฤษและตัวแรกพิมพ์ใหญ่", ephemeral=True)
            return
        user_id = str(interaction.user.id)
        today = datetime.now(tz).strftime("%Y-%m-%d")
        if today not in data["daily_checkins"]:
            data["daily_checkins"][today] = {dep: [] for dep in DEPARTMENTS.keys()}

        if self.action == "ออก" and user_id not in data["checkin_times"]:
            await interaction.response.send_message("❌ คุณยังไม่ได้เข้าเวร ไม่สามารถออกเวรได้!", ephemeral=True)
            return

        await interaction.response.send_message(f"กรุณาส่ง **รูปยืนยันการ{self.action}เวร** ในห้องนี้ ภายใน 1 นาที:", ephemeral=True)
        def check(msg):
            return msg.author.id == interaction.user.id and msg.attachments and msg.channel == interaction.channel
        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
        except:
            await interaction.followup.send(f"หมดเวลา! คุณไม่ได้ส่งรูปยืนยันการ{self.action}เวร", ephemeral=True)
            return

        file = await msg.attachments[0].to_file()
        await msg.delete()

        if self.action == "เข้า":
            if user_id not in data["daily_checkins"][today][self.department]:
                data["daily_checkins"][today][self.department].append(user_id)
            data["checkin_times"][user_id] = datetime.now(tz).isoformat()
        else:
            start_time_str = data["checkin_times"].get(user_id)
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str)
                hours = (datetime.now(tz) - start_time).seconds / 3600
                data["work_hours"][user_id] = data["work_hours"].get(user_id, 0) + hours
                del data["checkin_times"][user_id]
            if user_id in data["daily_checkins"][today][self.department]:
                data["daily_checkins"][today][self.department].remove(user_id)
        save_data(data)

        channel_id = DEPARTMENT_CHANNELS.get(self.department)
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title=f"{self.action}เวรเรียบร้อย ({self.department})",
                    description=f"โดย: {interaction.user.mention}\nชื่อในเกม: `{name}`\nเวลา: {thai_time()}",
                    color=discord.Color.green() if self.action == "เข้า" else discord.Color.red()
                )
                embed.set_image(url="attachment://uploaded.png")
                await channel.send(embed=embed, file=discord.File(fp=file.fp, filename="uploaded.png"))
        await interaction.followup.send(f"บันทึกการ{self.action}เวรเรียบร้อยแล้ว!", ephemeral=True)

# ================= ปุ่ม =================
class CheckinView(View):
    def __init__(self, department):
        super().__init__(timeout=None)
        self.add_item(Button(label="📥 เข้าเวร", style=discord.ButtonStyle.green, custom_id=f"checkin_{department}_in"))
        self.add_item(Button(label="📤 ออกเวร", style=discord.ButtonStyle.red, custom_id=f"checkin_{department}_out"))

@bot.event
async def on_interaction(interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data["custom_id"]
        if cid.startswith("checkin_"):
            _, department, action = cid.split("_")
            role_id = DEPARTMENTS.get(department)
            if role_id not in [r.id for r in interaction.user.roles]:
                await interaction.response.send_message("คุณไม่มีสิทธิ์กดปุ่มนี้!", ephemeral=True)
                return
            modal = CheckinModal("เข้า" if action == "in" else "ออก", department)
            await interaction.response.send_modal(modal)

# ================= รายงานเวร =================
@bot.command(name="รายงานเวร")
async def report_cmd(ctx):
    today = datetime.now(tz).strftime("%Y-%m-%d")
    for dep, role_id in DEPARTMENTS.items():
        role = ctx.guild.get_role(role_id)
        members = role.members if role else []
        checked_in = data["daily_checkins"].get(today, {}).get(dep, [])
        desc = ""
        for m in members:
            status = "เข้าเวร" if str(m.id) in checked_in else "ไม่ได้เข้าเวร"
            short_count = data["short_hours_count"].get(str(m.id), 0)
            absent_count = data["absent_count"].get(str(m.id), 0)
            extra = []
            if short_count > 0:
                extra.append(f"เตือนเข้าเวรไม่ครบ {short_count} ครั้ง")
            if absent_count > 0:
                extra.append(f"ขาดเวร {absent_count} วัน")
            status_text = f"{status}" + (f" / {' , '.join(extra)}" if extra else "")
            desc += f"{m.display_name} ({status_text})\n"
        if not desc:
            desc = "ไม่มีสมาชิกในหน่วยงาน"
        embed = discord.Embed(
            title=f"รายงานเวร {dep} ({today})",
            description=desc,
            color=discord.Color.blue()
        )
        embed.set_image(url=DEPARTMENT_IMAGES.get(dep, ""))
        await ctx.send(embed=embed)

# ================= รายงานอัตโนมัติ =================
async def send_daily_report(guild):
    today = datetime.now(tz).strftime("%Y-%m-%d")
    admin_channel = guild.get_channel(ADMIN_CHANNEL_ID)
    if not admin_channel:
        return
    for dep, role_id in DEPARTMENTS.items():
        role = guild.get_role(role_id)
        members = role.members if role else []
        checked_in = data["daily_checkins"].get(today, {}).get(dep, [])
        desc = ""
        for m in members:
            status = "เข้าเวร" if str(m.id) in checked_in else "ไม่ได้เข้าเวร"
            short_count = data["short_hours_count"].get(str(m.id), 0)
            absent_count = data["absent_count"].get(str(m.id), 0)
            extra = []
            if short_count > 0:
                extra.append(f"เตือนเข้าเวรไม่ครบ {short_count} ครั้ง")
            if absent_count > 0:
                extra.append(f"ขาดเวร {absent_count} วัน")
            status_text = f"{status}" + (f" / {' , '.join(extra)}" if extra else "")
            desc += f"{m.display_name} ({status_text})\n"
        if not desc:
            desc = "ไม่มีสมาชิกในหน่วยงาน"
        embed = discord.Embed(
            title=f"รายงานเวรประจำวัน ({dep}) - {today}",
            description=desc,
            color=discord.Color.blue()
        )
        embed.set_image(url=DEPARTMENT_IMAGES.get(dep, ""))
        await admin_channel.send(embed=embed)

# ================= ตรวจสอบทุกเที่ยงคืน =================
@tasks.loop(time=time(hour=0, minute=0, tzinfo=tz))
async def daily_check():
    guild = bot.guilds[0]
    for dep, role_id in DEPARTMENTS.items():
        role = guild.get_role(role_id)
        if not role:
            continue
        for member in role.members:
            uid = str(member.id)
            hours = data["work_hours"].get(uid, 0)
            if hours < MIN_HOURS:
                data["short_hours_count"][uid] = data["short_hours_count"].get(uid, 0) + 1
                if data["short_hours_count"][uid] >= (MAX_SHORT_HOURS + 1):
                    await remove_role_and_reset(member, role_id, guild)
                    continue
                else:
                    await send_warning(member, f"⚠️ คุณเข้าเวรไม่ครบ {MIN_HOURS} ชั่วโมง! เตือนครั้งที่ {data['short_hours_count'][uid]}/3", guild)
            else:
                data["short_hours_count"][uid] = 0

            data["absent_count"][uid] = data["absent_count"].get(uid, 0)
            if hours == 0:
                data["absent_count"][uid] += 1
            else:
                data["absent_count"][uid] = 0
            if data["absent_count"][uid] >= MAX_ABSENT_DAYS:
                await remove_role_and_reset(member, role_id, guild)
                continue

            data["work_hours"][uid] = 0
    save_data(data)
    await send_daily_report(guild)

# ================= ปุ่มโพสต์ =================
@bot.command(name="ตำรวจ")
async def post_police(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="ระบบบันทึกเวร - ตำรวจ",
            description="**กดปุ่มเพื่อเข้า/ออกเวร และแนบรูปยืนยันได้เลย!**",
            color=discord.Color.blue()
        )
        embed.set_image(url=DEPARTMENT_IMAGES["ตำรวจ"])
        await ctx.send(embed=embed, view=CheckinView("ตำรวจ"))

@bot.command(name="หมอ")
async def post_doctor(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="ระบบบันทึกเวร - หมอ",
            description="**กดปุ่มเพื่อเข้า/ออกเวร และแนบรูปยืนยันได้เลย!**",
            color=discord.Color.blue()
        )
        embed.set_image(url=DEPARTMENT_IMAGES["หมอ"])
        await ctx.send(embed=embed, view=CheckinView("หมอ"))

@bot.command(name="สภา")
async def post_council(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="ระบบบันทึกเวร - สภา",
            description="**กดปุ่มเพื่อเข้า/ออกเวร และแนบรูปยืนยันได้เลย!**",
            color=discord.Color.blue()
        )
        embed.set_image(url=DEPARTMENT_IMAGES["สภา"])
        await ctx.send(embed=embed, view=CheckinView("สภา"))

@bot.event
async def on_ready():
    print(f"Bot {bot.user} พร้อมใช้งานแล้ว!")
    daily_check.start()

bot.run(TOKEN)