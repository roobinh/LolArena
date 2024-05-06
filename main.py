import discord, random
from dotenv import dotenv_values
from discord.ext import commands

env = dotenv_values('.env')
bot_token = env.get('BOT_TOKEN')

intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Dictionary to store assigned numbers to players
player_numbers = {}


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


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
    else:
        await generate_teams(ctx, arg)


async def list_commands(ctx):
    # Create an embed to display the command list
    embed = discord.Embed(
        title="Arena Commands",
        description="Here are the available commands for the arena:",
        color=discord.Color.blue()
    )
    embed.add_field(name="/arena", value="Generate teams based on players in the current voice channel", inline=False)
    embed.add_field(name="/arena list", value="List all players in the current voice channel", inline=False)
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

        # Creating an embed to display the teams
        embed = discord.Embed(
            title="Teams for Arena",
            description="\n".join([f"Team {i+1}: {', '.join(team)}" for i, team in enumerate(teams)]),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("You need to be in a voice channel to use this command!")

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
bot.run(bot_token)
