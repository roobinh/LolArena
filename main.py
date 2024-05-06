import discord
import random
from dotenv import dotenv_values
from discord.ext import commands
from discord.ui import Button, View
from discord.ext.commands import MissingPermissions

# List of League of Legends champions
lol_champions = [
    "Aatrox", "Ahri", "Akali", "Alistar", "Amumu", "Anivia", "Annie", "Aphelios", "Ashe", "Aurelion Sol",
    "Azir", "Bard", "Blitzcrank", "Brand", "Braum", "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath",
    "Corki", "Darius", "Diana", "Dr. Mundo", "Draven", "Ekko", "Elise", "Evelynn", "Ezreal", "Fiddlesticks",
    "Fiora", "Fizz", "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Graves", "Hecarim", "Heimerdinger",
    "Illaoi", "Irelia", "Ivern", "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx", "Kai'Sa",
    "Kalista", "Karma", "Karthus", "Kassadin", "Katarina", "Kayle", "Kayn", "Kennen", "Kha'Zix", "Kindred",
    "Kled", "Kog'Maw", "LeBlanc", "Lee Sin", "Leona", "Lillia", "Lissandra", "Lucian", "Lulu", "Lux",
    "Malphite", "Malzahar", "Maokai", "Master Yi", "Miss Fortune", "Mordekaiser", "Morgana", "Nami", "Nasus", "Nautilus",
    "Neeko", "Nidalee", "Nocturne", "Nunu & Willump", "Olaf", "Orianna", "Ornn", "Pantheon", "Poppy", "Pyke",
    "Qiyana", "Quinn", "Rakan", "Rammus", "Rek'Sai", "Rell", "Renekton", "Rengar", "Riven", "Rumble",
    "Ryze", "Samira", "Sejuani", "Senna", "Seraphine", "Sett", "Shaco", "Shen", "Shyvana", "Singed",
    "Sion", "Sivir", "Skarner", "Sona", "Soraka", "Swain", "Sylas", "Syndra", "Tahm Kench", "Taliyah",
    "Talon", "Taric", "Teemo", "Thresh", "Tristana", "Trundle", "Tryndamere", "Twisted Fate", "Twitch", "Udyr",
    "Urgot", "Varus", "Vayne", "Veigar", "Vel'Koz", "Vi", "Viego", "Viktor", "Vladimir", "Volibear",
    "Warwick", "Wukong", "Xayah", "Xerath", "Xin Zhao", "Yasuo", "Yone", "Yorick", "Yuumi", "Zac",
    "Zed", "Ziggs", "Zilean", "Zoe", "Zyra","Gwen", "Akshan", "Vex", "Zeri", "Renata Glasc", "Bel'veth", 
    "Nilah", "K'sante", "Milio", "Naafiri", "Briar", "Hwei"
]

env = dotenv_values('.env')
bot_token = env.get('BOT_TOKEN')

intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Dictionary to store assigned numbers to players
player_numbers = {}

class ChampionButtonView(View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        button = Button(label="Generate Again", style=discord.ButtonStyle.primary)
        button.callback = self.generate_again
        self.add_item(button)

    async def generate_again(self, interaction: discord.Interaction):
        await generate_champions(self.ctx, interaction)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("I don't have permission to do that. Please check my role permissions.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not recognized. Please check the available commands using `/arena help`.")
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.send("An error occurred while executing the command. Make sure I have the necessary permissions.")
    else:
        await ctx.send(f"An unexpected error occurred: {error}")

@bot.hybrid_command(
    name="arena",
    description="Generate random teams of 2 players or based on specified numbers"
)
async def arena(ctx, arg: str = ""):
    if not arg:
        await generate_teams(ctx)  # Call generate_teams without any argument
    elif arg.lower() == "help":
        await list_commands(ctx)  # Call list_commands when help is requested
    elif arg.lower() == "list":
        await list_players(ctx)  # Call list_players when list is requested
    elif arg.lower() in ["champions", "c"]:
        await generate_champions(ctx)  # Call generate_champions when champions or c is requested
    else:
        await ctx.send("Unknown argument provided. Use `/arena help` for the correct syntax.")


async def list_commands(ctx):
    embed = discord.Embed(
        title="Arena Commands",
        description="Here are the available commands for the arena:",
        color=discord.Color.blue()
    )
    embed.add_field(name="/arena", value="Generate teams based on players in the current voice channel", inline=False)
    embed.add_field(name="/arena <numbers>", value="Generate teams based on players with corresponding numbers", inline=False)
    embed.add_field(name="/arena list", value="List all players in the current voice channel", inline=False)
    embed.add_field(name="/arena champions", value="Generate random arena team", inline=False)
    embed.add_field(name="/arena help", value="Show this help message", inline=False)
    await ctx.send(embed=embed)


async def list_players(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        members = voice_channel.members

        embed = discord.Embed(
            title=f"List of players in {voice_channel.name}",
            color=discord.Color.blue()
        )
        for member in members:
            if member.id not in player_numbers:  # Check if the player is new
                player_numbers[member.id] = len(player_numbers) + 1  # Assign a new number
            embed.add_field(name=f"{player_numbers[member.id]}", value=member.name, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("You need to be in a voice channel to use this command!")


async def generate_teams(ctx, arg=None):
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        members = voice_channel.members
        member_names = [member.name for member in members]

        if arg and arg.isdigit():
            selected_players = [member for member in members if player_numbers.get(member.id) in map(int, arg)]
        else:
            selected_players = members

        random.shuffle(selected_players)
        teams = []
        while len(selected_players) > 1:
            team = [selected_players.pop().name, selected_players.pop().name]
            teams.append(team)
        if selected_players:
            solo = selected_players.pop().name
            teams.append([solo])

        embed = discord.Embed(
            title="Teams for Arena",
            description="\n".join([f"Team {i+1}: {', '.join(team)}" for i, team in enumerate(teams)]),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("You need to be in a voice channel to use this command!")


async def generate_champions(ctx, interaction=None):
    # Generate two random champions
    random_champions = random.sample(lol_champions, 2)

    # Create hyperlinks to blitz.gg for each champion
    # Clean champion names by removing spaces and apostrophes
    def clean_name(name):
        return name.lower().replace("'", "").replace(" ", "")

    champion1_clean = clean_name(random_champions[0])
    champion2_clean = clean_name(random_champions[1])

    # Create hyperlinks to blitz.gg for each champion
    champion1_url = f"https://blitz.gg/lol/champions/{champion1_clean}/arena"
    champion2_url = f"https://blitz.gg/lol/champions/{champion2_clean}/arena"

    champion1_hyperlink = f"[{random_champions[0]}]({champion1_url})"
    champion2_hyperlink = f"[{random_champions[1]}]({champion2_url})"

    # Create an embed to display the champions with clickable links
    embed = discord.Embed(
        title="Random Champions",
        description=f"{ctx.author.name}: {champion1_hyperlink}\nTeammate: {champion2_hyperlink}",
        color=discord.Color.orange()
    )
    if interaction:
        await interaction.response.edit_message(embed=embed, view=ChampionButtonView(ctx))
    else:
        await ctx.send(embed=embed, view=ChampionButtonView(ctx))

bot.run(bot_token)