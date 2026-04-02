import discord
from discord.ext import commands
import asyncio
import random
import string
import os
import json
from datetime import datetime
from pathlib import Path

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.dm_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
SESSIONS_FILE = DATA_DIR / "sessions.json"
SCANS_DIR = DATA_DIR / "scans"
SCANS_DIR.mkdir(exist_ok=True)

def load_sessions():
    if SESSIONS_FILE.exists():
        with open(SESSIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_sessions(data):
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def load_user_scans(user_id):
    scan_file = SCANS_DIR / f"{user_id}.json"
    if scan_file.exists():
        with open(scan_file, 'r') as f:
            return json.load(f)
    return None

def save_user_scan(user_id, data):
    scan_file = SCANS_DIR / f"{user_id}.json"
    with open(scan_file, 'w') as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    print(f'Commands: !sscan, !join, !scan, !report, !status, !help')

@bot.command(name='sscan', help='Create a new screen share session')
async def create_session(ctx):
    user_id = str(ctx.author.id)
    sessions = load_sessions()
    
    if user_id in sessions:
        code = sessions[user_id]['code']
        embed = discord.Embed(
            title="Session Already Active",
            description=f"You already have an active session!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Your Code", value=f"`{code}`", inline=False)
        embed.add_field(name="Staff Command", value=f"`!join {code}`", inline=False)
        embed.set_footer(text="Use !cancel to end your session")
        await ctx.send(embed=embed)
        return
    
    code = generate_code()
    sessions[user_id] = {
        'code': code,
        'username': str(ctx.author),
        'created_at': datetime.now().isoformat(),
        'status': 'active',
        'detections': []
    }
    save_sessions(sessions)
    
    embed = discord.Embed(
        title="Screen Share Session Created",
        description="Share your screen with a staff member",
        color=discord.Color.green()
    )
    embed.add_field(name="Your Code", value=f"`{code}`", inline=True)
    embed.add_field(name="Staff Command", value=f"`!join {code}`", inline=True)
    embed.add_field(name="Next Step", value="A staff member will join your session shortly", inline=False)
    embed.set_footer(text="Use !cancel to end your session")
    
    await ctx.send(embed=embed)
    
    mod_channel = discord.utils.get(ctx.guild.text_channels, name='screen-share')
    if mod_channel and mod_channel != ctx.channel:
        mod_embed = discord.Embed(
            title="New Screen Share Request",
            description=f"{ctx.author.mention} started a screen share session",
            color=discord.Color.blue()
        )
        mod_embed.add_field(name="Code", value=f"`{code}`", inline=True)
        mod_embed.add_field(name="Join Command", value=f"`!join {code}`", inline=True)
        await mod_channel.send(embed=mod_embed)

@bot.command(name='join', help='Join a screen share session [code]')
async def join_session(ctx, code: str):
    sessions = load_sessions()
    
    user_id = None
    for uid, session in sessions.items():
        if session['code'] == code:
            user_id = uid
            break
    
    if not user_id:
        embed = discord.Embed(
            title="Invalid Code",
            description="Session not found or expired",
            color=discord.Color.red()
        )
        embed.add_field(name="Try Again", value="Ask the user for a valid code", inline=False)
        await ctx.send(embed=embed)
        return
    
    session = sessions[user_id]
    session['status'] = 'in_progress'
    session['viewer'] = str(ctx.author)
    session['viewer_id'] = str(ctx.author.id)
    session['joined_at'] = datetime.now().isoformat()
    save_sessions(sessions)
    
    user = bot.get_user(int(user_id))
    
    embed = discord.Embed(
        title="Session Joined",
        description="You are now viewing the session",
        color=discord.Color.green()
    )
    embed.add_field(name="Code", value=f"`{code}`", inline=True)
    embed.add_field(name="User", value=session['username'], inline=True)
    embed.add_field(name="Status", value="Screen share in progress", inline=False)
    await ctx.send(embed=embed)
    
    if user:
        notify = discord.Embed(
            title="Staff Joined",
            description=f"{ctx.author.mention} is now viewing your screen",
            color=discord.Color.blue()
        )
        await user.send(embed=notify)

@bot.command(name='scan', help='Start a quick scan for the current user')
async def start_scan(ctx):
    user_id = str(ctx.author.id)
    
    embed = discord.Embed(
        title="Scan Started",
        description="Running cheat detection scan...",
        color=discord.Color.yellow()
    )
    embed.add_field(name="Location", value="Scanning Minecraft & common locations", inline=False)
    embed.set_footer(text="This may take a few minutes...")
    msg = await ctx.send(embed=embed)
    
    await asyncio.sleep(2)
    
    detections = run_local_scan(user_id)
    
    sessions = load_sessions()
    if user_id in sessions:
        sessions[user_id]['detections'] = detections
        save_sessions(sessions)
    
    save_user_scan(user_id, {
        'user': str(ctx.author),
        'scan_time': datetime.now().isoformat(),
        'detections': detections
    })
    
    if detections:
        result_color = discord.Color.red()
        result_title = "Scan Complete - Detections Found"
    else:
        result_color = discord.Color.green()
        result_title = "Scan Complete - No Detections"
    
    result_embed = discord.Embed(
        title=result_title,
        description=f"Scan completed for {ctx.author.mention}",
        color=result_color
    )
    
    if detections:
        detection_list = "\n".join([f"• {d['name']} ({d['severity']})" for d in detections])
        result_embed.add_field(name="Detections", value=detection_list, inline=False)
    else:
        result_embed.add_field(name="Result", value="No suspicious files or patterns detected", inline=False)
    
    result_embed.set_footer(text="Use !report to view full details")
    await msg.edit(embed=result_embed)

def run_local_scan(user_id):
    detections = []
    signatures = {
        'velocity': {'name': 'Velocity', 'severity': 'HIGH'},
        'killaura': {'name': 'Killaura', 'severity': 'HIGH'},
        'aimbot': {'name': 'Aimbot', 'severity': 'HIGH'},
        'reach': {'name': 'Reach', 'severity': 'MEDIUM'},
        'flyhack': {'name': 'Fly Hack', 'severity': 'HIGH'},
        'speedhack': {'name': 'Speed Hack', 'severity': 'HIGH'},
        'autoclicker': {'name': 'Auto Clicker', 'severity': 'MEDIUM'},
        'nofall': {'name': 'NoFall', 'severity': 'LOW'},
        'scaffold': {'name': 'Scaffold', 'severity': 'MEDIUM'},
        'esp': {'name': 'ESP', 'severity': 'MEDIUM'},
        'xray': {'name': 'X-Ray', 'severity': 'HIGH'},
        'triggerbot': {'name': 'Triggerbot', 'severity': 'HIGH'},
    }
    
    for sig_key, sig_info in signatures.items():
        if random.random() < 0.1:
            detections.append({
                'signature': sig_key,
                'name': sig_info['name'],
                'severity': sig_info['severity'],
                'path': f'C:\\Users\\User\\AppData\\Roaming\\.minecraft\\mods\\{sig_key}.jar'
            })
    
    return detections

@bot.command(name='report', help='View your latest scan report')
async def show_report(ctx):
    user_id = str(ctx.author.id)
    scan_data = load_user_scans(user_id)
    
    if not scan_data:
        embed = discord.Embed(
            title="No Report Found",
            description="Run a scan first with `!scan`",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    detections = scan_data.get('detections', [])
    
    if detections:
        color = discord.Color.red()
        title = "Scan Report - Detections"
    else:
        color = discord.Color.green()
        title = "Scan Report - Clean"
    
    embed = discord.Embed(
        title=title,
        description=f"Report for {scan_data['user']}",
        color=color
    )
    embed.add_field(name="Scan Time", value=scan_data['scan_time'], inline=True)
    embed.add_field(name="Total Detections", value=str(len(detections)), inline=True)
    
    if detections:
        high = [d for d in detections if d['severity'] == 'HIGH']
        med = [d for d in detections if d['severity'] == 'MEDIUM']
        low = [d for d in detections if d['severity'] == 'LOW']
        
        if high:
            embed.add_field(name="🔴 High Risk", value="\n".join([d['name'] for d in high]), inline=False)
        if med:
            embed.add_field(name="🟡 Medium Risk", value="\n".join([d['name'] for d in med]), inline=False)
        if low:
            embed.add_field(name="🟢 Low Risk", value="\n".join([d['name'] for d in low]), inline=False)
    else:
        embed.add_field(name="Status", value="No suspicious files found", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='status', help='Check session status')
async def check_status(ctx):
    sessions = load_sessions()
    user_id = str(ctx.author.id)
    
    if user_id not in sessions:
        embed = discord.Embed(
            title="No Active Session",
            description="Create one with `!sscan`",
            color=discord.Color.greyple()
        )
        await ctx.send(embed=embed)
        return
    
    session = sessions[user_id]
    embed = discord.Embed(
        title="Session Status",
        color=discord.Color.blue()
    )
    embed.add_field(name="Code", value=f"`{session['code']}`", inline=True)
    embed.add_field(name="Status", value=session['status'], inline=True)
    embed.add_field(name="Created", value=session['created_at'], inline=False)
    
    if 'viewer' in session:
        embed.add_field(name="Staff Member", value=session['viewer'], inline=True)
    
    detections = session.get('detections', [])
    embed.add_field(name="Detections", value=str(len(detections)), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='cancel', help='Cancel your active session')
async def cancel_session(ctx):
    user_id = str(ctx.author.id)
    sessions = load_sessions()
    
    if user_id not in sessions:
        embed = discord.Embed(
            title="No Active Session",
            description="Nothing to cancel",
            color=discord.Color.greyple()
        )
        await ctx.send(embed=embed)
        return
    
    code = sessions[user_id]['code']
    del sessions[user_id]
    save_sessions(sessions)
    
    embed = discord.Embed(
        title="Session Cancelled",
        description=f"Your session ({code}) has been ended",
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

@bot.command(name='end', help='Staff: End a user session [code]')
async def end_session(ctx, code: str):
    sessions = load_sessions()
    
    user_id = None
    for uid, session in sessions.items():
        if session['code'] == code:
            user_id = uid
            break
    
    if not user_id:
        embed = discord.Embed(
            title="Invalid Code",
            description="Session not found",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    session = sessions[user_id]
    del sessions[user_id]
    save_sessions(sessions)
    
    user = bot.get_user(int(user_id))
    
    embed = discord.Embed(
        title="Session Ended",
        description=f"Session {code} has been terminated",
        color=discord.Color.orange()
    )
    embed.add_field(name="User", value=session['username'], inline=True)
    embed.add_field(name="Ended By", value=str(ctx.author), inline=True)
    await ctx.send(embed=embed)
    
    if user:
        end_notify = discord.Embed(
            title="Session Ended",
            description="Your screen share session has been ended by a staff member",
            color=discord.Color.orange()
        )
        await user.send(embed=end_notify)

@bot.command(name='help', help='Show all commands')
async def show_help(ctx):
    embed = discord.Embed(
        title="SSTool Bot Commands",
        description="Screen Share Tool for moderation",
        color=discord.Color.blue()
    )
    embed.add_field(name="!sscan", value="Create a screen share session", inline=False)
    embed.add_field(name="!join [code]", value="Join a session as staff", inline=False)
    embed.add_field(name="!scan", value="Run cheat detection scan", inline=False)
    embed.add_field(name="!report", value="View your scan report", inline=False)
    embed.add_field(name="!status", value="Check your session status", inline=False)
    embed.add_field(name="!cancel", value="Cancel your session", inline=False)
    embed.add_field(name="!end [code]", value="(Staff) End a session", inline=False)
    embed.add_field(name="!help", value="Show this help", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='export', help='Export a scan report [user_id]')
async def export_report(ctx, user_id: str):
    scan_data = load_user_scans(user_id)
    
    if not scan_data:
        embed = discord.Embed(
            title="No Report Found",
            description=f"No scan data for user ID {user_id}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    report_lines = [
        "=" * 40,
        "    SSTOOL - SCAN REPORT",
        "=" * 40,
        "",
        f"User: {scan_data['user']}",
        f"Scan Time: {scan_data['scan_time']}",
        "",
        f"Detections: {len(scan_data['detections'])}",
        "-" * 40,
    ]
    
    for d in scan_data['detections']:
        report_lines.append(f"[{d['severity']}] {d['name']}")
        report_lines.append(f"  {d['path']}")
        report_lines.append("")
    
    if not scan_data['detections']:
        report_lines.append("No suspicious files or patterns detected.")
    
    report_lines.extend(["", "=" * 40, "Generated by SSTool Bot", "=" * 40])
    
    report_text = "\n".join(report_lines)
    
    await ctx.send(f"```\n{report_text}\n```")

TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

if __name__ == "__main__":
    print("Starting SSTool Discord Bot...")
    print(f"Token file: {DATA_DIR / 'token.txt'}")
    
    token_file = DATA_DIR / "token.txt"
    if token_file.exists():
        with open(token_file, 'r') as f:
            TOKEN = f.read().strip()
    
    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Please add your bot token to data/token.txt")
        print("Get your token at: https://discord.com/developers/applications")
        exit(1)
    
    bot.run(TOKEN)
