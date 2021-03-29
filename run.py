# bot.py
import datetime
import json
import os
import random

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

with open('cards.json') as cards:
    CARD_LIST = json.load(cards)

command_prefix = os.getenv('COMMAND_PREFIX', '!!')
bot = commands.Bot(command_prefix=command_prefix)


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


control_role_name = 'Control' if os.getenv('UPPERCASE_CONTROL') else 'control'

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You do not have the correct role for this command.')
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send(error)
    elif isinstance(error, commands.errors.CommandNotFound):
        await ctx.send("Unknown command - try {0}help to see the available commands".format(command_prefix))
        pass
    else:
        control = discord.utils.get(ctx.guild.roles, name='bot-master')

        await ctx.send(f'{control.mention} there was a problem running this command please investigate')
        raise error


@bot.command(
    name='run-facility',
)
async def create_run(ctx, short_corp: str, facility: str):
    guild: discord.Guild = ctx.guild

    if short_corp not in CORPORATION_NAMES:
        await ctx.send(
            '{0} - {1} not found (must be one of {2})'.format(
                ctx.message.author.mention,
                short_corp,
                ', '.join(CORPORATION_NAMES)
            )
        )
        return

    category_name = f'runs-{short_corp}'
    category: discord.CategoryChannel = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name)

    text_channel: discord.TextChannel = discord.utils.get(category.text_channels,
                                                          name=f'{short_corp}-{facility.lower()}')

    if not text_channel:
        await ctx.send(
            '{0} - {1} not found as a facility for {2}'.format(
                ctx.message.author.mention,
                facility,
                CORPORATION_NAMES[short_corp]
            )
        )
        return

    # Make sure the runner isn't already on a run - that'd be naughty!
    for role in ctx.author.roles:
        if role.name.find('run-') == 0:
            await ctx.send(
                f'{ctx.message.author.mention} - you are already on a run!'
            )
            return

    voice_channel: discord.VoiceChannel = discord.utils.get(category.voice_channels,
                                                            name=f'{short_corp}-{facility.lower()}')

    role = None

    # Check if there's a run role already - if not we'll create a new one
    for key in text_channel.overwrites:
        if isinstance(key, discord.Role) and key.name.find('run-') == 0:
            role = key
            break

    send_initiation_message = False

    if not role:
        # Work out what's the new run number
        while True:
            random_bytes = random.getrandbits(16)

            role_name = f"run-{random_bytes}"
            # Next, create the run-* role
            role = discord.utils.get(guild.roles, name=role_name)

            if not role:
                role = await guild.create_role(name=role_name)
                send_initiation_message = True
                break

    await text_channel.set_permissions(role, read_messages=True)
    await voice_channel.set_permissions(role, view_channel=True)

    corp_role: discord.Role = discord.utils.get(guild.roles, name=CORPORATION_ROLE_NAMES[short_corp])

    if send_initiation_message:
        await text_channel.send(
            f"!!! RUN INITIATED !!!\n{corp_role.mention} please send your security representative to defend")

        await text_channel.send(
            "When resolving rolls, use the `!roll` command.\nTo roll 6 d8 and count the number of success, use `!roll 6d8 t5`.\nTo roll 6 d6 and count the number of successes, use `!roll 6d6 t5`\nYou can play cards using the `{0}play` command - see your relevant Google doc for the command you need".format(
                command_prefix
            )
        )

    await ctx.message.author.add_roles(role)

    await text_channel.send(f'{ctx.message.author.mention} has joined the run')


@bot.command(name='clear-runs', help='Deletes *all* run channels and roles for end of turn clean up')
@commands.has_role(control_role_name)
async def clear_runs(ctx):
    guild = ctx.guild

    # Get all channels in this category
    for corp_name in CORPORATION_NAMES:
        category_name = f'runs-{corp_name}'
        category = discord.utils.get(guild.categories, name=category_name)

        if category:
            channels = category.text_channels
            await ctx.send(f'Deleting content in {len(channels)} channels, please wait...')

            channel: discord.TextChannel
            delta = datetime.timedelta(days=14)
            for channel in channels:
                msgs = await channel.history(limit=100, after=datetime.datetime.now() - delta).flatten()
                if not msgs:
                    continue

                try:
                    await ctx.send(f'Deleting content in {channel.name}')
                    await channel.delete_messages(msgs)
                except discord.DiscordException:
                    continue

    from discord import Role
    role: Role
    for role in guild.roles:
        if role.name.find('run-') == 0:
            await role.delete()

    await ctx.send(f'Runs cleared')
    await guild.fetch_roles()


@bot.command(name='play', help='Plays the card with the given name')
async def play_card(ctx: commands.context.Context, card: str):
    if card not in CARD_LIST:
        await ctx.send(f'{ctx.message.author.mention} Unknown card {card}')
    else:
        card_name = CARD_LIST[card]
        file = discord.File(f'card-images/{card}.png', filename=f'{card_name}.png')
        await ctx.send(f'{ctx.message.author.nick or ctx.message.author.name} plays {card_name}', file=file)


async def create_category(guild, name, overwrites=None, text_channels=None, voice_channels=None):
    if voice_channels is None:
        voice_channels = {}
    if text_channels is None:
        text_channels = {}
    if overwrites is None:
        overwrites = {}
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
    'mccullough': 'McCullough Mechanical'
}

CORPORATION_ROLE_NAMES = {
    'augmented': os.getenv('ANT_ROLE_NAME', 'augmented-nucleotech'),
    'dtc': os.getenv('DTC_ROLE_NAME', 'digital-tactical-control'),
    'genetic': os.getenv('GENEQ_ROLE_NAME', 'genetic-equity'),
    'gordon': os.getenv('GORDON_ROLE_NAME', 'gordon-corporation'),
    'mccullough': os.getenv('MCM_ROLE_NAME', 'mccullough-mechanical')
}


@bot.command(name='build-facility', help='Builds a facility')
@commands.has_role(control_role_name)
async def build_facility(ctx: commands.context.Context, short_corp: str, facility_type: str, facility_name: str):
    if short_corp not in CORPORATION_NAMES:
        await ctx.send(
            '{0} not found (must be one of {1})'.format(
                short_corp,
                ', '.join(CORPORATION_NAMES)
            )
        )
        return

    guild = ctx.guild

    from discord import TextChannel
    channel: TextChannel = discord.utils.get(guild.channels, name='facility-list')

    assert channel is not None, "facility-list was not found?"

    corporation_name = CORPORATION_NAMES[short_corp]

    facilities = []
    message_to_edit: discord.message = None

    async for message in channel.history():
        if corporation_name in message.content:
            facilities = await facility_from_message(message)
            message_to_edit = message
            break

    # Make sure the names are unique
    if facility_name in [x[0] for x in facilities]:
        await ctx.send(f'{ctx.message.author.mention} - Already have a facility with that name')
        return

    facilities.append([facility_name, facility_type])

    from tabulate import tabulate
    table_string = tabulate(facilities, ["Facility name", "Facility Type"], tablefmt="github")
    message_contents = f'{corporation_name} facilities:\n```\n{table_string}\n```'

    await channel.send(message_contents)

    if message_to_edit:
        await message_to_edit.delete()

    # Now create a run channel
    channel_name = f'{short_corp}-{facility_name.lower()}'
    control = discord.utils.get(guild.roles, name=control_role_name)

    role = discord.utils.get(guild.roles, name=CORPORATION_ROLE_NAMES[short_corp])
    category_name = f'runs-{short_corp}'
    category = discord.utils.get(guild.categories, name=category_name)

    if not category:
        category = await guild.create_category(category_name)

    await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            control: discord.PermissionOverwrite(read_messages=True),
            role: discord.PermissionOverwrite(read_messages=True)
        }
    )

    await guild.create_voice_channel(
        name=channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            control: discord.PermissionOverwrite(view_channel=True),
            role: discord.PermissionOverwrite(view_channel=True)
        }
    )

    await ctx.send(f'{ctx.message.author.mention} - facility built')


@bot.command(name='remove-facility', help='Remove a facility')
@commands.has_role(control_role_name)
async def remove_facility(ctx: commands.context.Context, short_corp: str, facility_name: str):
    from discord import TextChannel
    from tabulate import tabulate

    guild: discord.Guild = ctx.guild

    channel: TextChannel = discord.utils.get(guild.channels, name='facility-list')

    assert channel is not None, "facility-list was not found?"

    corporation_name = CORPORATION_NAMES[short_corp]

    async for message in channel.history():
        if corporation_name in message.content:
            facilities = await facility_from_message(message)
            facilities = list(filter(lambda x: x[0] != facility_name, facilities))

            table_string = tabulate(facilities, ["Facility name", "Facility Type"], tablefmt="github")
            message_contents = f'{corporation_name} facilities:\n```\n{table_string}\n```'

            await channel.send(message_contents)
            await message.delete()

            channel = discord.utils.get(guild.channels, name=f'{short_corp}-{facility_name.lower()}')

            while channel:
                await channel.delete()
                await guild.fetch_channels()
                channel = discord.utils.get(guild.channels, name=f'{short_corp}-{facility_name.lower()}')

            await ctx.send(f'{ctx.message.author.mention} - facility removed')

            break

async def facility_from_message(message):
    return [[y.strip() for y in x.split('|')[1:-1]] for x in message.content.split("\n")[4:-1]]


@bot.command(name='roll', help='Rolls dice')
async def roll_dice(ctx: commands.context.Context, die_string: str):
    try:
        (amount, die_type) = die_string.split('d')
        amount = int(amount)
        die_type = int(die_type)
    except ValueError:
        await ctx.send(f'{ctx.message.author.mention} dice format unknown - use `1d6`, `5d8` etc')
        return

    values = [random.randint(1, die_type) for _ in range(amount)]
    values.sort(reverse=True)
    values = [f"**{x}**" if x >= 5 else str(x) for x in values]
    success = list(filter(lambda x: x[0] == '*', values))

    result = f'{len(success)}\nRolls: {", ".join(values)}'

    await ctx.send(f'{ctx.message.author.mention} rolls `{die_string}`: {result}')

bot.run(TOKEN)
