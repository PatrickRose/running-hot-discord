# bot.py
import json
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

with open('cards.json') as cards:
    CARD_LIST = json.load(cards)

bot = commands.Bot(command_prefix='!')


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You do not have the correct role for this command.')
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send(error)
    elif isinstance(error, commands.errors.CommandNotFound):
        # Don't send anything to the server because of how other bots work
        print(error)
    else:
        control = discord.utils.get(ctx.guild.roles, name='control')

        await ctx.send(f'{control.mention} there was a problem running this command please investigate')
        raise error


@bot.command(
    name='create-run',
    help='Create a run text+voice channel, limited to the run-* role - use mentions to assign roles automatically'
)
@commands.has_role('control')
async def create_run(ctx):
    guild = ctx.guild
    run_number = 1
    channel_name = f"run-{run_number}"

    # Work out what's the new run number
    while discord.utils.get(guild.channels, name=channel_name):
        run_number += 1
        channel_name = f"run-{run_number}"

    # Next, create the run-* role
    role = discord.utils.get(guild.roles, name=channel_name)
    control = discord.utils.get(guild.roles, name='control')
    if not role:
        role = await guild.create_role(name=channel_name)

    category = discord.utils.get(guild.categories, name='runs')
    if not category:
        category = await guild.create_category('runs')

    text_channel = await guild.create_text_channel(
        channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            control: discord.PermissionOverwrite(read_messages=True),
            role: discord.PermissionOverwrite(read_messages=True)
        }
    )
    await guild.create_voice_channel(
        channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            control: discord.PermissionOverwrite(view_channel=True),
            role: discord.PermissionOverwrite(view_channel=True)
        }
    )

    await ctx.send(f'Created text/voice channels {channel_name}')

    channel_message = ''

    # Now go through the list of people in the run and give them the run role
    for user in ctx.message.mentions:
        try:
            await user.add_roles(role)
            channel_message += f'{user.mention} '
        except Exception as e:
            await ctx.send(
                f'{control.mention} Could\'t give {user.name} the role {role.name}! Please assign manually'
            )
            print(e)

    if channel_message:
        await text_channel.send(f'{channel_message.strip()}, please report to this channel to resolve the run')

    await text_channel.send("When resolving rolls, use the `!roll` command.\nTo roll 6 d8 and count the number of "
                            "success, use `!roll 6d8 t5`.\nTo roll 6 d6 and count the number of successes, "
                            "use `!roll 6d6 t5`\nYou can play cards using the `!play` command - see your "
                            "relevant Google doc for the command you need")


@bot.command(name='clear-runs', help='Deletes *all* run channels and roles for end of turn clean up')
@commands.has_role('control')
async def clear_runs(ctx):
    guild = ctx.guild

    # Get all channels in this category
    category = discord.utils.get(guild.categories, name='runs')
    channels = category.channels
    await ctx.send(f'Deleting {len(channels)} channels, please wait...')

    roles_done = []

    for channel in channels:
        role = discord.utils.get(guild.roles, name=channel.name)
        if channel.name != "run-bot-commands":
            await channel.delete()

        if role and role not in roles_done:
            await role.delete()
            roles_done.append(role)

    await guild.fetch_channels()
    await guild.fetch_roles()
    await ctx.send(f'Channels and roles deleted')


@bot.command(name='play', help='Plays the card with the given name')
async def play_card(ctx: commands.context.Context, card: str):
    if card not in CARD_LIST:
        await ctx.send(f'{ctx.message.author.mention} Unknown card {card}')
    else:
        card_name = CARD_LIST[card]
        file = discord.File(f'card-images/{card}.png', filename=f'{card_name}.png')
        await ctx.send(f'{ctx.message.author.nick or ctx.message.author.name} plays {card_name}', file=file)


async def create_category(guild, name, overwrites={}, text_channels={}, voice_channels={}):
    category = discord.utils.get(guild.categories, name=name)

    if not category:
        category = await guild.create_category(
            name=name,
            overwrites=overwrites
        )

    for name in text_channels:
        await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=text_channels[name]
        )

    for name in voice_channels:
        await guild.create_voice_channel(
            name=name,
            category=category,
            overwrites=text_channels[name]
        )

    return category


async def delete_category(category):
    category_channels = category.channels
    for channel in category_channels:
        await channel.delete()

    await category.delete()


CORPORATION_NAMES = {
    'augmented': 'Augmented Nucleotech',
    'dtc': 'Digital Tactical Control',
    'genetic': 'Genetic Equity',
    'gordon': 'Gordon Corporation',
    'muccullough': 'MucCullough Mechanical'
}

FACILITY_TYPES = [
    'research',
    'security',
    'corporate',
    'ai-school'
]


@bot.command(name='build-facility', help='Builds a facility')
@commands.has_role('control')
async def play_card(ctx: commands.context.Context, corporation_name: str, facility_type: str, facility_name: str):
    if corporation_name not in CORPORATION_NAMES:
        await ctx.send(
            f'{0} not found (must be one of {1})'.format(
                corporation_name,
                ','.join(str(x) for x in CORPORATION_NAMES)
            )
        )
        return

    if facility_type not in FACILITY_TYPES:
        await ctx.send(f'Unknown facility type {facility_type}')
        return

    guild = ctx.guild

    from discord import TextChannel
    channel: TextChannel = discord.utils.get(guild.channels, name='facility-list')

    assert channel is not None, "facility-list was not found?"

    corporation_name = CORPORATION_NAMES[corporation_name]

    facilities = []
    message_to_edit: discord.message = None

    async for message in channel.history():
        if corporation_name in message.content:
            facilities = [[y.strip() for y in x.split('|')[1:-1]] for x in message.content.split("\n")[4:-1]]
            message_to_edit = message
            break

    # Make sure the names are unique
    if facility_name in [x[0] for x in facilities]:
        await ctx.send(f'{ctx.message.author.mention} - Already have a facility with that name')
        return

    facilities.append([facility_name, facility_type])

    from tabulate import tabulate
    message_contents = f'{corporation_name} facilities:\n```\n{tabulate(facilities, ["Facility name", "Facility Type"], tablefmt="github")}\n```'

    if message_to_edit:
        await message_to_edit.edit(content=message_contents)
    else:
        await channel.send(message_contents)

    await ctx.send(f'{ctx.message.author.mention} - facility built')

bot.run(TOKEN)
