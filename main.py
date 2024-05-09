import os, json, random, discord, subprocess
from dotenv import dotenv_values
from discord.ext import commands
from discord.ui import Button, View
from discord.ext.commands import MissingPermissions
from datetime import datetime

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
    "Nilah", "K'sante", "Milio", "Naafiri", "Briar", "Hwei", "Smolder"
]

env = dotenv_values('.env')
bot_token = env.get('BOT_TOKEN')
bot_token = env.get('BOT_TOKEN_DEV')
print(bot_token)

intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Dictionary to store assigned numbers to players
player_numbers = {}

class ArenaHelpView(View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx

        # Create buttons for different commands
        teams_button = Button(
            label="Generate Teams",
            style=discord.ButtonStyle.success  # Green
        )
        teams_button.callback = self.generate_teams
        self.add_item(teams_button)

        champions_button = Button(
            label="Generate Champions",
            style=discord.ButtonStyle.primary  # Yellow not available, so using primary (blue)
        )
        champions_button.callback = self.generate_champions
        self.add_item(champions_button)

        list_button = Button(
            label="List All Players",
            style=discord.ButtonStyle.secondary  # Blue
        )
        list_button.callback = self.list_players
        self.add_item(list_button)

    async def generate_teams(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        await generate_teams(self.ctx)

    async def generate_champions(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        await generate_champions(self.ctx)

    async def list_players(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        await list_players(self.ctx)


class ChampionButtonView(View):
    def __init__(self, ctx, champions, reroll_count=0, max_rerolls=2):
        super().__init__()
        self.ctx = ctx
        self.champions = champions  # Store the selected champions for easy access later
        self.reroll_count = reroll_count
        self.max_rerolls = max_rerolls

        # Reroll button
        remaining_rerolls = max_rerolls - reroll_count
        reroll_button = Button(
            label=f"Reroll ({remaining_rerolls})",
            style=discord.ButtonStyle.primary,
            disabled=reroll_count >= max_rerolls
        )
        reroll_button.callback = self.generate_again
        self.add_item(reroll_button)

        # Next Game button
        next_game_button = Button(
            label="Next Game",
            style=discord.ButtonStyle.success
        )
        next_game_button.callback = self.next_game
        self.add_item(next_game_button)

        # "Game Win 👑" button
        game_win_button = Button(
            label="Game Win 👑",
            style=discord.ButtonStyle.secondary
        )
        game_win_button.callback = self.game_win
        self.add_item(game_win_button)

    async def generate_again(self, interaction: discord.Interaction):
        self.reroll_count += 1
        await generate_champions(self.ctx, interaction, self.reroll_count, self.max_rerolls)

    async def next_game(self, interaction: discord.Interaction):
        # Identify the user who clicked the button
        clicked_user = interaction.user.name

        # Acknowledge the interaction
        await interaction.response.defer()

        # Update the title to include the user's name
        await generate_champions(self.ctx, None, 0, 2, clicked_user)

    async def game_win(self, interaction: discord.Interaction):
        clicked_user = interaction.user
        author = self.ctx.author

        # Determine which champion to attribute based on the clicked user
        if clicked_user == author:
            winner_champion = self.champions[0]
        else:
            winner_champion = self.champions[1]

        # Get the current timestamp in the "DD-MM-YYYY HH:MM" format
        win_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")

        # Read existing wins data from the JSON file or initialize a new structure
        json_file = "champion_wins.json"
        if os.path.exists(json_file):
            try:
                with open(json_file, "r") as file:
                    champion_wins = json.load(file)
            except json.JSONDecodeError:
                # Handle empty or corrupted JSON file
                champion_wins = {}
        else:
            champion_wins = {}

        # Update or create the entry for the clicked user, ensuring the 'wins' key always exists
        user_key = str(clicked_user.id)
        if user_key not in champion_wins:
            champion_wins[user_key] = {"name": clicked_user.name, "wins": []}
        elif "wins" not in champion_wins[user_key]:
            champion_wins[user_key]["wins"] = []

        # Check if the champion already exists in the user's wins
        existing_champions = [win["champion"] for win in champion_wins[user_key]["wins"]]
        if winner_champion not in existing_champions:
            # Add the new win to the user's list only if it doesn't already exist
            champion_wins[user_key]["wins"].append({
                "champion": winner_champion,
                "timestamp": win_timestamp
            })

            # Write the updated data back to the JSON file
            with open(json_file, "w") as file:
                json.dump(champion_wins, file, indent=4)

            # Prepare the message to indicate the champion was added
            status_message = f"**{winner_champion}** successfully added to the win-list."
        else:
            # Prepare the message to indicate the champion was already in the list
            status_message = f"**{winner_champion}** is already in your win-list."

        # Retrieve and sort the user's list of wins by timestamp
        all_wins = sorted(champion_wins[user_key]["wins"], key=lambda win: win["timestamp"])
        all_wins_str = "\n".join([f"{win['champion']} ({win['timestamp']})" for win in all_wins])

        # Prepare the full message
        message = (
            f"{status_message}\n\n"
            f"*Currently in the list:*\n{all_wins_str}"
        )

        # Send an ephemeral message visible only to the user who clicked the button
        await interaction.response.send_message(content=message, ephemeral=True)



def is_git_repo_up_to_date():
    try:
        # Fetch the latest changes from the remote
        subprocess.run(["git", "fetch"], check=True)

        # Check the difference between the local branch and the remote branch
        local_branch = subprocess.run(
            ["git", "rev-parse", "@"],
            check=True,
            stdout=subprocess.PIPE,
            text=True
        ).stdout.strip()
        
        remote_branch = subprocess.run(
            ["git", "rev-parse", "@{u}"],
            check=True,
            stdout=subprocess.PIPE,
            text=True
        ).stdout.strip()
        
        # Check for differences between local and remote branches
        if local_branch == remote_branch:
            print("Your local branch is up to date.")
        else:
            print("Your local branch is not up to date with the remote branch.")
            # Optionally, provide instructions for updating
            print("Consider pulling the latest changes with 'git pull'.")
    except subprocess.CalledProcessError as e:
        print("Verifying Git Status: Error while checking repository status:", e)
    except Exception as e:
        print("Verifying Git Status: An unexpected error occurred, probably because git is not installed.", e)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("I don't have permission to do that. Please check my role permissions.")
    elif isinstance(error, commands.CommandNotFound):
        pass
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
        await generate_teams(ctx)
    elif arg.isdigit():
        await generate_teams(ctx, arg)
    elif arg.lower() == "help":
        await list_commands(ctx)
    elif arg.lower() == "list":
        await list_players(ctx)
    elif arg.lower() in ["champions", "c"]:
        await generate_champions(ctx)
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

    await ctx.send(embed=embed, view=ArenaHelpView(ctx))

async def list_players(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        members = voice_channel.members

        embed = discord.Embed(
            title=f"List of players in {voice_channel.name}",
            color=discord.Color.blue()
        )
        for member in members:
            if member.id not in player_numbers:
                player_numbers[member.id] = len(player_numbers) + 1
            embed.add_field(name=f"{player_numbers[member.id]}", value=member.name, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("You need to be in a voice channel to use this command!")

async def generate_teams(ctx, arg=None):
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        members = [member for member in voice_channel.members if not member.bot]
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

async def generate_champions(ctx, interaction=None, reroll_count=0, max_rerolls=2, clicked_user=None):
    random_champions = random.sample(lol_champions, 2)

    def clean_name(name):
        return name.lower().replace("'", "").replace(" ", "")

    champion1_url = f"https://blitz.gg/lol/champions/{clean_name(random_champions[0])}/arena"
    champion2_url = f"https://blitz.gg/lol/champions/{clean_name(random_champions[1])}/arena"

    champion1_hyperlink = f"[{random_champions[0]}]({champion1_url})"
    champion2_hyperlink = f"[{random_champions[1]}]({champion2_url})"

    author = clicked_user if clicked_user else ctx.author.name
    embed = discord.Embed(
        title="Random Champions",
        description=f"{author}: {champion1_hyperlink}\nTeammate: {champion2_hyperlink}",
        color=discord.Color.orange()
    )

    if interaction:
        await interaction.response.edit_message(embed=embed, view=ChampionButtonView(ctx, random_champions, reroll_count, max_rerolls))
    else:
        await ctx.send(embed=embed, view=ChampionButtonView(ctx, random_champions, reroll_count, max_rerolls))

is_git_repo_up_to_date()
bot.run(bot_token)
