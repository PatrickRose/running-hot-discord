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
        await ctx.send(error)
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


@bot.command(name='clear-runs', help='Deletes *all* run channels and roles for end of turn clean up')
@commands.has_role('control')
async def clear_runs(ctx):
    guild = ctx.guild

    # Get all channels in this category
    category = discord.utils.get(guild.categories, name='runs')
    channels = [c for c in guild.channels if c.category_id == category.id]
    await ctx.send(f'Deleting {len(channels)} channels, please wait...')

    roles_done = []

    for channel in channels:
        role = discord.utils.get(guild.roles, name=channel.name)
        await channel.delete()

        if role and role not in roles_done:
            await role.delete()
            roles_done.append(role)

    await guild.fetch_channels()
    await guild.fetch_roles()
    await ctx.send(f'Channels and roles deleted')

@bot.command(name='play', help='Plays the card with the given name')
async def play_card(ctx: commands.context.Context, card_name: str):
    if card_name not in CARD_LIST:
        await ctx.send(f'{ctx.message.author.mention} Unknown card {card_name}')
    else:
        file = discord.File(CARD_LIST[card_name], filename=f'{card_name}.png')
        await ctx.send(f'{ctx.message.author.nick or ctx.message.author.name} plays {card_name}', file=file)


bot.run(TOKEN)
