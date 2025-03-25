import discord
from discord.ext import commands, tasks
import yt_dlp as youtube_dl
import asyncio
from flask import Flask, render_template_string
import threading


# ------------------ Discord Music Bot Setup ------------------

# Suppress youtube_dl debug output
youtube_dl.utils.bug_reports_message = lambda: ''

# youtube_dl options to extract audio from a URL
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,  # Only process individual tracks
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',  # Allow search terms if needed
}

# FFmpeg options for streaming audio
ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    """Creates an audio source from a provided URL."""
    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
    
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        # If multiple entries exist (like a playlist), take the first one.
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Create the bot with a dummy prefix (commands will use our custom keys).
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="k", intents=intents)

queues = {}
@bot.command()
async def hb(ctx):
    help_message = """
    **Music Bot Commands:**
    🎵 `kj` - Bot joins your voice channel
    🎶 `kpl [URL]` - Play a song from YouTube
    ⏭  `kpn` - Manually play the next song in the queue
    ⏸ `kpa` - Pause the current song
    ▶ `kre` - Resume the song
    ⏹ `kst` - Stop the music
    ⏭ `ksk` - Skip the current song
    🚪 `kle` - Bot leaves the voice channel
    ℹ `khb` - Display this help message
    Invite the bot here: https://discord.com/oauth2/authorize?client_id=1343179814206570599
    """
    await ctx.send(help_message)

# Global asynchronous queue to hold songs.
music_queue = asyncio.Queue()
# Global variable to store the text channel for auto-play notifications.
last_text_channel = None

async def play_next(voice_client):
    """Automatically plays the next song from the queue if available."""
    if not music_queue.empty():
        next_source = await music_queue.get()
        voice_client.play(next_source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(voice_client), bot.loop))
        if last_text_channel:
            await last_text_channel.send(f'🎶Now playing: **{next_source.title}**')

# ------------------ Bot Commands ------------------

@bot.command(name='j', help='Join your current voice channel.')
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        else:
            await ctx.voice_client.move_to(channel)
        await ctx.send(f"🎵Joined[សួស្ដី] **{channel.name}**")
    else:
        await ctx.send("You are not in a voice channel.")

@bot.command(name='pl', help='Play a song from a URL. Usage: !pl <URL>')
async def play(ctx, *, link):
    global last_text_channel
    last_text_channel = ctx.channel  # Update channel for notifications

    if ctx.voice_client is None:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You are not in a voice channel.")
            return

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(link, loop=bot.loop, stream=True)
        except Exception as e:
            await ctx.send("An error occurred while processing that link.")
            print(e)
            return

    # If a song is already playing, add to the queue; otherwise, play immediately.
    if ctx.voice_client.is_playing():
        await music_queue.put(player)
        await ctx.send(f'🎶Added to queue[បទចម្រៀងបន្ទាប់]: **{player.title}**')
    else:
        ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx.voice_client), bot.loop))
        await ctx.send(f'🎶Now playing[កំពុងចាក់បទចម្រៀង]: **{player.title}**')

@bot.command(name='st', help='Stop the current song and clear the queue.')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        # Clear the queue
        while not music_queue.empty():
            await music_queue.get()
        await ctx.send("⏹Playback stopped and queue cleared.")
    else:
        await ctx.send("I am not in a voice channel.")

@bot.command(name='le', help='Leave the voice channel and clear the queue.')
async def leave(ctx):
    if ctx.voice_client:
        while not music_queue.empty():
            await music_queue.get()
        await ctx.voice_client.disconnect()
        await ctx.send("🚪[លាហើយសូមអគុណ]Left the voice channel and cleared the queue.")
    else:
        await ctx.send("I am not in a voice channel.")

@bot.command(name='sk', help='Skip the current song.')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()  # Triggers auto-play for the next song.
        await ctx.send("⏭Skipped the current song.")
    else:
        await ctx.send("No song is currently playing.")

@bot.command(name='pn', help='Manually play the next song in the queue.')
async def playnext(ctx):
    if ctx.voice_client:
        # If something is playing, stop it to trigger auto-play.
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop()
            await ctx.send("Moving to the next song...")
        else:
            await play_next(ctx.voice_client)
            await ctx.send("🎶Now playing the next song.")
    else:
        await ctx.send("I am not in a voice channel.")

@bot.command(name='pa', help='Pause the current song.')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("▶Playback paused.")
    else:
        await ctx.send("No song is currently playing.")

@bot.command(name='re', help='Resume the paused song.')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Playback resumed.")
    else:
        await ctx.send("No paused audio to resume.")       

# ------------------ Flask Website ("k9 music") ------------------

app = Flask("k9 music")


@app.route('/')
def home():
    return render_template_string("HTML_TEMPLATE.html")

def run_web():
    # Run the web server on all interfaces at port 8080.
    app.run(host='0.0.0.0', port=8080)

# ------------------ Main Execution ------------------
@bot.command()
async def _khb(ctx):
    """Send bot invite link."""
    await ctx.send("Invite the bot here: https://discord.com/oauth2/authorize?client_id=1343179814206570599&permissions=8&integration_type=0&scope=bot")

if __name__ == '__main__':
    # Start the Flask website in a separate daemon thread.
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Run the Discord bot.
    bot.run("MTM0MzE3OTgxNDIwNjU3MDU5OQ.GaNHlR.6PHB_sUAVprrOu-Kvodpyur-RfZ4WoX3SjHUoQ")
